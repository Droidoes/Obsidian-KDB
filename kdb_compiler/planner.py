"""planner — turn last_scan + manifest into a list of CompileJobs.

Pipeline position:
    kdb_scan -> [planner] -> compiler -> patch_applier -> source_state_update

One CompileJob per eligible source. The planner owns:

  1. **Binary filter** (blueprint locked decision). kdb_scan puts every
     NEW/CHANGED file into `to_compile` regardless of `is_binary`; binaries
     can't be read as UTF-8 and have no per-source LLM contract in M2 v1.
     v1.1 will add a metadata-only page path; for now they stay in the
     manifest and are dropped here.

  2. **Absolute path resolution**. `source_id` like "KDB/raw/foo.md" is
     vault-relative POSIX; jobs carry the absolute path for the compiler.

  3. **Context-snapshot pre-build**. We read the source file (UTF-8) so
     graph_context_loader can run its tier-ranked matching. A read failure
     is *not* fatal at plan time — we emit an empty source_text, let the
     job reach compile_one, and the compiler captures the read failure in
     its resp-stats record (blueprint §9). Keeps the "one resp-stats record
     per eligible source" invariant even for unreadable files.

Context authority: GraphDB only (D49). manifest.json is not used for
context generation. If GraphDB is missing/empty/corrupt, planning fails
loud — operator runs `graphdb-kdb rebuild`.

CLI `kdb-plan` prints the job list for inspection. Not part of the
normal run path (compile drives planner internally via `plan()`).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from contextlib import contextmanager
from pathlib import Path

from kdb_compiler import graph_context_loader
from kdb_compiler.graph_context_loader import T2Mode
from kdb_compiler.source_io import SourceFrontmatter, parse_source_file
from kdb_compiler.types import CompileJob, ContextSnapshot


# ---------- manifest I/O ----------

def load_manifest(state_root: Path) -> dict:
    """Return manifest.json contents or {} if missing / unreadable.

    Missing-and-empty are both treated as bootstrap (no prior state). A
    JSONDecodeError is *not* swallowed — that indicates a corrupt file
    and should surface to the operator.
    """
    path = Path(state_root) / "manifest.json"
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return {}
    return json.loads(text)


# ---------- eligible sources ----------

def eligible_source_ids(scan: dict) -> list[str]:
    """Return scan['to_compile'] with binaries dropped, preserving scan order.

    A source_id is binary when its matching entry in scan['files'][*] has
    is_binary=True. Source_ids with no matching file record are kept
    (defensive — shouldn't happen in practice but not our bug to raise on).
    """
    to_compile = scan.get("to_compile") or []
    files = scan.get("files") or []
    binary_paths: set[str] = {
        f.get("path")
        for f in files
        if isinstance(f, dict) and f.get("is_binary") is True
    }
    return [sid for sid in to_compile if sid not in binary_paths]


# ---------- env-var resolution (Task #90 v0.2 — D-90-9) ----------

def _resolve_t2_mode_from_env() -> T2Mode:
    """Resolve KDB_T2_MODE to a T2Mode value. Default STRUCTURED per D-90-1.

    Case-insensitive. Invalid value raises RuntimeError (loud failure on
    misconfiguration — silent fallback to default would hide operator error).
    """
    raw = os.environ.get("KDB_T2_MODE", "").strip().lower()
    if not raw:
        return T2Mode.STRUCTURED
    try:
        return T2Mode(raw)
    except ValueError as exc:
        valid = ", ".join(m.value for m in T2Mode)
        raise RuntimeError(
            f"KDB_T2_MODE={raw!r} is invalid. Expected one of: {valid}."
        ) from exc


def _resolve_t2_resolver_from_env() -> str:
    """Resolve KDB_T2_RESOLVER to "simple" or "batch". Default "simple" per D-90-9."""
    raw = os.environ.get("KDB_T2_RESOLVER", "").strip().lower()
    if not raw:
        return "simple"
    if raw not in ("simple", "batch"):
        raise RuntimeError(
            f"KDB_T2_RESOLVER={raw!r} is invalid. Expected: 'simple' or 'batch'."
        )
    return raw


# ---------- job construction ----------

def _parse_source_for_plan(abs_path: Path) -> tuple[SourceFrontmatter | None, str]:
    """Plan-time wrapper around source_io.parse_source_file with degrade.

    Returns (None, "") on any I/O or decode failure — compile_one is the
    authoritative source-read gate; planner degrades to empty context.
    """
    try:
        return parse_source_file(abs_path)
    except (OSError, UnicodeDecodeError):
        return None, ""


def build_jobs(
    scan: dict,
    manifest: dict,
    vault_root: Path,
    *,
    context_page_cap: int = 50,
) -> list[CompileJob]:
    """Pure-ish (reads source files). One job per eligible source_id.

    Context authority: GraphDB only (D49). If the deprecated env var
    KDB_CONTEXT_SOURCE=manifest is set, raises explicitly.
    """
    vault_root = Path(vault_root)
    context_source = os.environ.get("KDB_CONTEXT_SOURCE", "")
    if context_source == "manifest":
        raise RuntimeError(
            "KDB_CONTEXT_SOURCE=manifest is deprecated (D49). "
            "GraphDB is the only supported context authority. "
            "Unset the variable or run `graphdb-kdb rebuild`."
        )

    t2_mode = _resolve_t2_mode_from_env()
    t2_resolver = _resolve_t2_resolver_from_env()

    with _graph_conn_or_raise() as conn:
        jobs: list[CompileJob] = []
        for source_id in eligible_source_ids(scan):
            abs_path = vault_root / source_id
            frontmatter, source_text = _parse_source_for_plan(abs_path)
            snapshot = _build_context(
                conn, source_id=source_id,
                source_text=source_text, page_cap=context_page_cap,
                frontmatter=frontmatter, mode=t2_mode, resolver=t2_resolver,
            )
            jobs.append(CompileJob(
                source_id=source_id,
                abs_path=str(abs_path),
                context_snapshot=snapshot,
            ))
        return jobs


def _build_context(
    conn,
    *,
    source_id: str,
    source_text: str,
    page_cap: int = 50,
    frontmatter: SourceFrontmatter | None = None,
    mode: T2Mode = T2Mode.STRUCTURED,
    resolver: str = "simple",
) -> ContextSnapshot:
    """Thin delegation to graph_context_loader (seam for test stubbing)."""
    return graph_context_loader.build_context_snapshot(
        conn, source_id=source_id, source_text=source_text, page_cap=page_cap,
        frontmatter=frontmatter, mode=mode, resolver=resolver,
    )


@contextmanager
def _graph_conn_or_raise():
    """Open GraphDB via context manager or raise RuntimeError with guidance.

    Validates: (1) graph path exists, (2) graph has >0 entities.
    Yields: kuzu.Connection for the duration of the block.
    """
    from graphdb_kdb import default_graph_path
    from graphdb_kdb.graphdb import GraphDB

    graph_path = default_graph_path()

    if not graph_path.exists():
        raise RuntimeError(
            f"GraphDB unavailable at {graph_path}. "
            "Run `graphdb-kdb rebuild` to regenerate from run journals."
        )

    with GraphDB(graph_path, read_only=True) as gdb:
        if gdb.stats()["entities"] == 0:
            raise RuntimeError(
                f"GraphDB at {graph_path} has 0 entities. "
                "Run `graphdb-kdb rebuild` to regenerate from run journals."
            )
        yield gdb.conn


def plan(
    vault_root: Path,
    *,
    scan: dict,
    state_root: Path | None = None,
    context_page_cap: int = 50,
) -> list[CompileJob]:
    """I/O shell. Loads manifest for state purposes, delegates to build_jobs.

    Context is always built from GraphDB (D49). Manifest is loaded for
    downstream pipeline stages (patch_applier, source_state_update) — not for
    context generation.
    """
    vault_root = Path(vault_root)
    if state_root is None:
        state_root = vault_root / "KDB" / "state"
    manifest = load_manifest(state_root)
    return build_jobs(scan, manifest, vault_root, context_page_cap=context_page_cap)


# ---------- CLI ----------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="kdb-plan",
        description="Build a CompileJob list from last_scan.json + manifest.json.",
    )
    p.add_argument("--vault-root", required=True, help="Absolute path to Obsidian vault root")
    p.add_argument("--page-cap", type=int, default=50, help="Max pages per context snapshot (default 50)")
    p.add_argument("--json", action="store_true", help="Emit JSON instead of a human-readable list")
    return p


def _job_to_cli_dict(job: CompileJob) -> dict:
    return {
        "source_id": job.source_id,
        "abs_path": job.abs_path,
        "context_page_count": len(job.context_snapshot.pages),
        "context_slugs": [p.slug for p in job.context_snapshot.pages],
    }


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    vault_root = Path(args.vault_root)
    state_root = vault_root / "KDB" / "state"
    scan_path = state_root / "last_scan.json"

    if not scan_path.exists():
        print(f"kdb-plan: missing last_scan.json at {scan_path}", file=sys.stderr)
        return 1

    try:
        scan = json.loads(scan_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"kdb-plan: last_scan.json unreadable: {exc}", file=sys.stderr)
        return 1

    jobs = plan(vault_root, scan=scan, state_root=state_root, context_page_cap=args.page_cap)

    if args.json:
        print(json.dumps([_job_to_cli_dict(j) for j in jobs], indent=2, ensure_ascii=False))
    else:
        print(f"kdb-plan: {len(jobs)} job(s) from {len(scan.get('to_compile', []))} to_compile entries")
        for j in jobs:
            print(f"  {j.source_id}  ({len(j.context_snapshot.pages)} context pages)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

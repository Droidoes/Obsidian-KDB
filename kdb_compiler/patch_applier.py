"""patch_applier — writes wiki pages from compile_result + next_manifest.

Architecture (Selection A + iii + a, M1.6 blueprint):
    * Pure core renders PagePatch objects.
    * I/O shell (`apply`) does all filesystem writes via atomic_io.
    * CLI runs pure manifest_update.build_manifest_update() to get next_manifest
      in memory, then applies — but does NOT write manifest.json (that is
      manifest_update's CLI or the M1.7 orchestrator's last step).

Contracts:
    * D8: LLM emits slug-keyed intents; Python owns frontmatter + paths.
    * D14: atomic temp+fsync+os.replace via atomic_io.
    * D18: full-body replacement.
    * D22: no imaginary complexity.
    * D23: no index.md — Obsidian file explorer + manifest.json serve as TOC.
    * D24: no log.md — state/runs/<run_id>.json is the authoritative journal.

Never writes outside KDB/wiki/. Never mutates KDB/raw/ or KDB/state/.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import manifest_update
from . import paths
from .atomic_io import atomic_write_text
from .run_context import RunContext, SCHEMA_VERSION, run_id_from_timestamp, now_iso


class PagePatchError(Exception):
    """Raised for invariant violations while rendering or applying patches."""


# -------------------------------------------------------------------------
# Dataclasses
# -------------------------------------------------------------------------

@dataclass
class PagePatch:
    page_key: str
    abs_path: Path
    frontmatter: dict
    body: str


@dataclass
class ApplyResult:
    pages_written: list[str] = field(default_factory=list)
    pages_skipped: list[str] = field(default_factory=list)
    dry_run: bool = False
    counts: dict = field(default_factory=dict)


# -------------------------------------------------------------------------
# YAML emitter — hand-rolled, fixed shape (blueprint §3)
# -------------------------------------------------------------------------

_FM_KEY_ORDER: tuple[str, ...] = (
    "title", "slug", "page_type", "status",
    "raw_path", "raw_hash", "raw_mtime",
    "compiled_at", "compiler_version", "schema_version_used",
    "source_refs",
)
_SRC_REF_KEY_ORDER: tuple[str, ...] = ("source_id", "hash", "role")

_BARE_STR = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._\-/ ]*$")
_YAML_RESERVED_FIRST = set("!&*@%|>?-:#,[]{}")


def _yaml_str(s: str) -> str:
    if "\n" in s:
        raise PagePatchError(f"Frontmatter string contains newline: {s!r}")
    if s == "" or s[0] in _YAML_RESERVED_FIRST or not _BARE_STR.match(s) or ":" in s or "#" in s:
        escaped = s.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return s


def _yaml_scalar(v: Any) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return repr(v)
    if isinstance(v, str):
        return _yaml_str(v)
    raise PagePatchError(f"Unsupported frontmatter scalar type: {type(v).__name__}")


def _emit_source_refs(refs: list[dict]) -> str:
    if not refs:
        return "source_refs: []\n"
    out = ["source_refs:"]
    for ref in refs:
        first = True
        for k in _SRC_REF_KEY_ORDER:
            if k not in ref:
                continue
            prefix = "  - " if first else "    "
            out.append(f"{prefix}{k}: {_yaml_scalar(ref[k])}")
            first = False
    return "\n".join(out) + "\n"


def emit_frontmatter(fm: dict) -> str:
    """Serialize frontmatter dict to YAML block (`---` wrapped)."""
    lines: list[str] = ["---"]
    for k in _FM_KEY_ORDER:
        if k not in fm:
            continue
        v = fm[k]
        if k == "source_refs":
            lines.append(_emit_source_refs(v).rstrip("\n"))
        else:
            lines.append(f"{k}: {_yaml_scalar(v)}")
    lines.append("---")
    lines.append("")
    return "\n".join(lines) + "\n"


# -------------------------------------------------------------------------
# Pure core
# -------------------------------------------------------------------------

def _select_primary_ref(page_record: dict) -> dict:
    """Pick the ref used to populate singular `raw_*` frontmatter fields.

    Summaries have a role=primary ref (set by manifest_update). Concepts and
    articles are cross-source and have none — fall back to the first ref
    after sorting by source_id for determinism.
    """
    refs = page_record.get("source_refs", [])
    if not refs:
        raise PagePatchError(
            f"Page {page_record.get('page_id', '<?>')} has no source_refs"
        )
    for ref in refs:
        if ref.get("role") == "primary":
            return ref
    return sorted(refs, key=lambda r: r["source_id"])[0]


def _source_mtime(next_manifest: dict, source_id: str) -> float:
    src = next_manifest.get("sources", {}).get(source_id)
    if not src:
        raise PagePatchError(f"Primary source {source_id!r} missing from manifest.sources")
    mtime = src.get("mtime")
    if not isinstance(mtime, (int, float)):
        raise PagePatchError(f"Source {source_id!r} has non-numeric mtime: {mtime!r}")
    return float(mtime)


def _fm_for_page(page_record: dict, next_manifest: dict, run_ctx: RunContext) -> dict:
    primary = _select_primary_ref(page_record)
    raw_path = primary["source_id"]
    return {
        "title": page_record["title"],
        "slug": page_record["slug"],
        "page_type": page_record["page_type"],
        "status": page_record["status"],
        "raw_path": raw_path,
        "raw_hash": primary["hash"],
        "raw_mtime": _source_mtime(next_manifest, raw_path),
        "compiled_at": run_ctx.started_at,
        "compiler_version": run_ctx.compiler_version,
        "schema_version_used": run_ctx.schema_version,
        "source_refs": list(page_record["source_refs"]),
    }


def _normalize_body(body: str) -> str:
    if not body.endswith("\n"):
        return body + "\n"
    stripped = body.rstrip("\n")
    return stripped + "\n"


def render_page(page_record: dict, body: str, next_manifest: dict, run_ctx: RunContext) -> str:
    fm = _fm_for_page(page_record, next_manifest, run_ctx)
    return emit_frontmatter(fm) + _normalize_body(body)


def build_page_patches(
    compile_result: dict, next_manifest: dict, run_ctx: RunContext
) -> list[PagePatch]:
    pages_by_key = next_manifest.get("pages", {})
    patches: list[PagePatch] = []
    for cs in compile_result.get("compiled_sources", []):
        for intent in cs.get("pages", []):
            slug = intent["slug"]
            ptype = intent["page_type"]
            page_key = paths.slug_to_relpath(slug, ptype)
            page_record = pages_by_key.get(page_key)
            if page_record is None:
                raise PagePatchError(
                    f"Compiled intent {slug!r} has no PageRecord at {page_key!r}"
                )
            fm = _fm_for_page(page_record, next_manifest, run_ctx)
            body = _normalize_body(intent["body"])
            abs_path = run_ctx.vault_root / page_key
            patches.append(PagePatch(page_key=page_key, abs_path=abs_path,
                                     frontmatter=fm, body=body))
    return patches


# -------------------------------------------------------------------------
# I/O shell
# -------------------------------------------------------------------------

def _load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _count_page_types(patches: list[PagePatch]) -> dict:
    seen: dict[str, set[str]] = {"summary": set(), "concept": set(), "article": set()}
    for p in patches:
        pt = p.frontmatter.get("page_type")
        if pt in seen:
            seen[pt].add(p.page_key)
    return {k: len(v) for k, v in seen.items()}


def _count_orphans(next_manifest: dict) -> int:
    return sum(
        1 for p in next_manifest.get("pages", {}).values()
        if p.get("status") == "orphan_candidate"
    )


def apply(
    vault_root: Path,
    *,
    compile_result: dict,
    next_manifest: dict,
    run_ctx: RunContext,
    write: bool = True,
) -> ApplyResult:
    """Render pages from `compile_result` against `next_manifest`.

    `compile_result` is passed in explicitly rather than re-read from disk
    so dry-runs (where compile_result.json is NOT written) don't silently
    fall back to a stale on-disk file from a previous run.
    """
    patches = build_page_patches(compile_result, next_manifest, run_ctx)

    per_type = _count_page_types(patches)
    unique_page_keys = sorted({p.page_key for p in patches})
    counts = {
        "pages_written": len(unique_page_keys),
        "summaries": per_type["summary"],
        "concepts": per_type["concept"],
        "articles": per_type["article"],
        "orphan_candidates": _count_orphans(next_manifest),
    }

    result = ApplyResult(
        pages_written=[],
        pages_skipped=[],
        dry_run=(not write) or run_ctx.dry_run,
        counts=counts,
    )
    if result.dry_run:
        return result

    for patch in patches:
        atomic_write_text(patch.abs_path, emit_frontmatter(patch.frontmatter) + patch.body)

    result.pages_written = unique_page_keys
    return result


# -------------------------------------------------------------------------
# CLI
# -------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m kdb_compiler.patch_applier",
        description="Render wiki pages from compile_result (pages-only; does not write manifest.json).",
    )
    p.add_argument("--state-root", required=True, type=Path,
                   help="Directory containing last_scan.json + compile_result.json + (optional) manifest.json")
    p.add_argument("--vault-root", required=True, type=Path,
                   help="Vault root (writes to <vault-root>/KDB/wiki/)")
    p.add_argument("--dry-run", action="store_true")
    return p


def _make_ctx(scan: dict, vault_root: Path, dry_run: bool) -> RunContext:
    run_id = scan.get("run_id") or run_id_from_timestamp(now_iso())
    started_at = scan.get("scanned_at") or now_iso()
    from . import __version__
    return RunContext(
        run_id=run_id,
        started_at=started_at,
        compiler_version=__version__,
        schema_version=SCHEMA_VERSION,
        dry_run=dry_run,
        vault_root=vault_root,
        kdb_root=vault_root / "KDB",
    )


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    state_root: Path = args.state_root
    vault_root: Path = args.vault_root

    try:
        scan = _load_json(state_root / "last_scan.json")
        cr = _load_json(state_root / "compile_result.json")
    except FileNotFoundError as e:
        print(f"patch_applier: missing input — {e}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as e:
        print(f"patch_applier: invalid JSON — {e}", file=sys.stderr)
        return 2

    if scan.get("run_id") != cr.get("run_id"):
        print(
            f"patch_applier: run_id mismatch last_scan={scan.get('run_id')!r} "
            f"compile_result={cr.get('run_id')!r}",
            file=sys.stderr,
        )
        return 2

    manifest_path = state_root / "manifest.json"
    prior = _load_json(manifest_path) if manifest_path.exists() else {}

    ctx = _make_ctx(scan, vault_root, args.dry_run)
    try:
        next_manifest, _stage = manifest_update.build_manifest_update(prior, scan, cr, ctx)
        result = apply(vault_root, compile_result=cr,
                       next_manifest=next_manifest,
                       run_ctx=ctx, write=not args.dry_run)
    except PagePatchError as e:
        print(f"patch_applier: {e}", file=sys.stderr)
        return 1
    except Exception as e:  # noqa: BLE001
        print(f"patch_applier: unexpected error — {e}", file=sys.stderr)
        return 1

    mode = "dry-run" if result.dry_run else "applied"
    print(f"patch_applier ({mode}): {len(result.pages_written)} pages")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

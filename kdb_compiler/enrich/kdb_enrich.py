# kdb_compiler/enrich/kdb_enrich.py
"""kdb-enrich — fire Pass-1 enrichment on one or more sources.

Usage:
    kdb-enrich <source.md> [<source.md> ...] [--provider deepseek] [--model deepseek-v4-flash]
    kdb-enrich --vault ~/Obsidian --include 'essays/**' [--provider ...] [--model ...]
    kdb-enrich --dry-run <source.md>     # show what would be enriched; no write
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

from kdb_compiler.enrich.enrich import enrich_one
from kdb_compiler.enrich.pass1_prompt import PASS1_PROMPT_VERSION
from kdb_compiler.enrich.enrich_journal import IngestRunJournal, write_journal
from kdb_compiler.enrich.config_loader import load_scope_config


DEFAULT_PROVIDER = "deepseek"
DEFAULT_MODEL = "deepseek-v4-flash"


def main():
    parser = argparse.ArgumentParser(prog="kdb-enrich")
    parser.add_argument("sources", nargs="*", type=Path,
                        help="Specific source files to enrich.")
    parser.add_argument("--vault", type=Path, default=None,
                        help="Vault root for --include glob mode.")
    parser.add_argument("--include", type=str, action="append", default=[],
                        help="Glob pattern relative to --vault.")
    parser.add_argument("--provider", default=DEFAULT_PROVIDER)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--runs-root", type=Path,
                        default=Path.home() / "Obsidian/KDB/state/ingest_runs")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    # Resolve source files
    sources = _resolve_sources(args)
    if not sources:
        print("No sources to enrich.", file=sys.stderr)
        sys.exit(1)

    run_id = f"ingest-{datetime.now().astimezone().strftime('%Y-%m-%dT%H-%M-%S')}"
    scope = load_scope_config()
    journal = IngestRunJournal(
        run_id=run_id,
        prompt_version=PASS1_PROMPT_VERSION,
        model=args.model,
        force_signal_globs=list(scope.force_signal),
        force_noise_globs=list(scope.force_noise),
        timestamp=datetime.now().astimezone().isoformat(timespec="seconds"),
    )

    if args.dry_run:
        print(f"[DRY-RUN] would enrich {len(sources)} sources with run_id={run_id}")
        for s, _ in sources:
            print(f"  {s}")
        return

    t0 = time.monotonic()
    for source_path, source_id in sources:
        result = enrich_one(
            source_path=source_path, source_id=source_id,
            runs_root=args.runs_root, run_id=run_id,
            provider=args.provider, model=args.model,
        )
        print(f"  {result.outcome:30s}  {source_id}")
        journal.sources_processed += 1
        journal.by_outcome[result.outcome] += 1
    journal.duration_seconds = round(time.monotonic() - t0, 2)
    journal_path = write_journal(args.runs_root, journal)
    print(f"\nrun_id={run_id}")
    print(f"journal={journal_path}")
    print(f"sources_processed={journal.sources_processed}")
    print(f"by_outcome={journal.by_outcome}")


def _resolve_sources(args) -> list[tuple[Path, str]]:
    """Returns list of (absolute_path, vault_relative_id) pairs."""
    out: list[tuple[Path, str]] = []
    if args.sources:
        for s in args.sources:
            out.append((s.resolve(), s.name))
    if args.vault and args.include:
        for pattern in args.include:
            for p in args.vault.glob(pattern):
                if p.suffix == ".md":
                    rel = str(p.relative_to(args.vault))
                    out.append((p.resolve(), rel))
    return out


if __name__ == "__main__":
    main()

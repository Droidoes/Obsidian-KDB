"""cohort_slug_collision_guard — Task #115, blueprint Task 0.3 (READ-ONLY).

Groups a cohort corpus by the FULLY NORMALIZED `expected_summary_slug`
(source stem → common.paths.slugify → 112-char stem budget → "summary-"
prefix — the same derivation Task 1.4 centralizes in Phase 1) and reports:

  - cross-source collision groups (distinct sources whose derived slugs
    coincide after normalization/truncation — e.g. `Foo Bar.md` vs
    `foo-bar.md`, or long-stem truncation collisions);
  - underivable stems (empty / non-ASCII-only normalization).

Verdict contract (blueprint Task 0.3 / R13 F3):
  zero collisions  ⇒ the deferred cross-source reservation (#116) exposes the
                     cohort to no known collision case — the cohort may fire.
  any collision    ⇒ STOP and resolve before firing the baseline/comparison.

This script is the spec-pinned STAND-IN for the Phase-1 production helper
(`compiler.expected_summary_slug`) — Phase 1 adds an equivalence test
pinning this derivation identical to the centralized helper's. Re-run on the
SAME corpus before Phase 5 (comparison cohort); zero collisions required.

Usage:
  .venv/bin/python scripts/cohort_slug_collision_guard.py \
      --corpus-root ~/Obsidian/Vault-in-place-test-run \
      --out benchmark/guards/task115-gate0-cohort-slug-collisions.json

Exit codes: 0 = zero collisions and no underivable stems;
            1 = collisions and/or underivable stems found (report printed).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from common.paths import slugify, PathError

SUMMARY_PREFIX = "summary-"
# 120 (MAX_SLUG_LEN) − len("summary-") — the stem budget so the full slug
# never exceeds the slug length cap.
STEM_BUDGET = 112

ALGORITHM_VERSION = "expected-summary-slug/1.0"
ALGORITHM_DESC = (
    "Path(source_id).stem → common.paths.slugify → 112-char stem budget "
    "(trailing-hyphen rstrip) → 'summary-' prefix"
)


def expected_summary_slug(source_id: str) -> str:
    """Spec-pinned derivation (blueprint Task 1.4). Raises PathError on
    empty / non-ASCII-only normalization (underivable stem)."""
    normalized = slugify(Path(source_id).stem)
    if len(normalized) > STEM_BUDGET:
        normalized = normalized[:STEM_BUDGET].rstrip("-")
    return SUMMARY_PREFIX + normalized


def _corpus_fingerprint(files: list[Path], root: Path) -> str:
    """Same construction as orchestrator._corpus_fingerprint: sha256 of the
    sorted {source_id: content_hash} mapping, so the guard report's
    fingerprint is directly comparable to the cohort run header's."""
    mapping = {}
    for f in files:
        source_id = f.relative_to(root).as_posix()
        mapping[source_id] = hashlib.sha256(f.read_bytes()).hexdigest()
    payload = json.dumps(sorted(mapping.items())).encode()
    return hashlib.sha256(payload).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--corpus-root", type=Path, required=True,
                    help="Vault/corpus root walked for .md sources (read-only).")
    ap.add_argument("--exclude", action="append", default=["KDB/"],
                    help="Relative dir prefixes to exclude (default: KDB/).")
    ap.add_argument("--out", type=Path, default=None,
                    help="Persist the JSON report here (default: stdout only).")
    args = ap.parse_args()

    root = args.corpus_root.expanduser().resolve()
    if not root.is_dir():
        print(f"ERROR: corpus root not found: {root}", file=sys.stderr)
        return 2

    files = sorted(
        p for p in root.rglob("*.md")
        if not any(p.relative_to(root).as_posix().startswith(ex) for ex in args.exclude)
    )

    sources: list[dict] = []
    underivable: list[dict] = []
    groups: dict[str, list[str]] = {}
    for f in files:
        source_id = f.relative_to(root).as_posix()
        try:
            key = expected_summary_slug(source_id)
        except PathError as e:
            underivable.append({"source_id": source_id, "error": str(e)})
            continue
        sources.append({"source_id": source_id, "expected_summary_slug": key})
        groups.setdefault(key, []).append(source_id)

    collisions = [
        {"expected_summary_slug": key, "source_ids": sorted(ids)}
        for key, ids in sorted(groups.items())
        if len(ids) > 1
    ]

    ok = not collisions and not underivable
    report = {
        "tool": "scripts/cohort_slug_collision_guard.py",
        "algorithm_version": ALGORITHM_VERSION,
        "algorithm": ALGORITHM_DESC,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "corpus_root": str(root),
        "excludes": args.exclude,
        "source_count": len(files),
        "corpus_fingerprint": _corpus_fingerprint(files, root),
        "collision_count": len(collisions),
        "collision_groups": collisions,
        "underivable_count": len(underivable),
        "underivable": underivable,
        "sources": sources,
        "verdict": (
            "ZERO COLLISIONS — cohort may fire"
            if ok
            else "STOP — resolve collisions/underivable stems before firing"
        ),
    }

    text = json.dumps(report, indent=2, ensure_ascii=False)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
        print(f"report persisted → {args.out}")

    print(f"corpus: {root} ({len(files)} sources, "
          f"fingerprint {report['corpus_fingerprint'][:16]}…)")
    print(f"derived keys: {len(groups)} distinct expected_summary_slug values")
    print(f"collisions: {len(collisions)} · underivable stems: {len(underivable)}")
    for c in collisions:
        print(f"  COLLISION {c['expected_summary_slug']}: {c['source_ids']}")
    for u in underivable:
        print(f"  UNDERIVABLE {u['source_id']}: {u['error']}")
    print(report["verdict"])
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

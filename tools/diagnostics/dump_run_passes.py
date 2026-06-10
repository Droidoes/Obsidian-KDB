#!/usr/bin/env python3
"""Dump Pass-1 and Pass-2 results for one orchestrate run into two readable
markdown files, for domain-coverage diagnosis.

Pass-1 source: per-source sidecars under <vault>/KDB/state/runs/<run_id>/pass1/*.md.json
               (covers ALL scanned sources incl. noise — 36 for run-3).
Pass-2 source: <vault>/KDB/state/compile_result.json compiled_sources[] (the
               SIGNAL sources that reached compile — 29 for run-3). Each page
               carries its own raw `domain`/`sub_domain` (pre-normalization).

Usage:
  python3 tools/diagnostics/dump_run_passes.py \
      --vault ~/Obsidian/Vault-in-place-test-run \
      --run 2026-05-30T15-53-39_EDT \
      --out-dir tools/diagnostics
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def load_pass1(run_dir: Path) -> list[dict]:
    """One record per scanned source from the pass1/ sidecars."""
    recs = []
    for f in sorted((run_dir / "pass1").glob("*.md.json")):
        d = json.loads(f.read_text())
        env = d.get("parsed_envelope") or {}
        recs.append(
            {
                "source_id": d.get("source_id"),
                "outcome": d.get("outcome"),
                "kdb_signal": env.get("kdb_signal"),
                "domain": env.get("domain"),
                "source_type": env.get("source_type"),
                "author": env.get("author"),
                "confidence": env.get("confidence"),
                "key_themes": env.get("key_themes") or [],
                "entity_search_keys": env.get("entity_search_keys") or [],
                "summary": env.get("summary"),
                "reject_reason": env.get("reject_reason"),
            }
        )
    return recs


def load_pass2(compile_result: Path) -> tuple[str, list[dict]]:
    d = json.loads(compile_result.read_text())
    return d.get("run_id"), d.get("compiled_sources", [])


def write_pass1(recs: list[dict], pass1_by_id: dict, out: Path) -> None:
    lines = ["# Pass-1 results — run 2026-05-30T15-53-39_EDT", ""]
    lines.append(f"Total scanned sources: **{len(recs)}**")
    sig = sum(1 for r in recs if r["kdb_signal"] == "signal")
    lines.append(f"signal: {sig} · noise: {len(recs) - sig}")
    dom_counts = Counter(r["domain"] for r in recs if r["kdb_signal"] == "signal")
    lines.append("")
    lines.append("Pass-1 SOURCE domain distribution (signal sources only):")
    for dom, n in dom_counts.most_common():
        lines.append(f"  - `{dom}`: {n}")
    lines.append("")
    lines.append("> Note: Pass-1 `domain` is a per-SOURCE classification written to the")
    lines.append("> `Source.domain` property. It is SEPARATE from Pass-2 per-ENTITY-page")
    lines.append("> `domain` (which drives Domain nodes + BELONGS_TO edges). Compare with")
    lines.append("> pass-2-run-3.md to see the disconnect.")
    lines.append("")
    lines.append("---")
    lines.append("")
    for r in recs:
        lines.append(f"## {r['source_id']}")
        lines.append("")
        lines.append(f"- **kdb_signal**: `{r['kdb_signal']}`  ·  outcome: `{r['outcome']}`  ·  confidence: {r['confidence']}")
        lines.append(f"- **domain**: `{r['domain']}`")
        lines.append(f"- **source_type**: `{r['source_type']}`  ·  author: {r['author']!r}")
        if r["reject_reason"]:
            lines.append(f"- reject_reason: {r['reject_reason']}")
        lines.append(f"- **key_themes**: {r['key_themes']}")
        lines.append(f"- **entity_search_keys**: {r['entity_search_keys']}")
        lines.append(f"- summary: {r['summary']}")
        lines.append("")
    out.write_text("\n".join(lines))


def write_pass2(run_id: str, sources: list[dict], pass1_by_id: dict, out: Path) -> None:
    lines = [f"# Pass-2 results — run {run_id}", ""]
    lines.append(f"Compiled (signal) sources: **{len(sources)}**")

    # Aggregate page-type + domain stats.
    ptypes = Counter()
    raw_dom = Counter()
    concept_total = concept_with_dom = 0
    for s in sources:
        for p in s["pages"]:
            pt = p.get("page_type")
            ptypes[pt] += 1
            raw_dom[p.get("domain")] += 1
            if pt == "concept":
                concept_total += 1
                if p.get("domain"):
                    concept_with_dom += 1
    lines.append("")
    lines.append(f"Page types: {dict(ptypes)}")
    lines.append(f"**Concept pages with a domain: {concept_with_dom}/{concept_total} "
                 f"({100*concept_with_dom//max(concept_total,1)}%)**")
    lines.append("")
    lines.append("Raw page-level `domain` values (pre-normalization, all page types):")
    for dom, n in raw_dom.most_common():
        lines.append(f"  - `{dom}`: {n}")
    lines.append("")
    lines.append("> Domain nodes + BELONGS_TO edges are created ONLY from CANONICAL")
    lines.append("> pages with a non-null `domain` (summary/alias pages are skipped by")
    lines.append("> design). `[P1 domain=...]` shows that source's Pass-1 classification")
    lines.append("> for adjacency — note where P1 says e.g. value-investing but every")
    lines.append("> Pass-2 page below emits domain=None.")
    lines.append("")
    lines.append("---")
    lines.append("")
    for s in sources:
        sid = s["source_id"]
        p1 = pass1_by_id.get(sid, {})
        lines.append(f"## {sid}")
        lines.append("")
        lines.append(f"`[P1 domain={p1.get('domain')}]`  ·  {len(s['pages'])} pages")
        lines.append("")
        lines.append("| page_type | slug | domain | sub_domain | status |")
        lines.append("|---|---|---|---|---|")
        for p in s["pages"]:
            lines.append(
                f"| {p.get('page_type')} | `{p.get('slug')}` | "
                f"**{p.get('domain')}** | {p.get('sub_domain')} | {p.get('status')} |"
            )
        lines.append("")
    out.write_text("\n".join(lines))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", required=True)
    ap.add_argument("--run", required=True)
    ap.add_argument("--out-dir", default="tools/diagnostics")
    args = ap.parse_args()

    vault = Path(args.vault).expanduser()
    run_dir = vault / "KDB" / "state" / "runs" / args.run
    compile_result = vault / "KDB" / "state" / "compile_result.json"
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    pass1 = load_pass1(run_dir)
    pass1_by_id = {r["source_id"]: r for r in pass1}
    run_id, pass2 = load_pass2(compile_result)

    if run_id != args.run:
        raise SystemExit(
            f"REFUSING: compile_result.json run_id={run_id!r} != requested "
            f"--run {args.run!r}. State file may be from a later run."
        )

    write_pass1(pass1, pass1_by_id, out_dir / "pass-1-run-3.md")
    write_pass2(run_id, pass2, pass1_by_id, out_dir / "pass-2-run-3.md")
    print(f"Wrote {out_dir/'pass-1-run-3.md'} ({len(pass1)} sources)")
    print(f"Wrote {out_dir/'pass-2-run-3.md'} ({len(pass2)} sources)")


if __name__ == "__main__":
    main()

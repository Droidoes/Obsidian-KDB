"""Task #90 Phase E acceptance tests.

E.1 — Live smoke (Joseph fires): Pass-1 enrichment + plan-time context
    construction. Asserts ContextSnapshot.pages contains entities seeded
    in the GraphDB whose slugs the LLM emits in entity_search_keys.
    Verifies the State B structured path end-to-end with a real LLM.

E.2 — Non-live: Pass-2 (compile prompt-builder) gracefully handles
    ContextSnapshot.pages=[] from State C. Closes Deepseek F-5's
    unverified-assumption concern at the plumbing layer without burning
    API credits.

Run E.1 (Joseph fires — costs ~$0.01 for one Pass-1 call):
    python3 -m pytest kdb_compiler/tests/test_t2_end_to_end_pass1_path.py -v -m live -s

Run E.2 (in normal suite):
    python3 -m pytest kdb_compiler/tests/test_t2_end_to_end_pass1_path.py::test_pass2_plumbing_on_empty_context_state_c
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from graphdb_kdb.graphdb import GraphDB
from kdb_compiler import planner
from kdb_compiler.ingestion.enrich import enrich_one
from kdb_compiler.prompt_builder import build_prompt
from kdb_compiler.types import ContextSnapshot


# ─── E.1 — Live smoke (Joseph fires) ───────────────────────────────────────

@pytest.mark.live
@pytest.mark.uses_real_graph_context
@pytest.mark.skipif(
    not os.getenv("DEEPSEEK_API_KEY"),
    reason="No DEEPSEEK_API_KEY in env",
)
def test_t2_structured_path_live(tmp_path: Path) -> None:
    """E.1 — Live verification of State B structured path end-to-end.

    1. Seed GraphDB with entities whose slugs Pass-1 is highly likely to
       emit in entity_search_keys for a value-investing essay.
    2. Fire enrich_one (Pass-1) on a synthetic source about value investing.
    3. Verify entity_search_keys was emitted non-empty.
    4. Fire planner.plan(...) → builds CompileJob with ContextSnapshot.
    5. Assert ContextSnapshot.pages contains at least one of the seeded
       entities (proving the State B path resolved keys → T2 hits).
    """
    # ─── Vault layout ──────────────────────────────────────────────────────
    vault_root = tmp_path / "vault"
    raw_dir = vault_root / "KDB" / "raw"
    state_dir = vault_root / "KDB" / "state"
    raw_dir.mkdir(parents=True, exist_ok=True)
    state_dir.mkdir(parents=True, exist_ok=True)

    # Seed entities the LLM should easily produce keys for.
    seed_slugs = ["value-investing", "warren-buffett", "margin-of-safety", "intrinsic-value"]
    seed_graph_dir = Path(os.environ["KDB_GRAPH_PATH"])
    with GraphDB(seed_graph_dir) as g:
        for slug in seed_slugs:
            g.conn.execute(
                "CREATE (e:Entity {slug: $s, title: $t, page_type: 'concept', "
                "status: 'active', confidence: 'high', canonical_id: NULL, "
                "created_at: '2026-05-27', updated_at: '2026-05-27', "
                "first_run_id: 't2-e1', last_run_id: 't2-e1'})",
                {"s": slug, "t": slug.replace("-", " ").title()},
            )

    # Source designed to produce predictable entity_search_keys.
    source_path = raw_dir / "value-investing-essay.md"
    source_id = "KDB/raw/value-investing-essay.md"
    source_path.write_text(
        "# Value Investing — The Buffett Approach\n\n"
        "Warren Buffett's approach to value investing rests on a deceptively "
        "simple principle: buy quality businesses at a substantial discount "
        "to their intrinsic value — what Benjamin Graham called the 'margin "
        "of safety'. This margin protects the investor against both bad "
        "judgment and bad luck.\n",
        encoding="utf-8",
    )

    # ─── Pass-1: enrich source on disk ─────────────────────────────────────
    runs_root = state_dir / "ingest_runs"
    enrich_result = enrich_one(
        source_path=source_path,
        source_id=source_id,
        runs_root=runs_root,
        run_id="t2-e1-test",
        provider="deepseek",
        model="deepseek-v4-flash",
    )
    assert enrich_result.outcome in ("enriched", "enriched_force_overridden"), (
        f"Pass-1 failed: outcome={enrich_result.outcome!r}, "
        f"error={enrich_result.error!r}"
    )
    envelope = enrich_result.parsed_envelope
    assert envelope is not None, "Pass-1 returned None envelope"

    emitted_keys = list(envelope.get("entity_search_keys") or [])
    assert emitted_keys, (
        "Pass-1 emitted entity_search_keys=[] — State C path; this test "
        "requires State B. Re-fire or pick a richer source body."
    )
    sys.stderr.write(f"\n[E.1] Pass-1 emitted entity_search_keys: {emitted_keys}\n")

    # ─── Plan-time: build CompileJob with ContextSnapshot ──────────────────
    # Bypass autouse stub_planner_graph_context via the uses_real_graph_context
    # marker; planner reads KDB_GRAPH_PATH and opens the seeded test graph.
    scan = {
        "to_compile": [source_id],
        "files": [{"path": source_id, "is_binary": False}],
    }
    jobs = planner.plan(vault_root, scan=scan, state_root=state_dir)
    assert len(jobs) == 1, f"expected 1 job, got {len(jobs)}"
    snapshot = jobs[0].context_snapshot

    page_slugs = {p.slug for p in snapshot.pages}
    seed_hits = page_slugs & set(seed_slugs)
    sys.stderr.write(
        f"[E.1] ContextSnapshot pages={len(snapshot.pages)} slugs={sorted(page_slugs)}\n"
        f"[E.1] Seed entity hits: {sorted(seed_hits)} (out of {seed_slugs})\n"
    )

    assert seed_hits, (
        f"State B structured path produced no T2 hits despite "
        f"entity_search_keys={emitted_keys} and seeded entities={seed_slugs}. "
        f"ContextSnapshot.pages slugs={sorted(page_slugs)}. "
        "Either alias resolution failed or LLM emitted slugs unrelated "
        "to seeded entities."
    )


# ─── E.2 — Non-live: empty-context prompt plumbing (Deepseek F-5) ──────────


def _write_vault_with_stub_system_prompt(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    (vault / "KDB").mkdir(parents=True, exist_ok=True)
    (vault / "KDB" / "KDB-Compiler-System-Prompt.md").write_text(
        "# KDB invariants (test stub)\n", encoding="utf-8"
    )
    return vault


def test_pass2_plumbing_on_empty_context_state_c(tmp_path: Path) -> None:
    """E.2 — Verify Pass-2 prompt construction gracefully handles
    ContextSnapshot.pages=[] (the State C production state).

    Deepseek F-5: blueprint v0.1 assumed Pass-2 handles empty context but
    never verified. This test exercises build_prompt directly to confirm:
    (a) no exception, (b) prompt assembled, (c) the EXISTING CONTEXT block
    renders as a valid JSON envelope with empty pages array. No LLM cost.
    """
    vault_root = _write_vault_with_stub_system_prompt(tmp_path)
    empty_snapshot = ContextSnapshot(source_id="KDB/raw/stub.md", pages=[])

    built = build_prompt(
        vault_root=vault_root,
        source_name="stub.md",
        source_text="A trivial note with no substantive content.",
        context_snapshot=empty_snapshot,
    )

    # (a) Prompt assembly returned a BuiltPrompt — no exception.
    assert built.system, "system prompt empty"
    assert built.user, "user prompt empty"

    # (b) The EXISTING CONTEXT block is present and renders empty pages.
    assert "## EXISTING CONTEXT (graph snapshot)" in built.user
    # Extract the JSON block between EXISTING CONTEXT and the next "## " header.
    context_section_start = built.user.index("## EXISTING CONTEXT")
    next_section_start = built.user.index("## ", context_section_start + 5)
    context_section = built.user[context_section_start:next_section_start]
    # Parse the JSON inside the section to verify it's well-formed and pages=[].
    json_start = context_section.index("{")
    json_end = context_section.rindex("}") + 1
    context_doc = json.loads(context_section[json_start:json_end])
    assert context_doc["source_id"] == "KDB/raw/stub.md"
    assert context_doc["pages"] == [], (
        f"Expected empty pages array, got: {context_doc['pages']!r}"
    )

    # (c) Source text + schema + exemplar sections all rendered.
    assert "## SOURCE CONTENT" in built.user
    assert "## RESPONSE SCHEMA" in built.user
    assert "## EXAMPLE RESPONSE" in built.user

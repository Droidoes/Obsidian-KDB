"""test_pass1_end_to_end — Full Pass-1 + compile integration acceptance test.

Task #89 §10.5 "tunnel ends meet" check (v0.2.2):

    Pass-1 (enrich_one) writes sectionalized YAML frontmatter to disk.
    Compile pipeline reads frontmatter → populates GraphDB Source node.

Five contract points (v0.2.2 reality — D-89-17 amended by D-89-19/D-89-20):
    C1: Source.domain populated from Pass-1 frontmatter (D-89-17 USE-directly).
    C2: Source.author populated from Pass-1 frontmatter (when envelope.author
        is non-None).
    C3: Source.source_type matches Pass-1 envelope (Bug #1 fix verifies the
        ingestor._write_source_meta SET on source_type when present, replacing
        the first-create default 'obsidian-kdb-raw').
    C4: Source.summary = Pass-1 verbatim summary + mechanical append of
        key_themes (D-89-19). Contains both the original sentence AND a
        ". Themes: <theme>, <theme>" tail when envelope.key_themes is non-empty.
        Specifically NOT just verbatim Pass-1 summary (Bug #2 dissolved by
        D-89-19's mechanical-append landing).
    C5: Frontmatter on disk contains entity_search_keys (D-89-20 new field) and
        does NOT contain key_entities (D-89-20 dropped field).

Run command (user fires — costs one API call). The DEEPSEEK_API_KEY is
auto-loaded from the repo-root `.env` via `python-dotenv` when any
`kdb_compiler` module is imported, so no CLI prefix is needed:
    python3 -m pytest kdb_compiler/tests/test_pass1_end_to_end.py -v -m live -s

@pytest.mark.uses_real_graph_context is set so the autouse
`_stub_planner_graph_context` fixture is bypassed, allowing the planner to
open the per-test isolated graph (which is empty but accessible, not None).
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from kdb_compiler.ingestion.enrich import enrich_one
from kdb_compiler import kdb_compile
from graphdb_kdb.graphdb import GraphDB


@pytest.mark.live
@pytest.mark.uses_real_graph_context
@pytest.mark.skipif(
    not os.getenv("DEEPSEEK_API_KEY"),
    reason="No DEEPSEEK_API_KEY in env",
)
def test_tunnel_ends_meet(tmp_path: Path) -> None:
    """Per Task #89 §10.5 acceptance criteria (v0.2.2) — 'tunnel ends meet'
    integration check.

    Fires two real LLM calls: one Pass-1 enrich_one call + one compile call.
    Asserts all five §10.5 contract points via collect-all-failures pattern
    (does not short-circuit on first failure, so one run yields full signal).
    """
    # ─── vault layout ────────────────────────────────────────────────────────
    vault_root = tmp_path / "vault"
    raw_dir = vault_root / "KDB" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    # Copy or stub the system prompt (compile Stage 2 loads it).
    sys_prompt_dest = vault_root / "KDB" / "KDB-Compiler-System-Prompt.md"
    real_sys_prompt = Path.home() / "Obsidian" / "KDB" / "KDB-Compiler-System-Prompt.md"
    if real_sys_prompt.exists():
        shutil.copy(real_sys_prompt, sys_prompt_dest)
    else:
        sys_prompt_dest.write_text("# KDB invariants (test stub)\n", encoding="utf-8")

    # Seed the per-test isolated GraphDB with one entity so the planner's
    # `_graph_conn_or_raise` check passes (requires graph dir to exist AND
    # have >0 entities). The seed entity is unrelated to the test source
    # and does not affect any C1–C5 assertion.
    seed_graph_dir = Path(os.environ["KDB_GRAPH_PATH"])
    with GraphDB(seed_graph_dir) as g:
        g.conn.execute(
            "CREATE (e:Entity {slug: 'e2e-seed', title: 'E2E Seed', "
            "page_type: 'concept', status: 'active', confidence: 'low', "
            "canonical_id: NULL, created_at: '2026-05-26', updated_at: '2026-05-26', "
            "first_run_id: 'e2e-seed', last_run_id: 'e2e-seed'})"
        )

    # Source file with rich value-investing content so Pass-1 emits
    # non-trivial domain / key_themes / entity_search_keys.
    source_path = raw_dir / "buffett-essay.md"
    source_id = "KDB/raw/buffett-essay.md"
    source_path.write_text(
        "# Buffett on Margin of Safety\n\n"
        "Warren Buffett, the chairman of Berkshire Hathaway, emphasizes buying "
        "securities at a substantial discount to their intrinsic value — a "
        "principle he calls 'margin of safety'. Key examples include See's "
        "Candies, Coca-Cola, and American Express. Buffett attributes this "
        "philosophy to Benjamin Graham and cites it as the foundation of "
        "long-term compounding of capital.\n",
        encoding="utf-8",
    )

    # ─── Phase 1: Pass-1 enrichment ──────────────────────────────────────────
    runs_root = vault_root / "KDB" / "state" / "ingest_runs"
    enrich_result = enrich_one(
        source_path=source_path,
        source_id=source_id,
        runs_root=runs_root,
        run_id="e2e-test",
        provider="deepseek",
        model="deepseek-v4-flash",
    )

    assert enrich_result.outcome in (
        "enriched", "enriched_force_overridden"
    ), f"Pass-1 failed with outcome={enrich_result.outcome!r}, error={enrich_result.error!r}"

    # Extract what Pass-1 wrote to the envelope for later assertions.
    envelope = enrich_result.parsed_envelope
    assert envelope is not None, "Pass-1 returned None envelope on non-failure outcome"

    # Verify frontmatter was actually written to disk.
    enriched_text = source_path.read_text(encoding="utf-8")
    assert enriched_text.startswith("---\n"), "Pass-1 did not embed YAML frontmatter"
    assert "kdb_signal:" in enriched_text, "Pass-1 frontmatter missing kdb_signal"
    assert "# Buffett on Margin of Safety" in enriched_text, (
        "Pass-1 stripped the body"
    )

    pass1_summary = envelope.get("summary", "")
    pass1_domain = envelope.get("domain", "")
    pass1_author = envelope.get("author")
    pass1_source_type = envelope.get("source_type", "")
    pass1_key_themes: list[str] = list(envelope.get("key_themes") or [])
    pass1_entity_search_keys: list[str] = list(envelope.get("entity_search_keys") or [])

    # ─── Phase 2: compile pipeline ───────────────────────────────────────────
    compile_result = kdb_compile.compile(
        vault_root,
        provider="deepseek",
        model="deepseek-v4-flash",
    )

    assert compile_result.success, (
        f"compile() failed: {compile_result.errors}"
    )

    # ─── Phase 3: graph + frontmatter assertions ─────────────────────────────
    graph_dir = Path(os.environ["KDB_GRAPH_PATH"])
    failures: list[str] = []

    with GraphDB(graph_dir) as gdb:
        src = gdb.get_source(source_id)

        if src is None:
            pytest.fail(
                f"Source node not found in GraphDB for source_id={source_id!r}. "
                "Compile may have succeeded but graph_sync failed, or source_id "
                "format mismatch between scan and ingestor."
            )

        # C1: domain populated from frontmatter (D-89-17)
        if not src.domain:
            failures.append(
                f"C1 domain: Source.domain is empty; expected non-empty from "
                f"Pass-1 frontmatter (envelope.domain={pass1_domain!r})"
            )
        elif src.domain != pass1_domain:
            failures.append(
                f"C1 domain: Source.domain={src.domain!r} != "
                f"envelope.domain={pass1_domain!r} (not normalized? check ingestor)"
            )

        # C2: author populated (may be None if Pass-1 returned None)
        if pass1_author is not None and src.author != pass1_author:
            failures.append(
                f"C2 author: Source.author={src.author!r} != "
                f"envelope.author={pass1_author!r}"
            )

        # C3: source_type — per D-89-17 + Bug #1 fix (v0.2.2), the
        # Source.source_type should reflect the Pass-1 frontmatter value, NOT
        # the first-create default 'obsidian-kdb-raw'.
        if src.source_type != pass1_source_type:
            failures.append(
                f"C3 source_type: Source.source_type={src.source_type!r} != "
                f"envelope.source_type={pass1_source_type!r}. "
                "Bug #1 fix (graphdb_kdb/ingestor.py:_write_source_meta) "
                "should SET source_type from source_meta when present."
            )

        # C4: Source.summary = Pass-1 verbatim + ". Themes: ..." mechanical
        # append (D-89-19). Should contain BOTH the verbatim Pass-1 summary
        # (modulo a possible trailing period strip) AND a "Themes: " marker
        # when key_themes is non-empty.
        if not src.summary:
            failures.append(
                "C4 summary: Source.summary is empty/None; expected populated "
                "from Pass-1 frontmatter + mechanical themes append"
            )
        elif pass1_key_themes:
            # Verbatim Pass-1 summary core should appear in the persisted
            # Source.summary (modulo trailing-period rstrip).
            base = pass1_summary.rstrip(". ")
            if base and base not in src.summary:
                failures.append(
                    f"C4 summary base: Source.summary does not contain the "
                    f"Pass-1 verbatim summary base. "
                    f"src.summary={src.summary!r}; "
                    f"expected to contain {base!r}"
                )
            if "Themes:" not in src.summary:
                failures.append(
                    f"C4 summary themes: Source.summary missing 'Themes: ...' "
                    f"mechanical append (D-89-19). "
                    f"key_themes={pass1_key_themes!r}; "
                    f"src.summary={src.summary!r}"
                )
            # Each Pass-1 theme should appear in the appended portion.
            for theme in pass1_key_themes:
                if theme not in src.summary:
                    failures.append(
                        f"C4 summary themes: theme {theme!r} not found in "
                        f"src.summary={src.summary!r}"
                    )

        # C5: Frontmatter on disk contains entity_search_keys (D-89-20 added)
        # and does NOT contain key_entities (D-89-20 dropped).
        if "entity_search_keys:" not in enriched_text:
            failures.append(
                "C5 frontmatter: entity_search_keys field missing from "
                "on-disk frontmatter (D-89-20 expected field)."
            )
        if "key_entities:" in enriched_text:
            failures.append(
                "C5 frontmatter: key_entities still appears in on-disk "
                "frontmatter — D-89-20 dropped this field; producer should "
                "no longer emit it."
            )
        if not pass1_entity_search_keys:
            failures.append(
                "C5 envelope: Pass-1 returned empty entity_search_keys; "
                "expected ≤10 slug candidates given the rich source content."
            )

    # Report all collected failures as a single pytest.fail() for one-pass signal.
    if failures:
        pytest.fail(
            f"§10.5 contract violations ({len(failures)} of 5 checks failed):\n"
            + "\n".join(f"  [{i+1}] {msg}" for i, msg in enumerate(failures))
        )

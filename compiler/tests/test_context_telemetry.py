"""Tests for Task #122 P1 context telemetry — the two-product builder and the
golden prompt-identity pins.

The golden fixture (`tests/fixtures/context_golden_prompts/task122_golden_prompts.json`)
was captured from PRE-#122 code via build_context_snapshot → build_prompt
across the five blueprint paths (structured keys / explicit-empty / legacy /
layered / empty-graph). NEVER regenerate it from post-change code — the pin
asserts byte-identical prompt text + identical prompt hash after the builder
change.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from kdb_graph.graphdb import GraphDB
from common.source_io import SourceFrontmatter
from common.types import KeyOutcome, TierRecord
from compiler.context_loader import T2Mode, build_context_snapshot
from compiler.prompt_builder import build_prompt

_FIXTURE_PATH = (Path(__file__).parents[2] / "tests" / "fixtures"
                 / "context_golden_prompts" / "task122_golden_prompts.json")
_FIXTURE = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))

SOURCE_ID = _FIXTURE["source_id"]
SOURCE_NAME = _FIXTURE["source_name"]
SOURCE_META = _FIXTURE["source_meta"]


def _fm(keys, domain: str | None = "value-investing") -> SourceFrontmatter:
    return SourceFrontmatter(
        kdb_signal="signal", domain=domain, source_type="essay",
        author="Fixture Author", summary="A golden fixture summary.",
        key_themes=[], entity_search_keys=keys,
    )


def _seed_golden_graph(conn) -> None:
    """The EXACT graph the golden fixture was captured against — do not change
    (the fixture's frozen bytes depend on this topology)."""
    for slug, title, ptype, ci in [
        ("value-investing", "Value Investing", "concept", None),
        ("margin-of-safety", "Margin of Safety", "concept", None),
        ("warren-buffett", "Warren Buffett", "concept", None),
        ("wb", "WB", "concept", "warren-buffett"),
        ("random-concept", "Random Concept", "concept", None),
    ]:
        conn.execute(
            "CREATE (e:Entity {slug: $s, title: $t, page_type: $pt, "
            "status: 'active', confidence: 'medium', canonical_id: $ci, "
            "created_at: '2026-01-01', updated_at: '2026-01-01', "
            "first_run_id: 'r0', last_run_id: 'r0'})",
            {"s": slug, "t": title, "pt": ptype, "ci": ci},
        )
    conn.execute(
        "CREATE (d:Domain {name: 'value-investing', created_at: '2026-01-01', "
        "first_run_id: 'r0'})"
    )
    for slug in ["value-investing", "margin-of-safety", "warren-buffett", "wb",
                 "random-concept"]:
        conn.execute(
            "MATCH (e:Entity {slug: $s}), (d:Domain {name: 'value-investing'}) "
            "CREATE (e)-[:BELONGS_TO {run_id: 'r0'}]->(d)", {"s": slug})
    conn.execute(
        "CREATE (s:Source {source_id: $sid, source_type: 'raw', "
        "canonical_path: $sid, status: 'active', file_type: 'markdown', "
        "hash: 'sha256:aaa', size_bytes: 100, "
        "first_seen_at: '2026-01-01', last_seen_at: '2026-01-01', "
        "last_ingested_at: '2026-01-01', ingest_state: 'compiled', "
        "ingest_count: 1, last_run_id: 'r0', moved_to: ''})",
        {"sid": SOURCE_ID},
    )
    conn.execute(
        "MATCH (s:Source {source_id: $sid}), (e:Entity {slug: 'value-investing'}) "
        "CREATE (s)-[:SUPPORTS {run_id: 'r0'}]->(e)", {"sid": SOURCE_ID})
    for f, t in [
        ("margin-of-safety", "value-investing"),
        ("warren-buffett", "margin-of-safety"),
        ("margin-of-safety", "random-concept"),
    ]:
        conn.execute(
            "MATCH (a:Entity {slug: $f}), (b:Entity {slug: $t}) "
            "CREATE (a)-[:LINKS_TO {run_id: 'r0'}]->(b)", {"f": f, "t": t})


@pytest.fixture
def golden_gdb(tmp_path: Path):
    with GraphDB(tmp_path / "golden-graph") as g:
        _seed_golden_graph(g.conn)
        yield g


def _rebuilt_prompt(conn, entry: dict):
    """Rebuild the prompt through the POST-change builder (.snapshot product)."""
    result = build_context_snapshot(
        conn, source_id=SOURCE_ID, source_text=entry["body"],
        frontmatter=_fm(entry["keys"]), mode=T2Mode(entry["mode"]),
    )
    return build_prompt(
        source_name=SOURCE_NAME, source_text=entry["body"],
        context_snapshot=result.snapshot, source_meta=SOURCE_META,
    )


def _prompt_hash(prompt) -> str:
    digest = hashlib.sha256(
        (prompt.system + "\n\n" + prompt.user).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


# ---------- golden prompt identity (frozen from PRE-#122 code) ----------

@pytest.mark.parametrize("path_name", ["structured_keys", "explicit_empty", "legacy", "layered"])
def test_golden_prompt_identity(golden_gdb, path_name):
    """Byte-identical prompt text + identical prompt hash post-change."""
    entry = _FIXTURE["paths"][path_name]
    prompt = _rebuilt_prompt(golden_gdb.conn, entry)
    assert prompt.user == entry["user"]
    assert _prompt_hash(prompt) == entry["prompt_hash"]


def test_golden_prompt_identity_empty_graph(tmp_path):
    entry = _FIXTURE["paths"]["empty_graph"]
    with GraphDB(tmp_path / "empty-graph") as g:
        result = build_context_snapshot(
            g.conn, source_id=SOURCE_ID, source_text=entry["body"],
            frontmatter=_fm(entry["keys"]), mode=T2Mode(entry["mode"]),
        )
    prompt = build_prompt(
        source_name=SOURCE_NAME, source_text=entry["body"],
        context_snapshot=result.snapshot, source_meta=SOURCE_META,
    )
    assert prompt.user == entry["user"]
    assert _prompt_hash(prompt) == entry["prompt_hash"]


# ---------- dispositions (structured_keys path) ----------

def test_telemetry_structured_keys_full(golden_gdb):
    result = build_context_snapshot(
        golden_gdb.conn, source_id=SOURCE_ID,
        source_text="Notes on partnership letters and the circle of competence idea.",
        frontmatter=_fm(["margin-of-safety", "wb", "nonexistent-key"]),
        mode=T2Mode.STRUCTURED,
    )
    t = result.telemetry
    assert t.source_id == SOURCE_ID
    assert t.configured_t2_mode == "structured"
    assert t.effective_t2_strategy == "structured_keys"
    assert t.keys_emitted == ["margin-of-safety", "wb", "nonexistent-key"]
    assert t.key_outcomes == [
        KeyOutcome("margin-of-safety", "resolved_t2_seed", "margin-of-safety", "r0"),
        # wb resolves via canonical_id; the stamp is the TARGET's first_run_id
        KeyOutcome("wb", "resolved_t2_seed", "warren-buffett", "r0"),
        KeyOutcome("nonexistent-key", "unresolved", None, None),
    ]
    # tiers: T1 = {value-investing} (SUPPORTS), T2 = {margin-of-safety,
    # warren-buffett}, T3 = {random-concept}; page_cap=50 → all delivered.
    assert t.t1 == TierRecord(1, 1, ["value-investing"])
    assert t.t2 == TierRecord(2, 2, ["margin-of-safety", "warren-buffett"])
    assert t.t3 == TierRecord(1, 1, ["random-concept"])
    assert t.candidate_universe_size == 5          # domain-scoped pool, pre-T1-exclusion
    assert t.domain_scope == "value-investing"
    assert t.cold_start is False
    assert t.max_hops == 1
    assert t.page_cap == 50


def test_disposition_resolved_already_t1(golden_gdb):
    result = build_context_snapshot(
        golden_gdb.conn, source_id=SOURCE_ID, source_text="x",
        frontmatter=_fm(["value-investing"]), mode=T2Mode.STRUCTURED,
    )
    assert result.telemetry.key_outcomes == [
        KeyOutcome("value-investing", "resolved_already_t1", "value-investing", "r0"),
    ]


def test_disposition_resolved_duplicate_seed(golden_gdb):
    """Two keys resolving to the SAME canonical: first seeds, second duplicates."""
    result = build_context_snapshot(
        golden_gdb.conn, source_id=SOURCE_ID, source_text="x",
        frontmatter=_fm(["wb", "warren-buffett"]), mode=T2Mode.STRUCTURED,
    )
    assert result.telemetry.key_outcomes == [
        KeyOutcome("wb", "resolved_t2_seed", "warren-buffett", "r0"),
        KeyOutcome("warren-buffett", "resolved_duplicate_seed", "warren-buffett", "r0"),
    ]


def test_disposition_resolved_out_of_scope(tmp_path: Path):
    """A key resolving OUTSIDE the domain-scoped pool (and not in T1) →
    resolved_out_of_scope."""
    with GraphDB(tmp_path / "scope-graph") as g:
        conn = g.conn
        for slug, dom in [("vi-1", "value-investing"), ("ai-1", "ai-ml")]:
            conn.execute(
                "CREATE (e:Entity {slug: $s, title: $s, page_type: 'concept', "
                "status: 'active', confidence: 'medium', "
                "created_at: '2026-01-01', updated_at: '2026-01-01', "
                "first_run_id: 'r0', last_run_id: 'r0'})",
                {"s": slug},
            )
            conn.execute(
                "CREATE (d:Domain {name: $d, created_at: '2026-01-01', "
                "first_run_id: 'r0'})",
                {"d": dom},
            )
            conn.execute(
                "MATCH (e:Entity {slug: $s}), (d:Domain {name: $d}) "
                "CREATE (e)-[:BELONGS_TO {run_id: 'r0'}]->(d)", {"s": slug, "d": dom})
        result = build_context_snapshot(
            conn, source_id="src-scope", source_text="x",
            frontmatter=_fm(["vi-1", "ai-1"]), mode=T2Mode.STRUCTURED,
        )
    t = result.telemetry
    assert t.key_outcomes == [
        KeyOutcome("vi-1", "resolved_t2_seed", "vi-1", "r0"),
        KeyOutcome("ai-1", "resolved_out_of_scope", "ai-1", "r0"),
    ]
    assert t.candidate_universe_size == 1          # pool = value-investing only


def test_disposition_precedence_t1_before_out_of_scope(golden_gdb):
    """A T1 canonical is also ∉ (pool − t1) — already_t1 must win the order."""
    # "value-investing" is T1; without the precedence it would read out_of_scope.
    result = build_context_snapshot(
        golden_gdb.conn, source_id=SOURCE_ID, source_text="x",
        frontmatter=_fm(["value-investing", "nonexistent"]), mode=T2Mode.STRUCTURED,
    )
    assert [o.disposition for o in result.telemetry.key_outcomes] == [
        "resolved_already_t1", "unresolved",
    ]


# ---------- cap pressure ----------

def test_cap_pressure_t1_fills_cap_t2_delivered_zero(tmp_path: Path):
    """T1 fills the cap ⇒ a valid resolved_t2_seed outcome is recorded
    (dispositions are pre-cap) while t2.delivered == 0."""
    with GraphDB(tmp_path / "cap-graph") as g:
        conn = g.conn
        for slug in ["t1-a", "t1-b", "t1-c", "seed-1", "seed-2"]:
            conn.execute(
                "CREATE (e:Entity {slug: $s, title: $s, page_type: 'concept', "
                "status: 'active', confidence: 'medium', "
                "created_at: '2026-01-01', updated_at: '2026-01-01', "
                "first_run_id: 'r0', last_run_id: 'r0'})",
                {"s": slug},
            )
        conn.execute(
            "CREATE (s:Source {source_id: 'src-cap', source_type: 'raw', "
            "canonical_path: 'src-cap', status: 'active', file_type: 'markdown', "
            "hash: 'sha256:aaa', size_bytes: 100, "
            "first_seen_at: '2026-01-01', last_seen_at: '2026-01-01', "
            "last_ingested_at: '2026-01-01', ingest_state: 'compiled', "
            "ingest_count: 1, last_run_id: 'r0', moved_to: ''})"
        )
        for slug in ["t1-a", "t1-b", "t1-c"]:
            conn.execute(
                "MATCH (s:Source {source_id: 'src-cap'}), (e:Entity {slug: $s}) "
                "CREATE (s)-[:SUPPORTS {run_id: 'r0'}]->(e)", {"s": slug})
        result = build_context_snapshot(
            conn, source_id="src-cap", source_text="x",
            page_cap=3, frontmatter=_fm(["seed-1", "seed-2"], domain=None),
            mode=T2Mode.STRUCTURED,
        )
    t = result.telemetry
    assert t.key_outcomes == [
        KeyOutcome("seed-1", "resolved_t2_seed", "seed-1", "r0"),
        KeyOutcome("seed-2", "resolved_t2_seed", "seed-2", "r0"),
    ]
    assert t.t1.delivered == 3                      # T1 fills the cap
    assert t.t2.candidates == 2                     # pre-cap tier set intact
    assert t.t2.delivered == 0 and t.t2.slugs == []  # …but nothing delivered
    assert t.t3.delivered == 0


# ---------- effective strategies ----------

def test_strategy_explicit_empty(golden_gdb):
    result = build_context_snapshot(
        golden_gdb.conn, source_id=SOURCE_ID,
        source_text="The margin-of-safety idea anchors this essay.",
        frontmatter=_fm([]), mode=T2Mode.STRUCTURED,
    )
    t = result.telemetry
    assert t.effective_t2_strategy == "explicit_empty"
    assert t.keys_emitted == [] and t.key_outcomes == []
    assert t.t2.candidates == 0                     # State C honored


def test_strategy_legacy_regex_via_mode(golden_gdb):
    """LEGACY mode: frontmatter keys ignored — no emissions, no outcomes."""
    result = build_context_snapshot(
        golden_gdb.conn, source_id=SOURCE_ID,
        source_text="The margin-of-safety idea anchors this essay.",
        frontmatter=_fm(["wb"]), mode=T2Mode.LEGACY,
    )
    t = result.telemetry
    assert t.configured_t2_mode == "legacy"
    assert t.effective_t2_strategy == "legacy_regex"
    assert t.keys_emitted == [] and t.key_outcomes == []
    assert "margin-of-safety" in t.t2.slugs         # regex found it


def test_strategy_legacy_regex_via_state_a(golden_gdb):
    """STRUCTURED + frontmatter=None (pre-Pass-1) → legacy_regex too."""
    result = build_context_snapshot(
        golden_gdb.conn, source_id=SOURCE_ID,
        source_text="The margin-of-safety idea anchors this essay.",
        frontmatter=None, mode=T2Mode.STRUCTURED,
    )
    t = result.telemetry
    assert t.effective_t2_strategy == "legacy_regex"
    assert t.keys_emitted == [] and t.key_outcomes == []
    assert t.domain_scope is None
    assert "margin-of-safety" in t.t2.slugs


def test_strategy_layered_union(golden_gdb):
    """LAYERED: key dispositions recorded for the key-derived part; the
    regex-derived slug joins T2 candidates WITHOUT an outcome."""
    result = build_context_snapshot(
        golden_gdb.conn, source_id=SOURCE_ID,
        source_text="The margin-of-safety idea anchors this essay.",
        frontmatter=_fm(["wb"]), mode=T2Mode.LAYERED,
    )
    t = result.telemetry
    assert t.effective_t2_strategy == "layered_union"
    assert t.keys_emitted == ["wb"]
    assert t.key_outcomes == [
        KeyOutcome("wb", "resolved_t2_seed", "warren-buffett", "r0"),
    ]
    # regex-derived margin-of-safety is a T2 candidate with NO outcome
    assert set(t.t2.slugs) == {"margin-of-safety", "warren-buffett"}
    assert t.t2.candidates == 2


def test_strategy_layered_union_empty_keys(golden_gdb):
    result = build_context_snapshot(
        golden_gdb.conn, source_id=SOURCE_ID,
        source_text="The margin-of-safety idea anchors this essay.",
        frontmatter=_fm([]), mode=T2Mode.LAYERED,
    )
    t = result.telemetry
    assert t.effective_t2_strategy == "layered_union"
    assert t.keys_emitted == [] and t.key_outcomes == []
    assert "margin-of-safety" in t.t2.slugs


# ---------- empty graph ----------

def test_empty_graph_full_telemetry(tmp_path: Path):
    with GraphDB(tmp_path / "empty") as g:
        result = build_context_snapshot(
            g.conn, source_id="src-x", source_text="anything",
            frontmatter=_fm(["k1", "k2"]), mode=T2Mode.STRUCTURED,
        )
    assert result.snapshot.pages == []
    t = result.telemetry
    assert t.configured_t2_mode == "structured"
    assert t.effective_t2_strategy == "structured_keys"
    assert t.keys_emitted == ["k1", "k2"]
    # every emitted key unresolved — outcomes PRESENT even on the early return
    assert t.key_outcomes == [
        KeyOutcome("k1", "unresolved", None, None),
        KeyOutcome("k2", "unresolved", None, None),
    ]
    zero = TierRecord(0, 0, [])
    assert t.t1 == t.t2 == t.t3 == zero
    assert t.candidate_universe_size == 0
    assert t.domain_scope == "value-investing"
    assert t.cold_start is True
    assert t.max_hops == 2                          # widening policy on empty graph
    assert t.page_cap == 50


# ---------- cold start / max_hops ----------

def test_cold_start_max_hops_2_recorded(golden_gdb):
    """Unknown source (no SUPPORTS) + sparse T2 → cold_start=True, max_hops=2."""
    result = build_context_snapshot(
        golden_gdb.conn, source_id="src-unknown",
        source_text="x", frontmatter=_fm(["margin-of-safety"]),
        mode=T2Mode.STRUCTURED,
    )
    t = result.telemetry
    assert t.cold_start is True
    assert t.max_hops == 2


def test_warm_start_max_hops_1_recorded(golden_gdb):
    result = build_context_snapshot(
        golden_gdb.conn, source_id=SOURCE_ID, source_text="x",
        frontmatter=_fm(["margin-of-safety"]), mode=T2Mode.STRUCTURED,
    )
    t = result.telemetry
    assert t.cold_start is False
    assert t.max_hops == 1


# ---------- tier invariant ----------

def test_tier_invariant_sum_delivered_equals_pages_within_cap(golden_gdb):
    scenarios = [
        ("structured", ["margin-of-safety", "wb", "nonexistent-key"], 50),
        ("structured", [], 50),
        ("layered", ["wb"], 50),
        ("structured", ["margin-of-safety", "wb"], 2),   # under cap pressure
    ]
    for mode_value, keys, cap in scenarios:
        result = build_context_snapshot(
            golden_gdb.conn, source_id=SOURCE_ID,
            source_text="The margin-of-safety idea anchors this essay.",
            page_cap=cap, frontmatter=_fm(keys), mode=T2Mode(mode_value),
        )
        t = result.telemetry
        assert t.t1.delivered + t.t2.delivered + t.t3.delivered \
            == len(result.snapshot.pages) <= t.page_cap, (mode_value, keys, cap)

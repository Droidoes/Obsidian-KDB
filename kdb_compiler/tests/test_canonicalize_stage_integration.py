"""Integration tests for Stage [6] canonicalize wiring in kdb_compile (#74.4).

Covers:
- Missing ledger → empty-ledger fallback (D-R5-8) — Stage 6 completes ok
- Valid ledger → aliases resolved, page slug renamed, body wikilinks remapped
- D-R5-10 atomic write-back of `state/compile_result.json` post-Stage 6
- D-R5-7 `canonical_meta` archived into per-run sidecar by Stage 10 graph_sync
- Fatal halts (D-R5-9): cycle in ledger / malformed JSON → pipeline stops
  before patch_applier; wiki is NOT written; journal records the failure
- JOURNAL_SCHEMA_VERSION bumped to "2.2"
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from kdb_compiler.kdb_compile import compile
from kdb_compiler.run_context import SCHEMA_VERSION, RunContext


# ---------------------------------------------------------------------------
# Helpers — minimal vault scaffolding (mirrors test_kdb_compile.py style)
# ---------------------------------------------------------------------------

_RUN_ID = "2026-05-20T10-00-00Z"
_RUN_AT = "2026-05-20T10:00:00Z"


def _ctx(vault: Path, *, dry_run: bool = False) -> RunContext:
    return RunContext(
        run_id=_RUN_ID,
        started_at=_RUN_AT,
        compiler_version="0.0.0-test",
        schema_version=SCHEMA_VERSION,
        dry_run=dry_run,
        vault_root=vault,
        kdb_root=vault / "KDB",
    )


def _make_vault(root: Path) -> tuple[Path, Path, Path]:
    vault = root / "vault"
    raw = vault / "KDB" / "raw"
    state = vault / "KDB" / "state"
    raw.mkdir(parents=True)
    state.mkdir(parents=True)
    return vault, raw, state


def _seed_source(raw: Path, slug: str = "paper.md") -> None:
    (raw / slug).write_text(f"# {slug}\nseed content", encoding="utf-8")


def _cr_with_alias(run_id: str, alias_slug: str = "aapl") -> dict:
    """Compile result that emits a page intent under an alias slug (one
    the ledger will redirect to a canonical)."""
    return {
        "run_id": run_id,
        "success": True,
        "compiled_sources": [{
            "source_id": "KDB/raw/paper.md",
            "summary_slug": "summary-paper",
            "concept_slugs": [alias_slug],
            "article_slugs": [],
            "pages": [
                {
                    "slug": "summary-paper",
                    "page_type": "summary",
                    "title": "Summary Paper",
                    "status": "active",
                    "body": f"See [[{alias_slug}]] for the ticker.",
                    "supports_page_existence": ["KDB/raw/paper.md"],
                    "outgoing_links": [alias_slug],
                    "confidence": "high",
                },
                {
                    "slug": alias_slug,
                    "page_type": "concept",
                    "title": alias_slug.upper(),
                    "status": "active",
                    "body": f"# {alias_slug.upper()}\n\nAlias-form body.",
                    "supports_page_existence": ["KDB/raw/paper.md"],
                    "outgoing_links": [],
                    "confidence": "medium",
                },
            ],
        }],
        "log_entries": [],
    }


def _cr_plain(run_id: str) -> dict:
    """Compile result with no slugs that match any ledger entry."""
    return {
        "run_id": run_id,
        "success": True,
        "compiled_sources": [{
            "source_id": "KDB/raw/paper.md",
            "summary_slug": "summary-paper",
            "concept_slugs": [],
            "article_slugs": [],
            "pages": [{
                "slug": "summary-paper",
                "page_type": "summary",
                "title": "Summary Paper",
                "status": "active",
                "body": "Plain body, no aliases.",
                "supports_page_existence": ["KDB/raw/paper.md"],
                "outgoing_links": [],
                "confidence": "high",
            }],
        }],
        "log_entries": [],
    }


def _write_cr(state: Path, cr: dict) -> None:
    (state / "compile_result.json").write_text(json.dumps(cr), encoding="utf-8")


def _write_ledger(state: Path, payload: dict | str) -> Path:
    ledger_dir = state / "canonicalization"
    ledger_dir.mkdir(parents=True, exist_ok=True)
    path = ledger_dir / "aliases.json"
    if isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
    else:
        path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _load_journal(state: Path, run_id: str) -> dict:
    return json.loads((state / "runs" / f"{run_id}.json").read_text("utf-8"))


def _by_idx(journal: dict) -> dict:
    return {s["index"]: s for s in journal["stages"]}


@pytest.fixture(autouse=True)
def _isolated_graphdb_path(tmp_path: Path):
    """Isolate the live GraphDB-KDB path so the cross-package Stage 10
    write doesn't pollute the user's real graph during tests."""
    os.environ["KDB_GRAPH_PATH"] = str(tmp_path / "graphdb-isolated")
    yield
    os.environ.pop("KDB_GRAPH_PATH", None)


# ---------------------------------------------------------------------------
# Missing ledger — D-R5-8 empty-ledger fallback
# ---------------------------------------------------------------------------

class TestMissingLedger:
    def test_missing_ledger_run_succeeds_with_empty_ledger(self, tmp_path: Path):
        """No aliases.json present → Stage 6 runs with empty ledger, no
        aliases emitted, run completes (D-R5-8)."""
        vault, raw, state = _make_vault(tmp_path)
        _seed_source(raw)
        _write_cr(state, _cr_plain(_RUN_ID))

        result = compile(vault, run_ctx=_ctx(vault))

        assert result.success is True
        journal = _load_journal(state, _RUN_ID)
        assert journal["schema_version"] == "2.2"
        s6 = _by_idx(journal)[6]
        assert s6["ok"] is True
        assert s6["ledger_snapshot_sha256"] == "empty"
        assert s6["aliases_emitted"] == 0
        assert s6["pages_merged"] == 0

    def test_missing_ledger_emits_canonicalize_ledger_missing_event(
        self, tmp_path: Path
    ):
        """Operator-visible signal: the orchestrator emits a custom event
        when the ledger path is empty so the CLI can surface the warning."""
        vault, raw, state = _make_vault(tmp_path)
        _seed_source(raw)
        _write_cr(state, _cr_plain(_RUN_ID))

        events: list[tuple[str, dict]] = []

        def progress(evt: str, **fields: object) -> None:
            events.append((evt, dict(fields)))

        result = compile(vault, run_ctx=_ctx(vault), progress=progress)
        assert result.success is True

        missing_events = [f for e, f in events if e == "canonicalize_ledger_missing"]
        assert len(missing_events) == 1
        assert missing_events[0]["path"].endswith("/canonicalization/aliases.json")


# ---------------------------------------------------------------------------
# Valid ledger — alias resolution end-to-end
# ---------------------------------------------------------------------------

class TestLedgerHappyPath:
    def test_ledger_with_alias_resolves_through_pipeline(self, tmp_path: Path):
        """aliases.json contains aapl → apple-inc. compile_result emits a
        page with slug 'aapl' + a body wikilink [[aapl]]. After Stage 6:
        pages[] renamed to apple-inc; body remapped; canonical_meta records
        the alias use."""
        vault, raw, state = _make_vault(tmp_path)
        _seed_source(raw)
        _write_cr(state, _cr_with_alias(_RUN_ID, alias_slug="aapl"))
        _write_ledger(state, {"aliases": [
            {"surface": "aapl", "canonical": "apple-inc"}
        ]})

        result = compile(vault, run_ctx=_ctx(vault))
        assert result.success is True

        # state/compile_result.json was overwritten by Stage 6 with the
        # canonicalized payload (D-R5-10).
        canonical_cr = json.loads((state / "compile_result.json").read_text())
        # The aapl page intent is renamed to apple-inc
        slugs = [p["slug"] for p in canonical_cr["compiled_sources"][0]["pages"]]
        assert "apple-inc" in slugs
        assert "aapl" not in slugs
        # The summary page's body wikilink is remapped
        summary = next(p for p in canonical_cr["compiled_sources"][0]["pages"]
                       if p["page_type"] == "summary")
        assert "[[apple-inc]]" in summary["body"]
        assert "[[aapl]]" not in summary["body"]
        # canonical_meta block present + carries the resolution record
        cm = canonical_cr["canonical_meta"]
        assert any(
            a["alias_slug"] == "aapl" and a["canonical_slug"] == "apple-inc"
            for a in cm["aliases_emitted"]
        )

    def test_canonical_wiki_page_is_written_not_alias(self, tmp_path: Path):
        """D-R5-12 verification: after compile with ledger aapl→apple-inc
        and a source emitting an aapl page, the vault has apple-inc.md
        but NOT aapl.md."""
        vault, raw, state = _make_vault(tmp_path)
        _seed_source(raw)
        _write_cr(state, _cr_with_alias(_RUN_ID, alias_slug="aapl"))
        _write_ledger(state, {"aliases": [
            {"surface": "aapl", "canonical": "apple-inc"}
        ]})

        result = compile(vault, run_ctx=_ctx(vault))
        assert result.success is True

        wiki_concepts = vault / "KDB" / "wiki" / "concepts"
        assert (wiki_concepts / "apple-inc.md").exists()
        assert not (wiki_concepts / "aapl.md").exists()

    def test_canonical_meta_archived_in_sidecar(self, tmp_path: Path):
        """D-R5-7 replay parity: the per-run sidecar at
        state/runs/<run_id>/compile_result.json contains canonical_meta
        (because Stage 6 wrote back to state/compile_result.json BEFORE
        Stage 10 archived it)."""
        vault, raw, state = _make_vault(tmp_path)
        _seed_source(raw)
        _write_cr(state, _cr_with_alias(_RUN_ID, alias_slug="aapl"))
        ledger_path = _write_ledger(state, {"aliases": [
            {"surface": "aapl", "canonical": "apple-inc"}
        ]})

        result = compile(vault, run_ctx=_ctx(vault))
        assert result.success is True

        archived = json.loads(
            (state / "runs" / _RUN_ID / "compile_result.json").read_text()
        )
        assert "canonical_meta" in archived
        # ledger_snapshot_sha256 matches the live ledger's sha (not "empty")
        import hashlib
        expected_sha = hashlib.sha256(ledger_path.read_bytes()).hexdigest()
        assert archived["canonical_meta"]["ledger_snapshot_sha256"] == expected_sha


# ---------------------------------------------------------------------------
# Fatal halts — D-R5-9
# ---------------------------------------------------------------------------

class TestFatalLedgerErrors:
    def test_circular_alias_halts_pipeline_before_patch_applier(
        self, tmp_path: Path
    ):
        """Cycle A→B, B→A → Stage 6 fails fatally; patch_applier never
        runs; wiki not written; journal carries CircularAliasError."""
        vault, raw, state = _make_vault(tmp_path)
        _seed_source(raw)
        _write_cr(state, _cr_plain(_RUN_ID))
        _write_ledger(state, {"aliases": [
            {"surface": "alpha", "canonical": "beta"},
            {"surface": "beta", "canonical": "alpha"},
        ]})

        result = compile(vault, run_ctx=_ctx(vault))

        assert result.success is False
        journal = _load_journal(state, _RUN_ID)
        # Stage 6 reports failure
        s6 = _by_idx(journal)[6]
        assert s6["ok"] is False
        assert "CircularAlias" in s6["note"]
        # Pipeline halted at Stage 6
        assert journal["terminated_at_stage"] == 6
        assert journal["failure_stage_name"] == "canonicalize"
        assert journal["failure_type"] == "CircularAliasError"
        # patch_applier never ran — Stage 8 absent from the journal
        assert 8 not in _by_idx(journal)
        # Wiki was NOT written (D-R5-9: leave both renderings on previous
        # state — for a first run, that means no wiki at all)
        assert not (vault / "KDB" / "wiki").exists() or \
               not any((vault / "KDB" / "wiki").rglob("*.md"))

    def test_malformed_ledger_halts_pipeline_before_patch_applier(
        self, tmp_path: Path
    ):
        """Bad JSON in aliases.json → LedgerLoadError; pipeline halts at
        Stage 6 before patch_applier."""
        vault, raw, state = _make_vault(tmp_path)
        _seed_source(raw)
        _write_cr(state, _cr_plain(_RUN_ID))
        _write_ledger(state, "{not valid json")

        result = compile(vault, run_ctx=_ctx(vault))

        assert result.success is False
        journal = _load_journal(state, _RUN_ID)
        s6 = _by_idx(journal)[6]
        assert s6["ok"] is False
        assert "LedgerLoadError" in s6["note"]
        assert journal["failure_type"] == "LedgerLoadError"
        assert journal["terminated_at_stage"] == 6
        assert 8 not in _by_idx(journal)  # patch_applier did not run

    def test_missing_required_field_in_ledger_halts_pipeline(
        self, tmp_path: Path
    ):
        """Entry missing 'canonical' field → LedgerLoadError → halt."""
        vault, raw, state = _make_vault(tmp_path)
        _seed_source(raw)
        _write_cr(state, _cr_plain(_RUN_ID))
        _write_ledger(state, {"aliases": [{"surface": "aapl"}]})

        result = compile(vault, run_ctx=_ctx(vault))
        assert result.success is False
        journal = _load_journal(state, _RUN_ID)
        assert journal["failure_type"] == "LedgerLoadError"
        assert journal["terminated_at_stage"] == 6


# ---------------------------------------------------------------------------
# Schema-validation compatibility — D-R5-7
# ---------------------------------------------------------------------------

class TestSchemaCompatibility:
    def test_canonical_meta_passes_jsonschema_validation(self, tmp_path: Path):
        """The canonicalized compile_result.json on disk must still
        validate against compile_result.schema.json (D-R5-7: single schema
        with canonical_meta + canonical_id as optional whitelisted props)."""
        from jsonschema import validate

        vault, raw, state = _make_vault(tmp_path)
        _seed_source(raw)
        _write_cr(state, _cr_with_alias(_RUN_ID, alias_slug="aapl"))
        _write_ledger(state, {"aliases": [
            {"surface": "aapl", "canonical": "apple-inc"}
        ]})

        result = compile(vault, run_ctx=_ctx(vault))
        assert result.success is True

        canonical_cr = json.loads((state / "compile_result.json").read_text())
        schema_path = Path(__file__).parent.parent / "schemas" / "compile_result.schema.json"
        schema = json.loads(schema_path.read_text())
        # Should not raise — schema accepts canonical_meta + canonical_id
        validate(instance=canonical_cr, schema=schema)

    def test_pre_74_compile_result_without_canonical_meta_validates(self):
        """#74.7 back-compat (D-R5-7 single-schema strategy): a pre-#74
        compile_result that lacks `canonical_meta` and `canonical_id`
        still validates against the post-#74.4 schema. Locks in that
        the schema additions are strictly optional — old journals replay
        without hitting jsonschema rejection."""
        from jsonschema import validate

        schema_path = Path(__file__).parent.parent / "schemas" / "compile_result.schema.json"
        schema = json.loads(schema_path.read_text())
        pre_74_cr = {
            "run_id": "pre-74-test",
            "success": True,
            "compiled_sources": [{
                "source_id": "KDB/raw/paper.md",
                "summary_slug": "summary-paper",
                "concept_slugs": [],
                "article_slugs": [],
                "pages": [{
                    "slug": "summary-paper",
                    "page_type": "summary",
                    "title": "Summary Paper",
                    "status": "active",
                    "body": "Pre-#74 body — no canonical_id field on the page.",
                    "supports_page_existence": ["KDB/raw/paper.md"],
                    "outgoing_links": [],
                    "confidence": "high",
                }],
            }],
            "log_entries": [],
        }
        assert "canonical_meta" not in pre_74_cr
        assert "canonical_id" not in pre_74_cr["compiled_sources"][0]["pages"][0]
        # Should not raise — the post-#74.4 schema accepts pre-#74 shapes
        validate(instance=pre_74_cr, schema=schema)

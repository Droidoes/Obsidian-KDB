"""Tests for kdb_compiler.canonicalize Stage [6] algorithm (Task #74.3).

Covers:
- `_normalize_slug` — slug normalization edge cases
- `build_resolve_map` — chain flattening (D-R5-13) + cycle detection
- `_remap_body_wikilinks` — body wikilink regex pass (D-R5-11)
- `_merge_page_intents` — OQ-F page collision merging
- `run` — end-to-end integration including canonical_meta emission
- `write_canonicalized` — atomic on-disk write-back (D-R5-10)

Anchors:
- docs/task74-canonicalization-blueprint.md §6 (contract) + §7 (algorithm)
- Round 5 §8.4 (5-layer selection — this is Layer 3)
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from kdb_compiler.canonicalize import (
    AliasEntry,
    AliasLedger,
    CanonicalizationResult,
    CircularAliasError,
    _merge_page_intents,
    _normalize_slug,
    _remap_body_wikilinks,
    _remap_outgoing_and_slug_lists,
    build_resolve_map,
    run,
    write_canonicalized,
)


# -------------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------------

def _ledger(*pairs: tuple[str, str]) -> AliasLedger:
    """Build an in-memory ledger from (surface, canonical) tuples."""
    return AliasLedger(
        entries=tuple(AliasEntry(surface=s, canonical=c) for s, c in pairs),
        snapshot_sha256="test-sha-" + str(len(pairs)),
    )


def _page(slug: str, body: str = "", **kw) -> dict:
    """Build a minimal pageIntent dict."""
    p = {
        "slug": slug,
        "page_type": kw.get("page_type", "concept"),
        "title": kw.get("title", slug),
        "body": body,
    }
    if "outgoing_links" in kw:
        p["outgoing_links"] = kw["outgoing_links"]
    if "supports_page_existence" in kw:
        p["supports_page_existence"] = kw["supports_page_existence"]
    return p


def _cs(source_id: str, summary_slug: str, pages: list[dict], **kw) -> dict:
    """Build a minimal compiledSource dict."""
    cs = {
        "source_id": source_id,
        "summary_slug": summary_slug,
        "pages": pages,
    }
    if "concept_slugs" in kw:
        cs["concept_slugs"] = kw["concept_slugs"]
    if "article_slugs" in kw:
        cs["article_slugs"] = kw["article_slugs"]
    return cs


def _cr(compiled_sources: list[dict], run_id: str = "test-run") -> dict:
    """Build a minimal compile_result dict."""
    return {
        "run_id": run_id,
        "success": True,
        "compiled_sources": compiled_sources,
    }


# -------------------------------------------------------------------------
# _normalize_slug
# -------------------------------------------------------------------------

class TestNormalizeSlug:
    def test_already_kebab(self):
        assert _normalize_slug("apple-inc") == "apple-inc"

    def test_uppercase(self):
        assert _normalize_slug("AAPL") == "aapl"

    def test_title_form(self):
        assert _normalize_slug("Apple Inc.") == "apple-inc"

    def test_collapses_internal_whitespace(self):
        assert _normalize_slug("apple    inc") == "apple-inc"

    def test_strips_diacritics(self):
        assert _normalize_slug("café") == "cafe"

    def test_strips_punctuation(self):
        assert _normalize_slug("Apple, Inc!") == "apple-inc"

    def test_empty_input(self):
        assert _normalize_slug("") == ""

    def test_pure_punctuation_input(self):
        assert _normalize_slug("!@#$%") == ""

    def test_idempotent(self):
        s = _normalize_slug("Apple Inc.")
        assert _normalize_slug(s) == s
        assert _normalize_slug(_normalize_slug(s)) == s


# -------------------------------------------------------------------------
# build_resolve_map — Pass 1
# -------------------------------------------------------------------------

class TestBuildResolveMap:
    def test_empty_ledger(self):
        assert build_resolve_map(_ledger()) == {}

    def test_single_hop(self):
        m = build_resolve_map(_ledger(("AAPL", "apple-inc")))
        assert m == {"aapl": "apple-inc"}

    def test_chain_flattening_two_hops(self):
        """D-R5-13: A→B and B→C must produce A→C and B→C (both flat)."""
        m = build_resolve_map(_ledger(
            ("aapl", "apple"),
            ("apple", "apple-inc"),
        ))
        assert m == {"aapl": "apple-inc", "apple": "apple-inc"}

    def test_chain_flattening_three_hops(self):
        m = build_resolve_map(_ledger(
            ("a", "b"),
            ("b", "c"),
            ("c", "d"),
        ))
        assert m == {"a": "d", "b": "d", "c": "d"}

    def test_cycle_two_node(self):
        with pytest.raises(CircularAliasError, match="cycle detected"):
            build_resolve_map(_ledger(
                ("a", "b"),
                ("b", "a"),
            ))

    def test_cycle_three_node(self):
        with pytest.raises(CircularAliasError, match="cycle detected"):
            build_resolve_map(_ledger(
                ("a", "b"),
                ("b", "c"),
                ("c", "a"),
            ))

    def test_self_mapping_skipped(self):
        """A surface that normalizes to its own canonical is a no-op
        (e.g., user mistakenly wrote `{surface: "AAPL", canonical: "AAPL"}` —
        normalized both ways to `aapl`)."""
        m = build_resolve_map(_ledger(("AAPL", "aapl")))
        assert m == {}

    def test_pure_punctuation_entries_skipped(self):
        m = build_resolve_map(_ledger(
            ("!!!", "apple-inc"),
            ("aapl", "@@@"),
        ))
        assert m == {}

    def test_surfaces_with_different_cases_collide(self):
        """Two surfaces that normalize to the same form should not both
        appear in the ledger (load-time guard); but if they did via direct
        AliasLedger construction in tests, only one wins (last-write).
        This test asserts the algorithm doesn't crash on duplicates;
        production rejects them at load time."""
        # Build a ledger directly bypassing load_or_empty validation
        ledger = AliasLedger(entries=(
            AliasEntry(surface="AAPL", canonical="apple-inc"),
            AliasEntry(surface="aapl", canonical="apple-inc"),
        ), snapshot_sha256="x")
        m = build_resolve_map(ledger)
        assert m == {"aapl": "apple-inc"}


# -------------------------------------------------------------------------
# _remap_body_wikilinks — Pass 4
# -------------------------------------------------------------------------

class TestBodyWikilinkRemap:
    def test_simple_remap(self):
        resolve = {"aapl": "apple-inc"}
        new_body, remaps = _remap_body_wikilinks(
            "Apple is [[aapl]] in markets.", resolve
        )
        assert new_body == "Apple is [[apple-inc]] in markets."
        assert remaps == [("aapl", "apple-inc")]

    def test_no_match_leaves_body_unchanged(self):
        resolve = {"aapl": "apple-inc"}
        body = "No wikilinks here."
        new_body, remaps = _remap_body_wikilinks(body, resolve)
        assert new_body == body
        assert remaps == []

    def test_canonical_target_left_alone(self):
        """[[apple-inc]] is already canonical — no remap, no record."""
        resolve = {"aapl": "apple-inc"}
        body = "See [[apple-inc]] for details."
        new_body, remaps = _remap_body_wikilinks(body, resolve)
        assert new_body == body
        assert remaps == []

    def test_display_text_preserved(self):
        """[[aapl|Apple]] → [[apple-inc|Apple]]: target rewrites, display
        text preserved verbatim (D-R5-11)."""
        resolve = {"aapl": "apple-inc"}
        new_body, remaps = _remap_body_wikilinks(
            "Click [[aapl|the stock symbol]] here.", resolve
        )
        assert new_body == "Click [[apple-inc|the stock symbol]] here."
        assert remaps == [("aapl", "apple-inc")]

    def test_multiple_remaps_in_one_body(self):
        resolve = {"aapl": "apple-inc", "goog": "alphabet-inc"}
        body = "Compare [[aapl]] vs [[goog]] vs [[msft]]."
        new_body, remaps = _remap_body_wikilinks(body, resolve)
        assert new_body == "Compare [[apple-inc]] vs [[alphabet-inc]] vs [[msft]]."
        assert remaps == [("aapl", "apple-inc"), ("goog", "alphabet-inc")]

    def test_uppercase_target_normalizes_for_lookup(self):
        """Body authors might write [[AAPL]] — the regex captures "AAPL",
        normalize_slug folds it to "aapl", looks up in resolve.
        Replacement uses the canonical kebab form."""
        resolve = {"aapl": "apple-inc"}
        new_body, remaps = _remap_body_wikilinks("See [[AAPL]].", resolve)
        assert new_body == "See [[apple-inc]]."
        assert remaps == [("AAPL", "apple-inc")]

    def test_idempotent_on_already_canonical(self):
        resolve = {"aapl": "apple-inc"}
        body = "Already [[apple-inc]] form."
        new_body, _ = _remap_body_wikilinks(body, resolve)
        new_body2, _ = _remap_body_wikilinks(new_body, resolve)
        assert new_body == new_body2 == body


# -------------------------------------------------------------------------
# _merge_page_intents — Pass 2 (OQ-F)
# -------------------------------------------------------------------------

class TestPageMerge:
    def test_no_collision_no_merge(self):
        resolve = {}
        cr = _cr([
            _cs("src1", "summary-src1", [_page("foo", "body of foo")]),
            _cs("src2", "summary-src2", [_page("bar", "body of bar")]),
        ])
        merged_log, used = _merge_page_intents(cr, resolve)
        assert merged_log == []
        assert used == []
        # Pages unchanged
        assert cr["compiled_sources"][0]["pages"][0]["slug"] == "foo"
        assert cr["compiled_sources"][1]["pages"][0]["slug"] == "bar"

    def test_alias_singleton_rename(self):
        """One source has a page whose slug normalizes to an alias —
        the slug renames to canonical, no body merge."""
        resolve = {"aapl": "apple-inc"}
        cr = _cr([_cs("src1", "summary-src1", [_page("aapl", "body of aapl")])])
        merged_log, used = _merge_page_intents(cr, resolve)
        assert cr["compiled_sources"][0]["pages"][0]["slug"] == "apple-inc"
        assert cr["compiled_sources"][0]["pages"][0]["body"] == "body of aapl"
        assert merged_log == [{
            "alias_page_slug": "aapl",
            "merged_into_canonical": "apple-inc",
            "merge_strategy": "alias-singleton-rename",
        }]
        assert used == [("aapl", "apple-inc")]

    def test_canonical_wins_when_canonical_named_page_exists(self):
        """OQ-F: if canonical-slug page intent exists, its body wins."""
        resolve = {"aapl": "apple-inc"}
        cr = _cr([
            _cs("src1", "summary-src1", [_page("aapl", "alias body — short")]),
            _cs("src2", "summary-src2",
                [_page("apple-inc", "canonical body — much longer because i ramble")]),
        ])
        merged_log, used = _merge_page_intents(cr, resolve)
        # One canonical page survives
        all_pages = [p for cs in cr["compiled_sources"] for p in cs["pages"]]
        assert len(all_pages) == 1
        assert all_pages[0]["slug"] == "apple-inc"
        assert all_pages[0]["body"] == "canonical body — much longer because i ramble"
        # Strategy recorded
        assert merged_log[0]["merge_strategy"] == "canonical-wins"

    def test_longest_wins_when_no_canonical_named(self):
        """OQ-F fallback: when all contenders are aliases, longest body wins."""
        resolve = {"aapl": "apple-inc", "apple-corp": "apple-inc"}
        cr = _cr([
            _cs("src1", "summary-src1", [_page("aapl", "short")]),
            _cs("src2", "summary-src2",
                [_page("apple-corp", "the much longer body that should win")]),
        ])
        merged_log, _ = _merge_page_intents(cr, resolve)
        all_pages = [p for cs in cr["compiled_sources"] for p in cs["pages"]]
        assert len(all_pages) == 1
        assert all_pages[0]["body"] == "the much longer body that should win"
        assert {e["merge_strategy"] for e in merged_log} == {"longest-wins"}

    def test_outgoing_links_union_across_contenders(self):
        """Codex's OQ-F refinement: outgoing_links are UNIONED across all
        contenders, not just the body-winner. Without union, contributions
        from the loser sources would be silently dropped."""
        resolve = {"aapl": "apple-inc"}
        cr = _cr([
            _cs("src1", "summary-src1",
                [_page("aapl", "tiny", outgoing_links=["stocks", "dividend"])]),
            _cs("src2", "summary-src2",
                [_page("apple-inc", "the longer canonical body",
                       outgoing_links=["tech", "hardware"])]),
        ])
        _merge_page_intents(cr, resolve)
        merged = [p for cs in cr["compiled_sources"] for p in cs["pages"]][0]
        # All four links survive, in seen order (canonical-wins → winner's
        # outgoing_links come first per the iteration order of contenders).
        assert merged["outgoing_links"] == ["stocks", "dividend", "tech", "hardware"]

    def test_supports_page_existence_union_across_contenders(self):
        """Same UNION discipline for supports_page_existence (Codex refinement)."""
        resolve = {"aapl": "apple-inc"}
        cr = _cr([
            _cs("src1", "summary-src1",
                [_page("aapl", "short", supports_page_existence=["KDB/raw/s1.md"])]),
            _cs("src2", "summary-src2",
                [_page("apple-inc", "longer canonical body",
                       supports_page_existence=["KDB/raw/s2.md"])]),
        ])
        _merge_page_intents(cr, resolve)
        merged = [p for cs in cr["compiled_sources"] for p in cs["pages"]][0]
        assert merged["supports_page_existence"] == ["KDB/raw/s1.md", "KDB/raw/s2.md"]

    def test_winner_placed_at_winners_position(self):
        """The merged page replaces the winner's entry; the loser's entry
        is removed from its compiled_source's pages[]."""
        resolve = {"aapl": "apple-inc"}
        cr = _cr([
            _cs("src1", "summary-src1", [_page("aapl", "alias body")]),
            _cs("src2", "summary-src2", [_page("apple-inc", "canonical longer body")]),
        ])
        _merge_page_intents(cr, resolve)
        # canonical-wins → winner is src2's page
        assert len(cr["compiled_sources"][0]["pages"]) == 0
        assert len(cr["compiled_sources"][1]["pages"]) == 1
        assert cr["compiled_sources"][1]["pages"][0]["body"] == "canonical longer body"


# -------------------------------------------------------------------------
# _remap_outgoing_and_slug_lists — Pass 3
# -------------------------------------------------------------------------

class TestOutgoingAndSlugListsRemap:
    def test_outgoing_links_remap(self):
        resolve = {"aapl": "apple-inc"}
        cr = _cr([_cs("src1", "summary-src1", [
            _page("foo", "", outgoing_links=["aapl", "bar"])
        ])])
        link_remaps, used = _remap_outgoing_and_slug_lists(cr, resolve)
        assert cr["compiled_sources"][0]["pages"][0]["outgoing_links"] == [
            "apple-inc", "bar"
        ]
        assert link_remaps == [("aapl", "apple-inc")]
        assert used == [("aapl", "apple-inc")]

    def test_concept_slugs_remap_with_dedup(self):
        """If two slugs in concept_slugs both remap to the same canonical,
        dedupe (preserving order of first occurrence)."""
        resolve = {"aapl": "apple-inc", "apple-corp": "apple-inc"}
        cr = _cr([_cs("src1", "summary-src1", [],
                      concept_slugs=["aapl", "apple-corp", "other"])])
        _remap_outgoing_and_slug_lists(cr, resolve)
        assert cr["compiled_sources"][0]["concept_slugs"] == ["apple-inc", "other"]

    def test_article_slugs_remap(self):
        resolve = {"aapl": "apple-inc"}
        cr = _cr([_cs("src1", "summary-src1", [],
                      article_slugs=["aapl", "other-article"])])
        _remap_outgoing_and_slug_lists(cr, resolve)
        assert cr["compiled_sources"][0]["article_slugs"] == [
            "apple-inc", "other-article"
        ]


# -------------------------------------------------------------------------
# run() — end-to-end integration
# -------------------------------------------------------------------------

class TestRunIntegration:
    def test_empty_ledger_is_noop(self):
        cr = _cr([_cs("src1", "summary-src1", [_page("foo", "body")])])
        result = run(cr, _ledger(), "run-1")
        assert result.compile_result is cr  # same object (mutated in place)
        assert result.canonical_meta["aliases_emitted"] == []
        assert result.canonical_meta["outgoing_link_remaps"] == []
        assert result.canonical_meta["merged_pages"] == []
        assert result.canonical_meta["ledger_snapshot_sha256"] == "test-sha-0"
        assert "canonical_meta" in cr  # written into cr top-level

    def test_end_to_end_alias_resolution(self):
        """Full pass: ledger maps AAPL→apple-inc; cr has page intent for
        AAPL with outgoing_links and body wikilinks both referencing AAPL.
        After run(): page slug renames to apple-inc; outgoing_links and
        body both reference apple-inc; canonical_meta records everything."""
        ledger = _ledger(("AAPL", "apple-inc"))
        cr = _cr([_cs("src1", "summary-src1", [
            _page(
                "aapl",
                "Header about [[aapl]] performance.",
                outgoing_links=["aapl", "stocks"],
            ),
        ])])
        result = run(cr, ledger, "run-1")

        # Page renamed
        page = cr["compiled_sources"][0]["pages"][0]
        assert page["slug"] == "apple-inc"
        # outgoing_links remapped + deduped
        assert page["outgoing_links"] == ["apple-inc", "stocks"]
        # Body wikilink remapped
        assert page["body"] == "Header about [[apple-inc]] performance."

        # canonical_meta records all three remap events for the same alias
        cm = result.canonical_meta
        assert cm["algorithm_version"] == "1.0"
        # aliases_emitted has the alias→canonical pair
        assert {"alias_slug": "aapl", "canonical_slug": "apple-inc",
                "algorithm": "ledger"} in cm["aliases_emitted"]
        # link remaps: from outgoing_links AND body wikilinks
        froms = [r["from"] for r in cm["outgoing_link_remaps"]]
        tos = [r["to"] for r in cm["outgoing_link_remaps"]]
        assert "aapl" in froms
        assert all(t == "apple-inc" for t in tos)
        # merged_pages records the singleton rename
        assert len(cm["merged_pages"]) == 1
        assert cm["merged_pages"][0]["merge_strategy"] == "alias-singleton-rename"

        # stats summary
        assert result.stats["pages_merged"] == 1
        assert result.stats["aliases_emitted"] >= 1

    def test_cross_source_collision_with_canonical_wins(self):
        """Two sources both emit page intents for canonical-equivalent
        slugs. The canonical-named body wins (OQ-F)."""
        ledger = _ledger(("aapl", "apple-inc"))
        cr = _cr([
            _cs("src-a", "summary-src-a", [_page("aapl", "alias body short")]),
            _cs("src-b", "summary-src-b",
                [_page("apple-inc", "canonical body — definitive write-up")]),
        ])
        result = run(cr, ledger, "run-2")

        all_pages = [p for cs in cr["compiled_sources"] for p in cs["pages"]]
        assert len(all_pages) == 1
        assert all_pages[0]["slug"] == "apple-inc"
        assert "canonical body" in all_pages[0]["body"]

        strategies = {e["merge_strategy"] for e in result.canonical_meta["merged_pages"]}
        assert "canonical-wins" in strategies

    def test_circular_alias_raises(self):
        """The fatal failure mode: D-R5-9 — Stage 6 halts the pipeline
        before patch_applier when the ledger contains a cycle."""
        ledger = _ledger(("a", "b"), ("b", "a"))
        cr = _cr([_cs("src1", "summary-src1", [_page("foo", "body")])])
        with pytest.raises(CircularAliasError, match="cycle detected"):
            run(cr, ledger, "run-1")

    def test_ledger_sha_propagated_to_canonical_meta(self):
        """D-R5-7: canonical_meta.ledger_snapshot_sha256 must equal the
        ledger's snapshot_sha256 at compile time. Replay (rebuild) checks
        these match before applying any aliases."""
        ledger = AliasLedger(
            entries=(AliasEntry(surface="aapl", canonical="apple-inc"),),
            snapshot_sha256="deadbeef-test-sha",
        )
        cr = _cr([_cs("src1", "summary-src1", [_page("foo", "body")])])
        result = run(cr, ledger, "run-1")
        assert result.canonical_meta["ledger_snapshot_sha256"] == "deadbeef-test-sha"

    def test_empty_ledger_sha_is_empty_sentinel(self):
        """When the ledger came from a missing file (D-R5-8), the sha is
        the literal sentinel "empty" — preserved verbatim into
        canonical_meta so replay knows the original run had no ledger."""
        empty = AliasLedger()  # default snapshot_sha256 = "empty"
        cr = _cr([_cs("src1", "summary-src1", [_page("foo", "body")])])
        result = run(cr, empty, "run-1")
        assert result.canonical_meta["ledger_snapshot_sha256"] == "empty"


# -------------------------------------------------------------------------
# write_canonicalized — D-R5-10 atomic write-back
# -------------------------------------------------------------------------

class TestWriteCanonicalized:
    def test_write_back_round_trips(self, tmp_path: Path):
        """The canonicalized cr is written atomically + can be read back."""
        cr = _cr([_cs("src1", "summary-src1", [_page("foo", "body")])])
        run(cr, _ledger(), "run-1")
        target = tmp_path / "compile_result.json"
        write_canonicalized(cr, target)
        # File exists and round-trips through JSON
        loaded = json.loads(target.read_text(encoding="utf-8"))
        assert loaded["run_id"] == "test-run"
        # canonical_meta is in the written file (D-R5-10 — subsequent
        # stages and archival see the canonicalized version)
        assert "canonical_meta" in loaded
        assert loaded["canonical_meta"]["algorithm_version"] == "1.0"

    def test_write_back_uses_atomic_io(self, tmp_path: Path):
        """Sanity check: writing twice leaves only the final content
        (no .tmp lingering) — atomic_write_json should rename into place."""
        cr = _cr([_cs("src1", "summary-src1", [_page("foo", "body")])])
        run(cr, _ledger(), "run-1")
        target = tmp_path / "compile_result.json"
        write_canonicalized(cr, target)
        cr["run_id"] = "test-run-2"
        write_canonicalized(cr, target)
        loaded = json.loads(target.read_text(encoding="utf-8"))
        assert loaded["run_id"] == "test-run-2"
        # No .tmp file left behind
        assert not any(p.name.endswith(".tmp") for p in tmp_path.iterdir())

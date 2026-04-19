"""Tests for context_loader — manifest snapshot builder.

Coverage per blueprint §10:
    - pages whose source_refs[].source_id matches source_id are selected
    - pages whose slug appears as a whole-word token in source_text are selected
    - depth-1 expansion via outgoing_links pulls in linked pages
    - dedup across selection paths (source_refs + text + outgoing)
    - page_cap truncates, with seeds prioritised over depth-1
    - empty / missing manifest -> empty snapshot
    - projection drops body, paths, timestamps, source_refs, etc.
    - ordering is deterministic (seeds sorted, then depth-1 sorted)
"""
from __future__ import annotations

import dataclasses

from kdb_compiler.context_loader import build_context_snapshot
from kdb_compiler.types import ContextPage, ContextSnapshot

SOURCE_ID = "KDB/raw/foo.md"


def _page_record(
    *,
    slug: str,
    title: str | None = None,
    page_type: str = "concept",
    outgoing: list[str] | None = None,
    cites: list[str] | None = None,
    body: str | None = "IGNORED body text",
    extras: dict | None = None,
) -> dict:
    rec: dict = {
        "slug": slug,
        "title": title if title is not None else slug.replace("-", " ").title(),
        "page_type": page_type,
        "outgoing_links": list(outgoing) if outgoing else [],
        "source_refs": [
            {"source_id": sid, "hash": "sha256:abc", "role": "primary"}
            for sid in (cites or [])
        ],
        # Noise fields that MUST NOT leak into ContextPage
        "page_id": f"KDB/wiki/concepts/{slug}.md",
        "body": body,
        "created_at": "2026-04-01T00:00:00Z",
        "updated_at": "2026-04-18T00:00:00Z",
        "last_run_id": "2026-04-01T00-00-00Z",
        "supports_page_existence": cites or [],
        "confidence": "medium",
        "status": "active",
    }
    if extras:
        rec.update(extras)
    return rec


def _manifest(pages: dict[str, dict]) -> dict:
    return {"schema_version": "1.0", "pages": pages}


# ---------- selection: source_refs ----------

def test_source_refs_match_selects_page() -> None:
    m = _manifest({
        "KDB/wiki/summaries/foo.md": _page_record(slug="foo", page_type="summary", cites=[SOURCE_ID]),
        "KDB/wiki/concepts/other.md": _page_record(slug="other", cites=["KDB/raw/other.md"]),
    })
    snap = build_context_snapshot(m, source_id=SOURCE_ID, source_text="")
    assert [p.slug for p in snap.pages] == ["foo"]


# ---------- selection: slug-in-text ----------

def test_slug_whole_word_match_in_text_selects_page() -> None:
    m = _manifest({
        "KDB/wiki/concepts/self-attention.md": _page_record(slug="self-attention"),
        "KDB/wiki/concepts/unrelated.md": _page_record(slug="unrelated"),
    })
    text = "Transformers use self-attention extensively."
    snap = build_context_snapshot(m, source_id=SOURCE_ID, source_text=text)
    assert [p.slug for p in snap.pages] == ["self-attention"]


def test_slug_substring_in_word_does_not_match() -> None:
    """'attention' must not match inside 'self-attention' or 'attentional'."""
    m = _manifest({
        "KDB/wiki/concepts/attention.md": _page_record(slug="attention"),
    })
    snap = build_context_snapshot(m, source_id=SOURCE_ID, source_text="attentional dynamics and self-attention")
    assert snap.pages == []


def test_slug_match_is_case_insensitive() -> None:
    m = _manifest({
        "KDB/wiki/concepts/self-attention.md": _page_record(slug="self-attention"),
    })
    snap = build_context_snapshot(
        m, source_id=SOURCE_ID, source_text="Self-Attention is the core idea"
    )
    assert [p.slug for p in snap.pages] == ["self-attention"]


# ---------- depth-1 expansion ----------

def test_depth1_via_outgoing_links_included() -> None:
    m = _manifest({
        "KDB/wiki/summaries/foo.md": _page_record(
            slug="foo", page_type="summary", cites=[SOURCE_ID],
            outgoing=["bar", "baz"],
        ),
        "KDB/wiki/concepts/bar.md": _page_record(slug="bar"),
        "KDB/wiki/concepts/baz.md": _page_record(slug="baz"),
        "KDB/wiki/concepts/quux.md": _page_record(slug="quux"),
    })
    snap = build_context_snapshot(m, source_id=SOURCE_ID, source_text="")
    assert [p.slug for p in snap.pages] == ["foo", "bar", "baz"]


def test_depth1_stops_at_one_hop() -> None:
    """bar -> baz -> quux chain: quux must NOT be included (depth-2)."""
    m = _manifest({
        "KDB/wiki/summaries/foo.md": _page_record(
            slug="foo", page_type="summary", cites=[SOURCE_ID],
            outgoing=["bar"],
        ),
        "KDB/wiki/concepts/bar.md": _page_record(slug="bar", outgoing=["baz"]),
        "KDB/wiki/concepts/baz.md": _page_record(slug="baz", outgoing=["quux"]),
        "KDB/wiki/concepts/quux.md": _page_record(slug="quux"),
    })
    snap = build_context_snapshot(m, source_id=SOURCE_ID, source_text="")
    assert [p.slug for p in snap.pages] == ["foo", "bar"]


def test_depth1_link_to_nonexistent_slug_dropped() -> None:
    m = _manifest({
        "KDB/wiki/summaries/foo.md": _page_record(
            slug="foo", page_type="summary", cites=[SOURCE_ID],
            outgoing=["ghost"],
        ),
    })
    snap = build_context_snapshot(m, source_id=SOURCE_ID, source_text="")
    assert [p.slug for p in snap.pages] == ["foo"]


# ---------- dedup ----------

def test_seed_via_both_source_refs_and_text_not_duplicated() -> None:
    m = _manifest({
        "KDB/wiki/summaries/foo.md": _page_record(
            slug="foo", page_type="summary", cites=[SOURCE_ID],
        ),
    })
    snap = build_context_snapshot(m, source_id=SOURCE_ID, source_text="foo is cool")
    assert [p.slug for p in snap.pages] == ["foo"]


def test_depth1_already_a_seed_not_duplicated() -> None:
    """foo links to bar; bar is also a seed by text mention."""
    m = _manifest({
        "KDB/wiki/summaries/foo.md": _page_record(
            slug="foo", page_type="summary", cites=[SOURCE_ID],
            outgoing=["bar"],
        ),
        "KDB/wiki/concepts/bar.md": _page_record(slug="bar"),
    })
    snap = build_context_snapshot(m, source_id=SOURCE_ID, source_text="mentions bar")
    assert [p.slug for p in snap.pages] == ["bar", "foo"]  # seeds sorted, no depth-1


# ---------- cap ----------

def test_page_cap_truncates() -> None:
    pages = {}
    for i in range(60):
        slug = f"c{i:02d}"
        pages[f"KDB/wiki/concepts/{slug}.md"] = _page_record(slug=slug, cites=[SOURCE_ID])
    m = _manifest(pages)
    snap = build_context_snapshot(m, source_id=SOURCE_ID, source_text="", page_cap=50)
    assert len(snap.pages) == 50
    # sorted seeds -> first 50 = c00..c49
    assert [p.slug for p in snap.pages] == [f"c{i:02d}" for i in range(50)]


def test_seeds_prioritised_over_depth1_when_cap_hits() -> None:
    """3-slot cap: 3 seeds + 2 depth-1 links -> only the 3 seeds remain."""
    m = _manifest({
        "KDB/wiki/summaries/alpha.md": _page_record(
            slug="alpha", page_type="summary", cites=[SOURCE_ID], outgoing=["linked-1", "linked-2"],
        ),
        "KDB/wiki/concepts/beta.md":   _page_record(slug="beta",  cites=[SOURCE_ID]),
        "KDB/wiki/concepts/gamma.md":  _page_record(slug="gamma", cites=[SOURCE_ID]),
        "KDB/wiki/concepts/linked-1.md": _page_record(slug="linked-1"),
        "KDB/wiki/concepts/linked-2.md": _page_record(slug="linked-2"),
    })
    snap = build_context_snapshot(m, source_id=SOURCE_ID, source_text="", page_cap=3)
    assert sorted(p.slug for p in snap.pages) == ["alpha", "beta", "gamma"]


# ---------- empty / malformed manifest ----------

def test_empty_manifest_yields_empty_snapshot() -> None:
    snap = build_context_snapshot({}, source_id=SOURCE_ID, source_text="anything")
    assert isinstance(snap, ContextSnapshot)
    assert snap.source_id == SOURCE_ID
    assert snap.pages == []


def test_manifest_missing_pages_key_yields_empty_snapshot() -> None:
    snap = build_context_snapshot({"schema_version": "1.0"}, source_id=SOURCE_ID, source_text="")
    assert snap.pages == []


def test_malformed_page_records_skipped() -> None:
    m = _manifest({
        "KDB/wiki/summaries/good.md": _page_record(slug="good", page_type="summary", cites=[SOURCE_ID]),
        "KDB/wiki/concepts/no-slug.md": {"page_type": "concept", "title": "x", "source_refs": [{"source_id": SOURCE_ID}]},
        "KDB/wiki/concepts/bad-type.md": {"slug": "bad-type", "title": "x", "page_type": "weird", "source_refs": [{"source_id": SOURCE_ID}]},
        "KDB/wiki/concepts/non-dict.md": "not-a-dict",
    })
    snap = build_context_snapshot(m, source_id=SOURCE_ID, source_text="")
    assert [p.slug for p in snap.pages] == ["good"]


# ---------- projection: drop leaky fields ----------

def test_context_page_exposes_only_four_fields() -> None:
    """ContextPage has exactly {slug, title, page_type, outgoing_links}.
    Asserts dataclass field names — the body-free invariant is type-enforced."""
    field_names = {f.name for f in dataclasses.fields(ContextPage)}
    assert field_names == {"slug", "title", "page_type", "outgoing_links"}


def test_snapshot_pages_have_no_body_or_paths() -> None:
    m = _manifest({
        "KDB/wiki/summaries/foo.md": _page_record(
            slug="foo", page_type="summary", cites=[SOURCE_ID],
            body="SECRET BODY" * 100,
        ),
    })
    snap = build_context_snapshot(m, source_id=SOURCE_ID, source_text="")
    blob = str(snap.to_dict())
    assert "SECRET BODY" not in blob
    assert "KDB/wiki/summaries/foo.md" not in blob
    assert "2026-04-01T00:00:00Z" not in blob
    assert "source_refs" not in blob


# ---------- determinism ----------

def test_ordering_is_deterministic() -> None:
    """Same inputs with shuffled manifest key order -> same snapshot."""
    base_pages = {
        "KDB/wiki/summaries/apple.md":  _page_record(slug="apple", page_type="summary", cites=[SOURCE_ID], outgoing=["cherry"]),
        "KDB/wiki/concepts/cherry.md":  _page_record(slug="cherry"),
        "KDB/wiki/concepts/banana.md":  _page_record(slug="banana", cites=[SOURCE_ID]),
    }
    m1 = _manifest(dict(base_pages))
    m2 = _manifest({k: base_pages[k] for k in sorted(base_pages, reverse=True)})
    s1 = build_context_snapshot(m1, source_id=SOURCE_ID, source_text="")
    s2 = build_context_snapshot(m2, source_id=SOURCE_ID, source_text="")
    assert [p.slug for p in s1.pages] == [p.slug for p in s2.pages]
    assert [p.slug for p in s1.pages] == ["apple", "banana", "cherry"]

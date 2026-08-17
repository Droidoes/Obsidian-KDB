"""Ledger: upsert/identity/delete semantics + FTS search over paragraphs."""
from __future__ import annotations

import pytest

from kdb_fts import ledger


def _rec(article_id: str, path: str, sha: str, paras: list[str], **kw) -> ledger.ArticleRecord:
    base = dict(
        article_id=article_id, path=path, content_sha256=sha,
        title="T", raw_author="A", author_id=None, published_date=None,
        source_url=None, content_kind="article", word_count=sum(len(p.split()) for p in paras),
        cleanliness="ok", paragraphs=paras,
    )
    base.update(kw)
    return ledger.ArticleRecord(**base)


def test_upsert_then_move_keeps_identity(tmp_path):
    conn = ledger.connect(tmp_path / "fts")
    ledger.upsert_article(conn, _rec("g1", "KDB/raw/x/a.md", "sha1", ["hello world"]), "run1")
    # same gmail id, new path (a move): one row, path updated
    ledger.upsert_article(conn, _rec("g1", "KDB/raw/y/a.md", "sha1", ["hello world"]), "run2")
    rows = conn.execute("SELECT article_id, path, first_seen_run, last_seen_run FROM articles").fetchall()
    assert rows == [("g1", "KDB/raw/y/a.md", "run1", "run2")]


def test_paragraphs_replaced_only_on_content_change(tmp_path):
    conn = ledger.connect(tmp_path / "fts")
    ledger.upsert_article(conn, _rec("g1", "p.md", "sha1", ["alpha", "beta"]), "run1")
    ledger.upsert_article(conn, _rec("g1", "p.md", "sha1", ["alpha", "beta"]), "run2")
    # unchanged hash → paragraphs untouched (still the originals, no dup)
    assert conn.execute("SELECT COUNT(*) FROM paragraphs").fetchone()[0] == 2
    ledger.upsert_article(conn, _rec("g1", "p.md", "sha2", ["gamma"]), "run3")
    paras = conn.execute("SELECT paragraph_id, body FROM paragraphs").fetchall()
    assert paras == [("p0001", "gamma")]


def test_delete_absent_cascades(tmp_path):
    conn = ledger.connect(tmp_path / "fts")
    ledger.upsert_article(conn, _rec("g1", "a.md", "s1", ["keep me"]), "run1")
    ledger.upsert_article(conn, _rec("g2", "b.md", "s2", ["drop me"]), "run1")
    assert ledger.delete_absent(conn, {"g1"}) == 1
    assert conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM paragraphs").fetchone()[0] == 1


def test_search_finds_body_term(tmp_path):
    conn = ledger.connect(tmp_path / "fts")
    ledger.upsert_article(conn, _rec("g1", "a.md", "s1", ["Barrick Gold trades below book value"], title="Miners"), "run1")
    ledger.upsert_article(conn, _rec("g2", "b.md", "s2", ["unrelated politics essay"]), "run1")
    ledger.rebuild_fts(conn)
    hits = ledger.search(conn, "Barrick")
    assert [h["article_id"] for h in hits] == ["g1"]
    assert "Barrick" in hits[0]["snippet"]


def test_search_malformed_query_raises_valueerror(tmp_path):
    conn = ledger.connect(tmp_path / "fts")
    ledger.rebuild_fts(conn)
    with pytest.raises(ValueError):
        ledger.search(conn, '"unterminated')


def test_fts_indexes_canonical_author_name(tmp_path):
    """Final-review Phase-1 note: FTS author column is the canonical name
    (falling back to raw when unmapped), not always the raw string."""
    from kdb_fts import author_map, intake

    (tmp_path / "author_map.yaml").write_text(
        'John Q. Puberman: {canonical: "John Puberman"}\n', encoding="utf-8"
    )
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "a.md").write_text(
        "---\ntitle: Zebra Thesis\nauthor: John Q. Puberman\n---\n\n"
        + "word " * 60, encoding="utf-8")
    conn = ledger.connect(tmp_path)
    intake.run_intake(conn, raw, "run-1", state_root=tmp_path)
    hits = ledger.search(conn, "Puberman")
    assert hits and hits[0]["author"] == "John Puberman"

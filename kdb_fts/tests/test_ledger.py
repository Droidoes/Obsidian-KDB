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


def _seed_gated(conn, tmp_path, articles):
    """articles: list of (gid, topic, signal, exploration, extract_ideas, extract_lessons)."""
    from kdb_fts import intake
    raw = tmp_path / "raw"
    raw.mkdir(exist_ok=True)
    for (gid, topic, sig, exp, ei, el) in articles:
        (raw / f"{gid}.md").write_text(
            f"---\ntitle: {gid}\nauthor: A\ngmail_message_id: {gid}\n---\n\n" + "body " * 60,
            encoding="utf-8")
    intake.run_intake(conn, raw, "seed", state_root=tmp_path)
    for (gid, topic, sig, exp, ei, el) in articles:
        ledger.insert_gate_verdict(conn, article_id=gid, run_id="r1", topic=topic,
                                   signal=sig, extract_ideas=ei, extract_lessons=el,
                                   exploration=exp, confidence=None, rationale="",
                                   model="m", prompt_version="gate_v1",
                                   input_tokens=0, output_tokens=0)


def test_triggered_articles_union_exploration(tmp_path):
    conn = ledger.connect(tmp_path)
    _seed_gated(conn, tmp_path, [
        ("inv", "investment", 0.5, 0, True, False),   # accepted (topic clause)
        ("fe",  "finance-econ", 0.5, 0, False, True),  # accepted (topic clause)
        ("sig", "other", 0.9, 0, False, False),        # accepted (signal clause)
        ("geo", "geopolitics", 0.1, 0, False, False),  # ineligible, no exploration
        ("exp", "geopolitics", 0.1, 1, False, False),  # ineligible + exploration
    ])
    got = {r["article_id"] for r in ledger.triggered_articles(conn)}
    assert got == {"inv", "fe", "sig", "exp"}   # geo excluded


def test_article_paragraphs_ordered(tmp_path):
    conn = ledger.connect(tmp_path)
    _seed_gated(conn, tmp_path, [("inv", "investment", 0.5, 0, True, False)])
    paras = ledger.article_paragraphs(conn, "inv")
    assert [p[0] for p in paras] == ["p0001"]


def test_insert_span_refuses_non_substring(tmp_path):
    conn = ledger.connect(tmp_path)
    _seed_gated(conn, tmp_path, [("inv", "investment", 0.5, 0, True, False)])
    with pytest.raises(ledger.SpanProofError):
        ledger.insert_span(conn, article_id="inv", record_type="idea", record_id=1,
                           field="thesis", paragraph_id="p0001", exact_quote="NOT IN SOURCE")


def test_commit_extraction_article_atomic_rolls_back(tmp_path):
    conn = ledger.connect(tmp_path)
    _seed_gated(conn, tmp_path, [("inv", "investment", 0.5, 0, True, False)])
    with pytest.raises(ledger.SpanProofError):
        ledger.commit_extraction_article(
            conn, article_id="inv", run_id="r1", schema_version="extract_v1", model="m",
            prompt_version="extract_v1",
            statuses=[{"status": "ok", "chunk_index": 0, "n_chunks": 1, "n_mentions": 1,
                       "n_cards": 0, "expect_ideas": True, "expect_lessons": False,
                       "input_tokens": 0, "output_tokens": 0}],
            mentions=[{"company": "X", "stance": "long", "thesis": "buy",
                       "spans": [{"field": "thesis", "paragraph_id": "p0001",
                                  "exact_quote": "bogus"}]}],
            cards=[])
    # rollback: the failed txn left no extraction_runs row and no mention row
    assert conn.execute("SELECT COUNT(*) FROM extraction_runs").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM idea_mentions").fetchone()[0] == 0

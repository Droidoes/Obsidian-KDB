# kdb_fts Phase 0 — Package + Intake + FTS Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the `kdb_fts` package skeleton with deterministic intake of the gmail-substack raw tree into a SQLite ledger (stable identity, cleanliness classification, paragraph IDs, author map) and a full-text search surface — **no LLM calls, no cost**.

**Architecture:** Phase 0 of blueprint [`../specs/2026-08-16-task145-kdb-fts-blueprint-v0.1.md`](../specs/2026-08-16-task145-kdb-fts-blueprint-v0.1.md). New top-level package `kdb_fts/` importing `common` only; all state under `<vault>/KDB/fts/` (env override `KDB_FTS_PATH`); SQLite via stdlib `sqlite3` with a numbered-migration runner; FTS5 rebuilt from scratch on each intake. Raw sources are read-only to this package (D3).

**Scope note:** This plan covers **Phase 0 only**. Phases 1–5 (gate, extraction, ranker, feedback app, steady state) each get their own plan when the preceding phase gate passes — they are live-LLM phases with Joseph-fired gates.

**Tech Stack:** Python 3.10+, stdlib `sqlite3` (FTS5), `yaml` (existing dep), `common.paths` / `common.source_io` / `common.atomic_io` (existing leaf utilities).

## Global Constraints

- `kdb_fts` imports **no internal package except `common`** (AST-guarded; blueprint D2).
- **Nothing else imports `kdb_fts`** in v1 (AST-guarded).
- All writes resolve under `state_root()` (= `$KDB_FTS_PATH` else `<vault>/KDB/fts/`) or a test tmp dir — mechanically guarded (D3/D4). **kdb_fts never writes** the wiki, manifest, graph, pipeline configs, feeder state, or raw sources.
- File writes go through `common.atomic_io`; **direct `open(..., "w"/"a"/"x")` is forbidden** in `kdb_fts`.
- **`sqlite3.connect` appears in `kdb_fts/ledger.py` only.**
- Identity: `article_id` = `gmail_message_id` from frontmatter, else `"sha256:" + sha256(file text)`; never the file path (D17).
- Skip-by-rule classes (D16): `content_kind` in `{video, podcast}`; body < 50 words; "Weekly Stack" digest stubs; frontmatter-bleed files (repaired *view* only — original bytes untouched).
- Cleanliness precedence (exactly one label per file): `digest-stub` > `media` > `bleed` > `short` > `ok`.
- Conventional commits with task id: `feat(kdb-fts): #145 P0 — …`. **Commit steps require Joseph's explicit go-ahead** (standing repo gate); executor pauses at each commit step until told.
- Python 3.10+ type hints (`list[str]`, `str | None`), 4-space indent, `snake_case` modules, tests in `kdb_fts/tests/test_<module>.py`.

---

### Task 1: Package skeleton, boundary guards, wiring

**Files:**
- Create: `kdb_fts/__init__.py`
- Create: `kdb_fts/tests/__init__.py` (empty)
- Create: `kdb_fts/tests/test_skeleton.py`
- Modify: `tools/tests/test_package_boundaries.py` (INTERNAL set, ALLOWED row, new reverse test)
- Modify: `pyproject.toml` (packages.find include, testpaths, script entry)
- Modify: `conftest.py` (add fts isolation fixture)

**Interfaces:**
- Produces: package `kdb_fts` importable; entry point `kdb-fts = kdb_fts.cli:main` (cli.py arrives in Task 7 — the entry point is declared now, resolved then); env var `KDB_FTS_PATH` reserved for state-root override.

- [ ] **Step 1: Write the failing tests**

`kdb_fts/tests/test_skeleton.py`:

```python
"""Phase 0 smoke: package imports, and nothing internal leaks in/out."""
from __future__ import annotations


def test_package_imports():
    import kdb_fts

    assert kdb_fts.__doc__ is not None
```

Add to `tools/tests/test_package_boundaries.py`:

```python
def test_nothing_imports_kdb_fts():
    """v1: kdb_fts is a leaf producer — no internal package may import it (D2)."""
    for pkg in sorted(INTERNAL - {"kdb_fts"}):
        if not (ROOT / pkg).is_dir():
            continue
        offenders = _top_level_imports(pkg) & {"kdb_fts"}
        assert not offenders, f"{pkg} must not import kdb_fts (reads exports instead)"
```

And extend the two existing structures in the same file:

- `INTERNAL` set: add `"kdb_fts"`.
- `ALLOWED` dict: add row `"kdb_fts": {"common"},` with comment `# #145: parallel extraction system; leaf producer over common only`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest kdb_fts/tests/test_skeleton.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'kdb_fts'`

Run: `pytest tools/tests/test_package_boundaries.py -v`
Expected: `test_package_dependency_contract[kdb_fts-...]` FAILS (package dir missing → `rglob` on missing dir yields empty, so this may actually pass — the skeleton test is the real failing gate here; the parametrized contract passes trivially until code exists, which is correct: it guards drift, not absence).

- [ ] **Step 3: Create the skeleton**

`kdb_fts/__init__.py`:

```python
"""kdb_fts — parallel extraction/ranking system over raw source corpora (#145).

Substrate-parallel to kdb_graph: reads KDB/raw trees, keeps its own state
under <vault>/KDB/fts/ (ledger.sqlite + FTS5), writes nothing else (D3/D4).
Imports `common` only; nothing internal imports this package in v1.
"""
from __future__ import annotations
```

`kdb_fts/tests/__init__.py`: empty file.

`pyproject.toml` edits:

- `[project.scripts]`: add line `kdb-fts               = "kdb_fts.cli:main"`
- `[tool.setuptools.packages.find] include`: add `"kdb_fts*"` to the list.
- `[tool.pytest.ini_options] testpaths`: add `"kdb_fts/tests"` to the list.

`conftest.py` — append a second autouse fixture:

```python
@pytest.fixture(autouse=True)
def _isolate_fts_dir(tmp_path, monkeypatch):
    """Redirect KDB_FTS_PATH to a per-test tmp dir — mirrors _isolate_graph_dir."""
    monkeypatch.setenv("KDB_FTS_PATH", str(tmp_path / "fts_isolated"))
    yield
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest kdb_fts/tests/test_skeleton.py tools/tests/test_package_boundaries.py -v`
Expected: all PASS (including the new parametrized `kdb_fts` row and `test_nothing_imports_kdb_fts`).

Run: `pip install -e ".[dev]"` then `kdb-fts --help 2>&1 | head -2 || true`
Expected: install succeeds; `kdb-fts` fails with `ModuleNotFoundError: kdb_fts.cli` (Task 7 resolves).

- [ ] **Step 5: Commit (gate: Joseph's go-ahead)**

```bash
git add kdb_fts/ tools/tests/test_package_boundaries.py pyproject.toml conftest.py
git commit -m "feat(kdb-fts): #145 P0 — package skeleton + boundary guards"
```

---

### Task 2: State root + SQLite schema with migrations

**Files:**
- Create: `kdb_fts/state.py`
- Create: `kdb_fts/schema.py`
- Test: `kdb_fts/tests/test_schema.py`

**Interfaces:**
- Produces: `state.state_root() -> Path`; `schema.SCHEMA_VERSION: int`; `schema.MIGRATIONS: dict[int, str]`; `schema.current_version(conn) -> int`; `schema.migrate(conn) -> None`. Tables created by migration 1: `meta`, `articles`, `paragraphs`, `authors`, `author_aliases`, `articles_fts` (FTS5). Task 3's ledger consumes all of these.

**Deviation from blueprint §4 (approved shapes only):** blueprint listed no `state.py`; state-root resolution needs a home and `ledger.py` is declared the *sqlite* writer, so `state_root()` gets its own tiny module. Blueprint layout otherwise unchanged.

- [ ] **Step 1: Write the failing tests**

`kdb_fts/tests/test_schema.py`:

```python
"""Schema: fresh DB migrates to latest; migrate is idempotent; env override wins."""
from __future__ import annotations

import sqlite3

from kdb_fts import schema, state


def test_state_root_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv("KDB_FTS_PATH", str(tmp_path / "custom"))
    assert state.state_root() == (tmp_path / "custom").resolve()


def test_state_root_default(monkeypatch, tmp_path):
    monkeypatch.delenv("KDB_FTS_PATH", raising=False)
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(tmp_path / "vault"))
    assert state.state_root() == (tmp_path / "vault" / "KDB" / "fts").resolve()


def test_fresh_db_migrates_to_latest():
    conn = sqlite3.connect(":memory:")
    schema.migrate(conn)
    assert schema.current_version(conn) == schema.SCHEMA_VERSION
    tables = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table','virtual table')"
            # sqlite_master records FTS5 shadow tables as type 'table'
        )
    }
    for expected in ("meta", "articles", "paragraphs", "authors", "author_aliases"):
        assert expected in tables, f"missing table {expected}"
    fts = conn.execute(
        "SELECT sql FROM sqlite_master WHERE name = 'articles_fts'"
    ).fetchone()
    assert fts is not None and "fts5" in fts[0].lower()


def test_migrate_is_idempotent():
    conn = sqlite3.connect(":memory:")
    schema.migrate(conn)
    schema.migrate(conn)  # second run: no-op, no error
    assert schema.current_version(conn) == schema.SCHEMA_VERSION
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest kdb_fts/tests/test_schema.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'kdb_fts.state'`

- [ ] **Step 3: Implement**

`kdb_fts/state.py`:

```python
"""state — kdb_fts state-root resolution (D4).

One self-contained subtree: <vault>/KDB/fts/ (or $KDB_FTS_PATH). Mirrors the
KDB_GRAPH_PATH pattern so tests isolate via env (root conftest does this).
"""
from __future__ import annotations

import os
from pathlib import Path

from common import paths

ENV_VAR = "KDB_FTS_PATH"


def state_root() -> Path:
    """Resolve the kdb_fts state root: $KDB_FTS_PATH else <vault>/KDB/fts."""
    env = os.environ.get(ENV_VAR)
    root = Path(env).expanduser() if env else paths.kdb_root() / "fts"
    return root.resolve()
```

`kdb_fts/schema.py`:

```python
"""schema — SQLite DDL + numbered migrations for the kdb_fts ledger.

Phase 0 (migration 1): articles / paragraphs / authors / author_aliases /
articles_fts. Gate, extraction, feedback, and ranker tables arrive as later
migrations in their own phases (D14: re-extraction never rewrites identity).
"""
from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 1

MIGRATIONS: dict[int, str] = {
    1: """
    CREATE TABLE meta (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    CREATE TABLE articles (
        article_id     TEXT PRIMARY KEY,  -- gmail_message_id else 'sha256:'+hash (D17)
        path           TEXT NOT NULL,      -- mutable attribute, never identity
        content_sha256 TEXT NOT NULL,
        title          TEXT,
        raw_author     TEXT,
        author_id      INTEGER REFERENCES authors(author_id),
        published_date TEXT,
        source_url     TEXT,
        content_kind   TEXT,
        word_count     INTEGER NOT NULL,
        cleanliness    TEXT NOT NULL,      -- ok|short|media|digest-stub|bleed|repaired
        first_seen_run TEXT NOT NULL,
        last_seen_run  TEXT NOT NULL
    );
    CREATE TABLE paragraphs (
        article_id   TEXT NOT NULL REFERENCES articles(article_id) ON DELETE CASCADE,
        paragraph_id TEXT NOT NULL,          -- p0001… stable within one content hash
        body         TEXT NOT NULL,
        PRIMARY KEY (article_id, paragraph_id)
    );
    CREATE TABLE authors (
        author_id       INTEGER PRIMARY KEY,
        canonical_name  TEXT NOT NULL UNIQUE,
        publication     TEXT,
        explicit_rating REAL,              -- nullable; wins when set (D9a)
        derived_score   REAL
    );
    CREATE TABLE author_aliases (
        raw_string TEXT PRIMARY KEY,
        author_id  INTEGER NOT NULL REFERENCES authors(author_id)
    );
    CREATE VIRTUAL TABLE articles_fts USING fts5(
        article_id UNINDEXED,
        title,
        author,
        body
    );
    """,
}


def current_version(conn: sqlite3.Connection) -> int:
    """Schema version of an open connection; 0 for a brand-new database."""
    try:
        row = conn.execute(
            "SELECT value FROM meta WHERE key = 'schema_version'"
        ).fetchone()
    except sqlite3.OperationalError:  # meta table does not exist yet
        return 0
    return int(row[0]) if row else 0


def migrate(conn: sqlite3.Connection) -> None:
    """Apply all pending migrations in order. Idempotent."""
    for version in range(current_version(conn) + 1, SCHEMA_VERSION + 1):
        conn.executescript(MIGRATIONS[version])
        conn.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES ('schema_version', ?)",
            (str(version),),
        )
        conn.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest kdb_fts/tests/test_schema.py -v`
Expected: 4 PASS

- [ ] **Step 5: Commit (gate)**

```bash
git add kdb_fts/state.py kdb_fts/schema.py kdb_fts/tests/test_schema.py
git commit -m "feat(kdb-fts): #145 P0 — state root + SQLite schema migration 1"
```

---

### Task 3: Ledger — typed DB access layer

**Files:**
- Create: `kdb_fts/ledger.py`
- Test: `kdb_fts/tests/test_ledger.py`

**Interfaces:**
- Consumes: `schema.migrate`, `state.state_root` (Task 2).
- Produces (Task 4+ rely on these):
  - `ledger.ArticleRecord` dataclass — fields: `article_id: str`, `path: str`, `content_sha256: str`, `title: str | None`, `raw_author: str | None`, `author_id: int | None`, `published_date: str | None`, `source_url: str | None`, `content_kind: str | None`, `word_count: int`, `cleanliness: str`, `paragraphs: list[str]`.
  - `ledger.connect(root: Path | None = None) -> sqlite3.Connection` — creates state dir, runs migrations, enables foreign keys.
  - `ledger.upsert_article(conn, rec: ArticleRecord, run_id: str) -> None` — insert or update; replaces that article's paragraph rows when the content hash changed.
  - `ledger.delete_absent(conn, present_ids: set[str]) -> int` — delete articles (and their paragraphs) not in `present_ids`; returns count deleted.
  - `ledger.rebuild_fts(conn) -> None` — full FTS5 repopulation from `articles` + `paragraphs`.
  - `ledger.search(conn, query: str, limit: int = 20) -> list[dict]` — keys `article_id`, `title`, `author`, `snippet`; raises `ValueError` on malformed MATCH syntax.

- [ ] **Step 1: Write the failing tests**

`kdb_fts/tests/test_ledger.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest kdb_fts/tests/test_ledger.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'kdb_fts.ledger'`

- [ ] **Step 3: Implement**

`kdb_fts/ledger.py`:

```python
"""ledger — typed DB access; the ONLY module that opens ledger.sqlite (D3/D4).

Every sqlite3.connect in kdb_fts lives here (write-boundary guard R1).
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from kdb_fts import schema, state

_DB_NAME = "ledger.sqlite"


@dataclass
class ArticleRecord:
    article_id: str
    path: str
    content_sha256: str
    title: str | None
    raw_author: str | None
    author_id: int | None
    published_date: str | None
    source_url: str | None
    content_kind: str | None
    word_count: int
    cleanliness: str
    paragraphs: list[str] = field(default_factory=list)


def connect(root: Path | None = None) -> sqlite3.Connection:
    """Open (creating if needed) the ledger under the state root; migrate."""
    root = (root or state.state_root())
    root.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(root / _DB_NAME)
    conn.execute("PRAGMA foreign_keys = ON")
    schema.migrate(conn)
    return conn


def upsert_article(conn: sqlite3.Connection, rec: ArticleRecord, run_id: str) -> None:
    """Insert or refresh one article. Paragraphs are replaced only when the
    content hash changed; first_seen_run is sticky, last_seen_run advances."""
    existing = conn.execute(
        "SELECT content_sha256 FROM articles WHERE article_id = ?",
        (rec.article_id,),
    ).fetchone()
    if existing is None:
        conn.execute(
            """INSERT INTO articles
               (article_id, path, content_sha256, title, raw_author, author_id,
                published_date, source_url, content_kind, word_count, cleanliness,
                first_seen_run, last_seen_run)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (rec.article_id, rec.path, rec.content_sha256, rec.title, rec.raw_author,
             rec.author_id, rec.published_date, rec.source_url, rec.content_kind,
             rec.word_count, rec.cleanliness, run_id, run_id),
        )
        _replace_paragraphs(conn, rec)
    else:
        conn.execute(
            """UPDATE articles SET path=?, content_sha256=?, title=?, raw_author=?,
               author_id=?, published_date=?, source_url=?, content_kind=?,
               word_count=?, cleanliness=?, last_seen_run=?
               WHERE article_id=?""",
            (rec.path, rec.content_sha256, rec.title, rec.raw_author, rec.author_id,
             rec.published_date, rec.source_url, rec.content_kind, rec.word_count,
             rec.cleanliness, run_id, rec.article_id),
        )
        if existing[0] != rec.content_sha256:
            _replace_paragraphs(conn, rec)
    conn.commit()


def _replace_paragraphs(conn: sqlite3.Connection, rec: ArticleRecord) -> None:
    conn.execute("DELETE FROM paragraphs WHERE article_id = ?", (rec.article_id,))
    conn.executemany(
        "INSERT INTO paragraphs(article_id, paragraph_id, body) VALUES (?,?,?)",
        [(rec.article_id, f"p{i:04d}", body) for i, body in enumerate(rec.paragraphs, 1)],
    )


def delete_absent(conn: sqlite3.Connection, present_ids: set[str]) -> int:
    """Delete articles (and cascaded paragraphs) whose ids are not present."""
    rows = conn.execute("SELECT article_id FROM articles").fetchall()
    stale = [r[0] for r in rows if r[0] not in present_ids]
    conn.executemany("DELETE FROM articles WHERE article_id = ?", [(a,) for a in stale])
    conn.commit()
    return len(stale)


def rebuild_fts(conn: sqlite3.Connection) -> None:
    """Full FTS5 repopulation (cheap at 4.2M words; keeps index logic trivial)."""
    conn.execute("DELETE FROM articles_fts")
    conn.execute(
        """INSERT INTO articles_fts(article_id, title, author, body)
           SELECT a.article_id, COALESCE(a.title, ''), COALESCE(a.raw_author, ''),
                  COALESCE((SELECT GROUP_CONCAT(p.body, char(10)||char(10))
                            FROM paragraphs p WHERE p.article_id = a.article_id), '')
           FROM articles a"""
    )
    conn.commit()


def search(conn: sqlite3.Connection, query: str, limit: int = 20) -> list[dict]:
    """FTS5 MATCH over title/author/body; bm25 order; snippet from body."""
    try:
        rows = conn.execute(
            """SELECT article_id, title, author,
                      snippet(articles_fts, 3, '**', '**', '…', 12) AS snip
               FROM articles_fts WHERE articles_fts MATCH ?
               ORDER BY rank LIMIT ?""",
            (query, limit),
        ).fetchall()
    except sqlite3.OperationalError as e:
        raise ValueError(f"malformed FTS5 query {query!r}: {e}") from e
    return [
        {"article_id": r[0], "title": r[1], "author": r[2], "snippet": r[3]}
        for r in rows
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest kdb_fts/tests/test_ledger.py -v`
Expected: 5 PASS

- [ ] **Step 5: Commit (gate)**

```bash
git add kdb_fts/ledger.py kdb_fts/tests/test_ledger.py
git commit -m "feat(kdb-fts): #145 P0 — ledger access layer (upsert/delete/FTS)"
```

---

### Task 4: Intake — deterministic walk, classification, identity

**Files:**
- Create: `kdb_fts/intake.py`
- Create: `tests/fixtures/fts_tree/` fixture files (see Step 1)
- Test: `kdb_fts/tests/test_intake.py`

**Interfaces:**
- Consumes: `ledger.ArticleRecord`, `ledger.upsert_article`, `ledger.delete_absent`, `ledger.rebuild_fts` (Task 3); `common.source_io.parse_existing_frontmatter`.
- Produces:
  - `intake.scan_tree(raw_root: Path) -> list[ledger.ArticleRecord]` — pure walk + classify, no DB.
  - `intake.run_intake(conn, raw_root: Path, run_id: str) -> dict` — scan + upsert + delete_absent + rebuild_fts; returns stats dict with keys `seen`, `upserted`, `deleted`, `by_cleanliness` (dict), `by_content_kind` (dict), `raw_author_strings` (int).
  - Classification rules (constants): `intake.DIGEST_TITLE_RE`, `intake.SHORT_WORD_FLOOR = 50`, `intake.MEDIA_KINDS = {"video", "podcast"}`.
  - Author wiring (Task 5) slots into `run_intake` via `author_id` resolution — Task 4 leaves `author_id=None`.

- [ ] **Step 1: Create fixtures + failing tests**

Fixture tree under `tests/fixtures/fts_tree/` (repo-shared fixture dir; reusable by later phases):

`tests/fixtures/fts_tree/plain-article.md`:

```markdown
---
title: 'Barrick: Settlement Clears the Path'
author: Damodaran
published_date: '2026-07-01'
source_url: https://example.substack.com/p/barrick
gmail_message_id: g-fixture-001
content_kind: article
feeder: gmail-substack
---

Barrick Gold trades below book value today. The settlement removes the overhang on the stock and clears the path for a re-rating over the next twelve months.

Management reiterated production guidance, the balance sheet carries little debt, and the dividend is well covered by free cash flow even at lower gold prices.
```

(52 body words — must stay ≥ 50 so this fixture is the `ok` exemplar, not `short`.)

`tests/fixtures/fts_tree/weekly-stack-digest.md`:

```markdown
---
title: '"0DTE: What the Pros Are Really Doing" and 4 more'
author: Substack
published_date: '2026-06-26'
gmail_message_id: g-fixture-002
content_kind: article
---

Your Weekly Stack has arrived.
```

`tests/fixtures/fts_tree/video-note.md`:

```markdown
---
title: 'Interview: Macro Outlook'
author: Some Channel
gmail_message_id: g-fixture-003
content_kind: video
---

Transcript link only.
```

`tests/fixtures/fts_tree/short-note.md`:

```markdown
---
title: 'Quick hit'
author: Damodaran
gmail_message_id: g-fixture-004
content_kind: article
---

One line only.
```

`tests/fixtures/fts_tree/bleed-file.md` (note: **broken YAML** — the colon-less line makes the frontmatter block unparseable):

```markdown
---
title: 'Bleedy'
author broken line here
---

Actual body text lives after the broken fence.
```

`tests/fixtures/fts_tree/_promo/promo.md`:

```markdown
---
title: 'Promo blast'
gmail_message_id: g-fixture-005
content_kind: article
---

Buy the course now and learn more today.
```

`kdb_fts/tests/test_intake.py`:

```python
"""Intake: classification precedence, identity, idempotency over the fixture tree."""
from __future__ import annotations

from pathlib import Path

from kdb_fts import intake, ledger

FIXTURE = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "fts_tree"


def _by_id(recs):
    return {r.article_id: r for r in recs}


def test_scan_classifies_each_fixture():
    recs = _by_id(intake.scan_tree(FIXTURE))
    assert "g-fixture-005" not in recs  # _promo/ excluded from the walk entirely
    assert recs["g-fixture-001"].cleanliness == "ok"
    assert recs["g-fixture-002"].cleanliness == "digest-stub"
    assert recs["g-fixture-003"].cleanliness == "media"
    assert recs["g-fixture-004"].cleanliness == "short"
    assert recs["g-fixture-001"].word_count == 52  # 27 words + 25 words, two paragraphs


def test_bleed_file_gets_repaired_view():
    recs = intake.scan_tree(FIXTURE)
    bleeds = [r for r in recs if r.cleanliness == "bleed"]
    assert len(bleeds) == 1
    assert bleeds[0].article_id.startswith("sha256:")  # no parseable gmail id → hash identity
    assert bleeds[0].paragraphs == ["Actual body text lives after the broken fence."]


def test_run_intake_is_idempotent(tmp_path):
    conn = ledger.connect(tmp_path / "fts")
    stats1 = intake.run_intake(conn, FIXTURE, "run1")
    stats2 = intake.run_intake(conn, FIXTURE, "run2")
    assert stats1["seen"] == 5  # 5 fixture files outside _promo/
    assert stats2["seen"] == 5 and stats2["deleted"] == 0
    # paragraphs are NOT rewritten on unchanged content:
    n_paras = conn.execute("SELECT COUNT(*) FROM paragraphs").fetchone()[0]
    intake.run_intake(conn, FIXTURE, "run3")
    assert conn.execute("SELECT COUNT(*) FROM paragraphs").fetchone()[0] == n_paras


def test_identity_survives_move(tmp_path, monkeypatch):
    conn = ledger.connect(tmp_path / "fts")
    intake.run_intake(conn, FIXTURE, "run1")
    moved = tmp_path / "tree2"
    import shutil
    shutil.copytree(FIXTURE, moved)
    (moved / "plain-article.md").rename(moved / "renamed-article.md")
    intake.run_intake(conn, moved, "run2")
    row = conn.execute(
        "SELECT path FROM articles WHERE article_id = 'g-fixture-001'"
    ).fetchone()
    assert row[0].endswith("renamed-article.md")
```

Wait — fixture count check: 5 article fixtures + 1 in `_promo/`. `seen` counts walked files excluding `_promo` → 5? Listed above: plain-article, weekly-stack-digest, video-note, short-note, bleed-file = 5 files outside `_promo`. Fix the test expectations accordingly (ids: 001–004 have gmail ids; bleed has hash identity).

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest kdb_fts/tests/test_intake.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'kdb_fts.intake'`

- [ ] **Step 3: Implement**

`kdb_fts/intake.py`:

```python
"""intake — deterministic walk of a raw source tree (no LLM, D16/D17).

Reads KDB/raw trees read-only; produces ArticleRecords for the ledger.
Cleanliness precedence (one label per file):
    digest-stub > media > bleed > short > ok
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from common.source_io import parse_existing_frontmatter

from kdb_fts import ledger

DIGEST_TITLE_RE = re.compile(r"\band\s+\d+\s+more\b", re.IGNORECASE)
SHORT_WORD_FLOOR = 50
MEDIA_KINDS = frozenset({"video", "podcast"})
_EXCLUDE_DIRS = frozenset({"_promo"})
_BLEED_FENCE_SCAN_LIMIT = 200  # lines to scan for the closing fence


def _word_count(body: str) -> int:
    return len(re.findall(r"\S+", body))


def _split_paragraphs(body: str) -> list[str]:
    """Blank-line split; paragraph i becomes p000i in the ledger (stable per hash)."""
    return [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]


def _repair_bleed(text: str) -> str:
    """Repaired VIEW for frontmatter-bleed files: drop everything through the
    closing fence. Original bytes are never touched (D16)."""
    lines = text.splitlines()
    for i in range(1, min(len(lines), _BLEED_FENCE_SCAN_LIMIT)):
        if lines[i].strip() == "---":
            return "\n".join(lines[i + 1 :])
    return text  # no closing fence found: treat whole file as body


def _identity(fm: dict, text: str) -> str:
    gid = fm.get("gmail_message_id")
    if gid:
        return str(gid)
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def scan_tree(raw_root: Path) -> list[ledger.ArticleRecord]:
    """Walk raw_root for *.md (excluding _EXCLUDE_DIRS), classify, and return
    one ArticleRecord per file. Pure: no DB, no writes."""
    records: list[ledger.ArticleRecord] = []
    for path in sorted(Path(raw_root).rglob("*.md")):
        if _EXCLUDE_DIRS & set(path.relative_to(raw_root).parts[:-1]):
            continue
        text = path.read_text(encoding="utf-8")
        fm, body = parse_existing_frontmatter(text)
        is_bleed = text.lstrip().startswith("---") and not fm
        view = _repair_bleed(text) if is_bleed else body
        title = fm.get("title")
        kind = fm.get("content_kind")
        words = _word_count(view)
        if isinstance(title, str) and DIGEST_TITLE_RE.search(title):
            cleanliness = "digest-stub"
        elif kind in MEDIA_KINDS:
            cleanliness = "media"
        elif is_bleed:
            cleanliness = "bleed"
        elif words < SHORT_WORD_FLOOR:
            cleanliness = "short"
        else:
            cleanliness = "ok"
        records.append(
            ledger.ArticleRecord(
                article_id=_identity(fm, text),
                path=str(path),
                content_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                title=title if isinstance(title, str) else None,
                raw_author=fm.get("author") if isinstance(fm.get("author"), str) else None,
                author_id=None,  # Task 5 wires the author map
                published_date=(
                    str(fm["published_date"]) if fm.get("published_date") else None
                ),
                source_url=fm.get("source_url"),
                content_kind=kind if isinstance(kind, str) else None,
                word_count=words,
                cleanliness=cleanliness,
                paragraphs=_split_paragraphs(view),
            )
        )
    return records


def run_intake(conn, raw_root: Path, run_id: str) -> dict:
    """Scan + upsert + prune + FTS rebuild. Idempotent on an unchanged tree."""
    records = scan_tree(raw_root)
    for rec in records:
        ledger.upsert_article(conn, rec, run_id)
    deleted = ledger.delete_absent(conn, {r.article_id for r in records})
    ledger.rebuild_fts(conn)
    by_cleanliness: dict[str, int] = {}
    by_kind: dict[str, int] = {}
    for r in records:
        by_cleanliness[r.cleanliness] = by_cleanliness.get(r.cleanliness, 0) + 1
        k = r.content_kind or "unknown"
        by_kind[k] = by_kind.get(k, 0) + 1
    return {
        "seen": len(records),
        "upserted": len(records),
        "deleted": deleted,
        "by_cleanliness": by_cleanliness,
        "by_content_kind": by_kind,
        "raw_author_strings": len({r.raw_author for r in records if r.raw_author}),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest kdb_fts/tests/test_intake.py -v`
Expected: 4 PASS

- [ ] **Step 5: Commit (gate)**

```bash
git add kdb_fts/intake.py kdb_fts/tests/test_intake.py tests/fixtures/fts_tree/
git commit -m "feat(kdb-fts): #145 P0 — deterministic intake with cleanliness classes"
```

---

### Task 5: Author map — raw string → canonical author

**Files:**
- Create: `kdb_fts/author_map.py`
- Modify: `kdb_fts/intake.py` (`run_intake` wires author resolution)
- Test: `kdb_fts/tests/test_author_map.py`

**Interfaces:**
- Consumes: `ledger.ArticleRecord` (Task 4).
- Produces:
  - `author_map.load_map(root: Path) -> dict[str, dict[str, str]]` — reads `author_map.yaml` under the state root; `{}` when absent. YAML shape: `raw string: {canonical: Name, publication: Pub}` (`publication` optional).
  - `author_map.resolve(conn, raw: str, mapping) -> int` — get-or-create the canonical author row + alias row; returns `author_id`.
  - `author_map.unmapped(conn) -> list[str]` — raw strings whose canonical equals their own normalization (i.e., no explicit yaml entry) — the list Joseph edits from.
  - Normalization (default canonical when unmapped): `re.sub(r"\s+", " ", raw).strip()`.

- [ ] **Step 1: Write the failing tests**

`kdb_fts/tests/test_author_map.py`:

```python
"""Author map: yaml override, normalization default, unmapped listing."""
from __future__ import annotations

from kdb_fts import author_map, ledger


def test_default_canonical_is_normalized_raw(tmp_path):
    conn = ledger.connect(tmp_path / "fts")
    aid = author_map.resolve(conn, "  Aswath   Damodaran ", {})
    row = conn.execute(
        "SELECT canonical_name, publication FROM authors WHERE author_id = ?", (aid,)
    ).fetchone()
    assert row == ("Aswath Damodaran", None)
    # alias recorded; resolving again reuses the same author
    assert author_map.resolve(conn, "  Aswath   Damodaran ", {}) == aid


def test_yaml_override_maps_alias_to_canonical(tmp_path):
    conn = ledger.connect(tmp_path / "fts")
    mapping = {"Damodaran": {"canonical": "Aswath Damodaran",
                             "publication": "Musings on Markets"}}
    aid = author_map.resolve(conn, "Damodaran", mapping)
    row = conn.execute(
        "SELECT canonical_name, publication FROM authors WHERE author_id = ?", (aid,)
    ).fetchone()
    assert row == ("Aswath Damodaran", "Musings on Markets")
    # and the default-normalized form lands on the SAME author row
    assert author_map.resolve(conn, "Aswath Damodaran", mapping) == aid


def test_load_map_missing_file_returns_empty(tmp_path):
    assert author_map.load_map(tmp_path / "fts") == {}


def test_load_map_roundtrip(tmp_path):
    root = tmp_path / "fts"
    root.mkdir(parents=True)
    (root / "author_map.yaml").write_text(
        "Damodaran:\n  canonical: Aswath Damodaran\n  publication: Musings on Markets\n"
    )
    assert author_map.load_map(root) == {
        "Damodaran": {"canonical": "Aswath Damodaran", "publication": "Musings on Markets"}
    }


def test_unmapped_lists_only_non_overridden(tmp_path):
    conn = ledger.connect(tmp_path / "fts")
    author_map.resolve(conn, "Damodaran", {"Damodaran": {"canonical": "Aswath Damodaran"}})
    author_map.resolve(conn, "Mystery Writer", {})
    assert author_map.unmapped(conn) == ["Mystery Writer"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest kdb_fts/tests/test_author_map.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'kdb_fts.author_map'`

- [ ] **Step 3: Implement**

`kdb_fts/author_map.py`:

```python
"""author_map — raw author string → canonical author/publication (yaml).

author_map.yaml lives under the state root and is Joseph-editable config.
Unmapped strings never block intake: they default to their normalized form
and are listed by unmapped() for Joseph to curate (§6 blueprint).
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import yaml


def _normalize(raw: str) -> str:
    return re.sub(r"\s+", " ", raw).strip()


def load_map(root: Path) -> dict[str, dict[str, str]]:
    path = Path(root) / "author_map.yaml"
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {str(k): dict(v) for k, v in data.items()}


def resolve(conn: sqlite3.Connection, raw: str, mapping: dict[str, dict[str, str]]) -> int:
    """Get-or-create canonical author + alias for one raw string."""
    entry = mapping.get(raw, {})
    canonical = entry.get("canonical") or _normalize(raw)
    publication = entry.get("publication")
    row = conn.execute(
        "SELECT author_id FROM author_aliases WHERE raw_string = ?", (raw,)
    ).fetchone()
    if row:
        return row[0]
    row = conn.execute(
        "SELECT author_id FROM authors WHERE canonical_name = ?", (canonical,)
    ).fetchone()
    if row:
        author_id = row[0]
        if publication:  # enrich existing row if we now know the publication
            conn.execute(
                "UPDATE authors SET publication = COALESCE(publication, ?) WHERE author_id = ?",
                (publication, author_id),
            )
    else:
        cur = conn.execute(
            "INSERT INTO authors(canonical_name, publication) VALUES (?,?)",
            (canonical, publication),
        )
        author_id = cur.lastrowid
    conn.execute(
        "INSERT INTO author_aliases(raw_string, author_id) VALUES (?,?)",
        (raw, author_id),
    )
    conn.commit()
    return author_id


def unmapped(conn: sqlite3.Connection) -> list[str]:
    """Raw strings with no yaml override (canonical == normalized raw).

    Post-filtered in Python (not SQL): SQLite TRIM strips only leading/trailing
    whitespace, while _normalize also collapses internal runs — a SQL-only
    comparison would silently drop exactly the messy strings this list exists
    to surface.
    """
    rows = conn.execute(
        """SELECT al.raw_string, a.canonical_name FROM author_aliases al
           JOIN authors a ON a.author_id = al.author_id
           ORDER BY al.raw_string"""
    ).fetchall()
    return [raw for raw, canonical in rows if canonical == _normalize(raw)]
```

Add to `kdb_fts/tests/test_author_map.py` (pins the internal-whitespace case):

```python
def test_unmapped_includes_internal_whitespace_variant(tmp_path):
    conn = ledger.connect(tmp_path / "fts")
    author_map.resolve(conn, "Aswath  Damodaran", {})  # double internal space
    assert author_map.unmapped(conn) == ["Aswath  Damodaran"]
```

Modify `kdb_fts/intake.py` — add the import at module top and replace `run_intake`
with the author-resolving version (full body, replaces the Task-4 version):

```python
# module top, with the existing imports:
from kdb_fts import author_map, ledger
```

```python
def run_intake(conn, raw_root: Path, run_id: str, state_root: Path | None = None) -> dict:
    """Scan + upsert + prune + FTS rebuild. Idempotent on an unchanged tree.

    state_root: where author_map.yaml lives (None → no overrides applied).
    """
    records = scan_tree(raw_root)
    mapping = author_map.load_map(state_root) if state_root else {}
    for rec in records:
        if rec.raw_author:
            rec.author_id = author_map.resolve(conn, rec.raw_author, mapping)
        ledger.upsert_article(conn, rec, run_id)
    deleted = ledger.delete_absent(conn, {r.article_id for r in records})
    ledger.rebuild_fts(conn)
    by_cleanliness: dict[str, int] = {}
    by_kind: dict[str, int] = {}
    for r in records:
        by_cleanliness[r.cleanliness] = by_cleanliness.get(r.cleanliness, 0) + 1
        k = r.content_kind or "unknown"
        by_kind[k] = by_kind.get(k, 0) + 1
    return {
        "seen": len(records),
        "upserted": len(records),
        "deleted": deleted,
        "by_cleanliness": by_cleanliness,
        "by_content_kind": by_kind,
        "raw_author_strings": len({r.raw_author for r in records if r.raw_author}),
    }
```

Add to `kdb_fts/tests/test_intake.py`:

```python
def test_run_intake_resolves_authors(tmp_path):
    conn = ledger.connect(tmp_path / "fts")
    intake.run_intake(conn, FIXTURE, "run1", state_root=tmp_path / "fts")
    rows = conn.execute(
        "SELECT DISTINCT a.canonical_name FROM articles ar "
        "JOIN authors a ON a.author_id = ar.author_id ORDER BY 1"
    ).fetchall()
    names = [r[0] for r in rows]
    assert "Damodaran" in names and "Substack" in names
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest kdb_fts/tests/test_author_map.py kdb_fts/tests/test_intake.py -v`
Expected: all PASS (5 + 5)

- [ ] **Step 5: Commit (gate)**

```bash
git add kdb_fts/author_map.py kdb_fts/intake.py kdb_fts/tests/
git commit -m "feat(kdb-fts): #145 P0 — author map with yaml overrides"
```

---

### Task 6: Write-boundary guard (mechanical, D3)

**Files:**
- Modify: `tools/tests/test_package_boundaries.py` (add guard + self-test)
- Create: `tools/tests/fixtures/write_boundary_violation.py` (fixture the guard must catch)

**Interfaces:**
- Consumes: `kdb_fts` package tree as it exists after Tasks 1–5.
- Produces: `test_fts_write_boundary()` — AST scan enforcing: R1 `sqlite3.connect` only in `ledger.py`; R2 no `open()` with `w`/`a`/`x` modes anywhere in `kdb_fts` (use `common.atomic_io`); R3 filesystem mutation calls (`Path.write_text/write_bytes/unlink/rename/mkdir`, `os.remove/replace`, `shutil.*`) only in `ledger.py` (`mkdir` for the state dir) — later phases extend the allowlist per-module in this test.

- [ ] **Step 1: Write the failing test + violation fixture**

`tools/tests/fixtures/write_boundary_violation.py`:

```python
"""Fixture: a module that violates the kdb_fts write boundary (R1/R2/R3)."""
import sqlite3
from pathlib import Path


def bad_write(path: Path) -> None:
    with open(path, "w") as f:  # R2: bare open for write
        f.write("nope")
    with path.open("w") as f:  # R2: Path.open for write
        f.write("nope")
    sqlite3.connect(path)  # R1: connect outside ledger.py
    path.unlink()  # R3: mutator outside the allowlist
```

Add to `tools/tests/test_package_boundaries.py`:

```python
# --- #145 P0: kdb_fts write-boundary guard (blueprint D3) -------------------

_SQLITE_ALLOWLIST = {"ledger.py"}
_MKDIR_ALLOWLIST = {"ledger.py"}
_MUTATOR_ALLOWLIST = {"ledger.py"}


def _fts_write_violations(pkg_dir: pathlib.Path) -> list[str]:
    """AST scan of one tree for write-boundary violations. Returns messages."""
    violations: list[str] = []
    for path in pkg_dir.rglob("*.py"):
        if "tests" in path.parts or "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text())
        for n in ast.walk(tree):
            if not isinstance(n, ast.Call):
                continue
            # R1: sqlite3.connect outside the allowlist
            if (isinstance(n.func, ast.Attribute) and n.func.attr == "connect"
                    and isinstance(n.func.value, ast.Name) and n.func.value.id == "sqlite3"
                    and path.name not in _SQLITE_ALLOWLIST):
                violations.append(f"{path.name}:{n.lineno} sqlite3.connect outside ledger.py")
            # R2: open(...) — bare, Path.open, io.open — with a write-ish mode
            if (isinstance(n.func, ast.Name) and n.func.id == "open") or (
                isinstance(n.func, ast.Attribute) and n.func.attr == "open"
            ):
                mode = None
                if isinstance(n.func, ast.Attribute):
                    # Path.open(mode, ...) vs io.open(file, mode, ...) — take the
                    # first positional arg that is a pure mode string.
                    for arg in n.args[:2]:
                        if (isinstance(arg, ast.Constant) and isinstance(arg.value, str)
                                and arg.value and all(c in "rwa+xbt" for c in arg.value)):
                            mode = arg.value
                            break
                elif len(n.args) >= 2 and isinstance(n.args[1], ast.Constant):
                    mode = n.args[1].value
                for kw in n.keywords:
                    if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
                        mode = kw.value.value
                if isinstance(mode, str) and any(m in mode for m in "wax+"):
                    violations.append(f"{path.name}:{n.lineno} open(mode={mode!r}) — use common.atomic_io")
            # R3: mutating Path/os/shutil calls outside the allowlists
            if isinstance(n.func, ast.Attribute):
                attr = n.func.attr
                if (attr in {"write_text", "write_bytes", "unlink", "rename"}
                        and path.name not in _MUTATOR_ALLOWLIST):
                    violations.append(f"{path.name}:{n.lineno} Path.{attr} — writes go through ledger/atomic_io")
                if attr == "mkdir" and path.name not in _MKDIR_ALLOWLIST:
                    violations.append(f"{path.name}:{n.lineno} mkdir outside {_MKDIR_ALLOWLIST}")
                if (attr in {"remove", "replace"}
                        and isinstance(n.func.value, ast.Name) and n.func.value.id == "os"):
                    violations.append(f"{path.name}:{n.lineno} os.{attr}")
                if isinstance(n.func.value, ast.Name) and n.func.value.id == "shutil":
                    violations.append(f"{path.name}:{n.lineno} shutil.{attr}")
    return violations


def test_fts_write_boundary():
    assert _fts_write_violations(ROOT / "kdb_fts") == []


def test_fts_write_boundary_catches_violation(tmp_path):
    import shutil
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    shutil.copy(ROOT / "tools" / "tests" / "fixtures" / "write_boundary_violation.py",
                pkg / "bad.py")
    found = _fts_write_violations(pkg)
    assert sum("open(mode='w'" in v for v in found) == 2, found     # R2 bare + Path.open
    assert any("sqlite3.connect outside ledger.py" in v for v in found), found  # R1
    assert any("Path.unlink" in v for v in found), found            # R3
```

(Known theoretical false positive, accepted: an attribute-open call whose first
positional arg is a string literal composed solely of `[rwa+xbt]` — e.g.
`io.open("bar")` — is misread as a mode. `Path.open` is unaffected since its
mode comes first.)

- [ ] **Step 2: Run to verify the self-test passes and (before implementation is real) confirm the guard actually scans**

Run: `pytest tools/tests/test_package_boundaries.py -v -k write_boundary`
Expected: `test_fts_write_boundary_catches_violation` PASSES immediately (it tests the scanner, not the package). `test_fts_write_boundary` — **FAILS if any Task 1–5 code violates the rules**. Known violation to fix in this task: `author_map.py` Step-3 draft has no writes, but check `intake.py`/`ledger.py`: `ledger.connect` calls `root.mkdir(...)` — allowed (`ledger.py` in `_MKDIR_ALLOWLIST`). If `test_fts_write_boundary` fails on real code, fix the code (not the guard).

Note: the fixture file itself lives under `tools/tests/fixtures/` and is excluded from package scans (the scanner only walks the `kdb_fts` tree); the `_top_level_imports` scanner skips `tests` parts, so the fixture's `open(..., "w")` does not trip anything else.

- [ ] **Step 3: Fix any real violations found**

Expected clean. If the guard flags real code, refactor the write into `ledger.py` or `common.atomic_io` before proceeding. (Example: if `intake.py` ever wrote a repaired-view cache file, that write would move behind `atomic_io.atomic_write_text` under `state_root()`.)

- [ ] **Step 4: Run full boundary suite**

Run: `pytest tools/tests/test_package_boundaries.py -v`
Expected: all PASS

- [ ] **Step 5: Commit (gate)**

```bash
git add tools/tests/test_package_boundaries.py tools/tests/fixtures/write_boundary_violation.py
git commit -m "test(kdb-fts): #145 P0 — mechanical write-boundary guard (D3)"
```

---

### Task 7: CLI — `kdb-fts intake|search|status`

**Files:**
- Create: `kdb_fts/cli.py`
- Test: `kdb_fts/tests/test_cli.py`

**Interfaces:**
- Consumes: `ledger.connect/search`, `intake.run_intake`, `author_map.unmapped`, `state.state_root`.
- Produces: `cli.main(argv: list[str] | None = None) -> int`. Subcommands:
  - `intake [--raw-root PATH] [--state PATH]` — run intake; print stats.
  - `search <query> [--n 20]` — print ranked hits with snippets.
  - `status` — counts by cleanliness / content_kind, distinct authors, unmapped count, DB path.
- Later phases add `gate`, `extract`, `rank`, `review`, etc. to the same argparse tree.

- [ ] **Step 1: Write the failing tests**

`kdb_fts/tests/test_cli.py`:

```python
"""CLI smoke: intake → status → search round-trip over the fixture tree."""
from __future__ import annotations

from pathlib import Path

from kdb_fts import cli

FIXTURE = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "fts_tree"


def test_intake_status_search_roundtrip(tmp_path, capsys):
    state = tmp_path / "fts"
    assert cli.main(["intake", "--raw-root", str(FIXTURE), "--state", str(state)]) == 0
    out = capsys.readouterr().out
    assert "seen=5" in out and "deleted=0" in out

    assert cli.main(["status", "--state", str(state)]) == 0
    out = capsys.readouterr().out
    assert "ok: 1" in out and "digest-stub: 1" in out and "media: 1" in out
    assert "short: 1" in out and "bleed: 1" in out

    assert cli.main(["search", "Barrick", "--state", str(state)]) == 0
    out = capsys.readouterr().out
    assert "g-fixture-001" in out and "Barrick" in out


def test_search_no_hits_exit_0(tmp_path, capsys):
    state = tmp_path / "fts"
    cli.main(["intake", "--raw-root", str(FIXTURE), "--state", str(state)])
    capsys.readouterr()
    assert cli.main(["search", "zzzznope", "--state", str(state)]) == 0
    assert "no hits" in capsys.readouterr().out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest kdb_fts/tests/test_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'kdb_fts.cli'`

- [ ] **Step 3: Implement**

`kdb_fts/cli.py`:

```python
"""kdb-fts — CLI for the parallel extraction/ranking system (#145).

Phase 0 surface: intake / search / status (no LLM). Later phases add
gate/extract/rank/review to this same argparse tree (blueprint §8).
"""
from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from kdb_fts import author_map, intake, ledger, state


def _default_raw_root() -> Path:
    from common import paths

    return paths.kdb_root() / "raw" / "joseph-ft-public-gmail"


def _cmd_intake(args) -> int:
    root = Path(args.state).expanduser().resolve() if args.state else state.state_root()
    conn = ledger.connect(root)
    run_id = datetime.now().astimezone().isoformat(timespec="seconds")
    stats = intake.run_intake(
        conn, Path(args.raw_root).expanduser(), run_id, state_root=root
    )
    print(f"seen={stats['seen']} upserted={stats['upserted']} deleted={stats['deleted']}")
    print(f"cleanliness: {stats['by_cleanliness']}")
    print(f"content_kind: {stats['by_content_kind']}")
    print(f"raw_author_strings={stats['raw_author_strings']}")
    return 0


def _cmd_search(args) -> int:
    root = Path(args.state).expanduser().resolve() if args.state else state.state_root()
    conn = ledger.connect(root)
    hits = ledger.search(conn, args.query, limit=args.n)
    if not hits:
        print("no hits")
        return 0
    for h in hits:
        print(f"{h['article_id']}  {h['title'] or '(untitled)'}  — {h['author'] or '?'}")
        print(f"    {h['snippet']}")
    return 0


def _cmd_status(args) -> int:
    root = Path(args.state).expanduser().resolve() if args.state else state.state_root()
    conn = ledger.connect(root)
    print(f"db: {root / 'ledger.sqlite'}")
    for label, sql in (
        ("cleanliness", "SELECT cleanliness, COUNT(*) FROM articles GROUP BY 1 ORDER BY 1"),
        ("content_kind", "SELECT COALESCE(content_kind,'unknown'), COUNT(*) FROM articles GROUP BY 1 ORDER BY 1"),
    ):
        print(f"{label}:")
        for row in conn.execute(sql):
            print(f"  {row[0]}: {row[1]}")
    n_authors = conn.execute("SELECT COUNT(*) FROM authors").fetchone()[0]
    unm = author_map.unmapped(conn)
    print(f"authors: {n_authors} canonical, {len(unm)} unmapped raw strings")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kdb-fts")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("intake", help="walk raw tree → ledger + FTS rebuild")
    p.add_argument("--raw-root", default=str(_default_raw_root()))
    p.add_argument("--state", default=None, help="override state root (else $KDB_FTS_PATH else <vault>/KDB/fts)")
    p.set_defaults(fn=_cmd_intake)

    p = sub.add_parser("search", help="FTS5 query over title/author/body")
    p.add_argument("query")
    p.add_argument("--n", type=int, default=20)
    p.add_argument("--state", default=None)
    p.set_defaults(fn=_cmd_search)

    p = sub.add_parser("status", help="counts by cleanliness/kind, authors, db path")
    p.add_argument("--state", default=None)
    p.set_defaults(fn=_cmd_status)

    args = parser.parse_args(argv)
    return args.fn(args)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest kdb_fts/tests/test_cli.py -v`
Expected: 2 PASS

Run: `pip install -e ".[dev]" && kdb-fts --help`
Expected: usage line listing `intake`, `search`, `status`.

- [ ] **Step 5: Commit (gate)**

```bash
git add kdb_fts/cli.py kdb_fts/tests/test_cli.py
git commit -m "feat(kdb-fts): #145 P0 — CLI intake/search/status"
```

---

### Task 8: Real-tree gate + docs (Phase 0 exit gate)

**Files:**
- Modify: `docs/CODEBASE_OVERVIEW.md` (Milestone Changelog entry)
- Modify: `docs/TASKS.md` (#145 row: Phase 0 closed)
- Modify: `AGENTS.md` (Project Structure block: add `kdb_fts/` line; entry-point list: add `kdb-fts`)

**Interfaces:**
- Consumes: everything above, run against the real vault.

This task is **Joseph-fired** (touches the real vault's new `KDB/fts/` subtree; writes nothing else).

- [ ] **Step 1: Full suite green**

Run: `pytest`
Expected: baseline 3256 + new kdb_fts tests (~20) all PASS, 32 skipped, exit 0.

- [ ] **Step 2: Real intake**

Run: `kdb-fts intake`
Expected (reproduces the 2026-08-16 audit exactly):
- `seen=2659` (residual intake tree, `_promo` excluded)
- cleanliness: `digest-stub: 34`, `media: 89` (77 video + 12 podcast), `short: 25`, `bleed: 0`, `ok: 2511`
  - **Amended 2026-08-16 (Joseph): audit said `bleed: 3`; not reproducible on the
    live tree under any detection signature (no unparseable frontmatter, no
    missing gmail ids, no doubled blocks, no oversized values). Gate expects
    `bleed: 0`. The bleed classifier stays armed and fixture-tested; if a broken
    file ever lands, update this number then.**
- content_kind: `article: 2570`, `video: 77`, `podcast: 12`
- `raw_author_strings=117`
- Rankable cross-check: `ok + short + media + bleed` = 2625

If any OTHER number diverges, STOP — reconcile against the audit before
proceeding (the audit is the ground truth for this gate).

- [ ] **Step 3: Idempotency + boundary spot-checks**

Run: `kdb-fts intake` again → `deleted=0`, and `sqlite3 ~/Obsidian/KDB/fts/ledger.sqlite "SELECT COUNT(*) FROM paragraphs"` unchanged before/after.
Run: `kdb-fts search "Barrick"` → real hits with snippets.
Run: `find ~/Obsidian/KDB -path ~/Obsidian/KDB/fts -prune -o -newermt '-10 minutes' -type f -print | head`
Expected: no files outside `KDB/fts/` modified by the intake (D3 spot-check; guard test is the standing enforcement).

- [ ] **Step 4: Docs**

- `docs/CODEBASE_OVERVIEW.md`: Milestone Changelog entry — "#145 P0: kdb_fts package — intake + SQLite ledger + FTS5 over the gmail-substack raw tree; no LLM; write-boundary guard added."
- `docs/TASKS.md`: #145 row — Phase 0 ✅, note next gate is Phase 1 (gate + labeling app).
- `AGENTS.md`: Project Structure — add `kdb_fts/          # Parallel extraction/ranking system (#145): intake, SQLite ledger, FTS5` under `kdb_graph_search/`; entry-point list — add `kdb-fts               # kdb_fts CLI (P0: intake/search/status)`.

- [ ] **Step 5: Commit (gate)**

```bash
git add docs/CODEBASE_OVERVIEW.md docs/TASKS.md AGENTS.md
git commit -m "docs: #145 P0 — close phase gate; kdb_fts in structure + entry points"
```

---

## Self-review notes (run against blueprint §9 Phase 0 + §10)

- Spec coverage: package skeleton (T1), boundary rows (T1), write-boundary guard (T6), SQLite schema + migrations (T2), intake over fixture tree (T4/T5), FTS queries (T3/T7), real-tree gate (T8). Blueprint §10 rows covered: Boundary (T1), Write guard (T6), Intake (T4), Identity (T4 `test_identity_survives_move`). Gate/Extract/Cluster/Ranker/Decay/Feedback/Review/Dry-run rows are Phases 1+ — out of scope here by design.
- Phase 0 gate numbers are encoded in T8 Step 2 with a stop-on-divergence rule.
- Type consistency: `ArticleRecord` fields match between ledger (T3) and intake (T4) construction; `run_intake(conn, raw_root, run_id, state_root=...)` signature consistent between T5 edit and T7 caller; `ledger.search` dict keys (`article_id`/`title`/`author`/`snippet`) consistent between T3 tests and T7 renderer.

---

## Controller-ratified amendments (applied during execution, 2026-08-16)

The plan-text code blocks above are the original ratified text. Execution review
surfaced four defects; these amendments supersede the corresponding blocks and
the landed code is authoritative:

1. **Task 4 fixture** — `plain-article.md` body fattened to 52 words (two
   paragraphs) so it is a genuine `ok` exemplar under the <50-word rule;
   assertion `word_count == 52`. (Found by Task 4 implementer.)
2. **Task 5 `unmapped()`** — SQL `TRIM` comparison replaced by a Python
   post-filter `canonical == _normalize(raw)` (internal-whitespace variants
   were silently dropped from the curation list). Pinning test added. (Task 5
   reviewer Important.)
3. **Task 6 guard** — R2 now matches attribute opens (`Path.open`, `io.open`)
   with first-pure-mode-string extraction; R3 Path mutators allowlist
   `ledger.py` (`_MUTATOR_ALLOWLIST`); dead `_WRITE_MUTATORS` dropped; fixture
   + self-test extended to prove R1/R2(×2)/R3 all bite. Known accepted false
   positive: literal first arg of pure mode chars (e.g. `io.open("bar")`).
   (Task 6 reviewer Importants.)
4. **Final review fix wave (commit e29eb73)** —
   - `author_map.resolve()`: alias-first early return deleted; canonical
     target computed from the CURRENT mapping every call, alias upserted with
     `ON CONFLICT(raw_string) DO UPDATE` — Joseph's `author_map.yaml` edits
     now take effect on the next intake (the curation loop). Accepted side
     effect: repointing can orphan the old default-canonical author row
     (deliberately not GC'd; Phase 1 should decide author GC explicitly).
   - `intake.scan_tree()`: non-dict frontmatter coerced to `{}` before the
     `is_bleed` check (scalar/list YAML frontmatter → `bleed` + repair view,
     never a crash); `source_url` isinstance-guarded like the other fields.
   - `author_map.load_map()`: null yaml entries degrade to `{}`; unparseable
     or non-mapping files raise `ValueError` naming the path (fail loud for
     hand-edited config).
   - 5 new pinning tests; full suite 3288 passed, exit 0.

**Task 8 pre-flight addition (final-review recommendation):** before the real
`kdb-fts intake`, run a scan-only smoke so a per-file pathological input
surfaces with its path:

```bash
.venv/bin/python -c "
from pathlib import Path
from kdb_fts import intake
recs = intake.scan_tree(Path.home() / 'Obsidian/KDB/raw/joseph-ft-public-gmail')
print(len(recs), 'scanned OK')"
```

Expected: `2659 scanned OK` (gmail-substack tree), no traceback.

# get_body Content Tool — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `get_body(slug, page_type)` — a shared, read-only tool that returns a wiki page's body (frontmatter stripped) from `KDB/wiki/<subdir>/<slug>.md`.

**Architecture:** One new leaf module `common/wiki_io.py`, sibling to `source_io.py`. It composes two existing primitives — `paths.slug_to_abspath` (path + slug/page_type validation) and `source_io.parse_existing_frontmatter` (frontmatter/body split). Read-only; the compiler's `page_writer` owns writes. Consumed later by the Phase-3 MCP server and the graph viewer — built once here.

**Tech Stack:** Python 3, pytest. No new dependencies (`yaml` already used by `source_io`).

**Spec:** `docs/superpowers/specs/2026-06-11-get-body-content-tool-design.md`

---

## File Structure

- **Create** `common/wiki_io.py` — `get_body()` + `ContentNotFoundError`. Sole responsibility: read a wiki page body by slug+page_type.
- **Create** `common/tests/test_wiki_io.py` — unit tests over a tmp vault root (no graph fixture needed).
- No other files change. `common/__init__.py` is not touched — consumers import `from common.wiki_io import get_body` (matches how `paths`/`source_io` are imported, not re-exported).

---

### Task 1: Happy path — `get_body` returns frontmatter-stripped body

**Files:**
- Create: `common/wiki_io.py`
- Test: `common/tests/test_wiki_io.py`

- [ ] **Step 1: Write the failing tests**

Create `common/tests/test_wiki_io.py`:

```python
"""Tests for wiki_io — slug + page_type -> wiki page body reader."""
from __future__ import annotations

from pathlib import Path

import pytest

from common import paths
from common.wiki_io import get_body


def _write_page(root: Path, slug: str, page_type: str, body: str) -> Path:
    """Write a wiki page (fixed frontmatter block + body) at the resolved path."""
    fm = (
        "---\n"
        "title: Sample Title\n"
        f"slug: {slug}\n"
        f"page_type: {page_type}\n"
        "status: active\n"
        "---\n"
    )
    path = paths.slug_to_abspath(slug, page_type, root=root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(fm + body, encoding="utf-8")
    return path


@pytest.mark.parametrize("page_type", ["summary", "concept", "article"])
def test_get_body_returns_prose_for_each_page_type(tmp_path: Path, page_type: str) -> None:
    body = "The 4-7-8 breath is a relaxation exercise.\n"
    # File on disk has a blank line between the closing fence and the prose.
    _write_page(tmp_path, "four-seven-eight-breath", page_type, "\n" + body)
    result = get_body("four-seven-eight-breath", page_type, root=tmp_path)
    assert result == body  # frontmatter gone AND leading blank line stripped


def test_get_body_preserves_horizontal_rule_in_body(tmp_path: Path) -> None:
    body = "Intro line.\n\n---\n\nSection after a horizontal rule.\n"
    _write_page(tmp_path, "has-rule", "concept", "\n" + body)
    result = get_body("has-rule", "concept", root=tmp_path)
    assert result == body
    assert "---" in result  # body's own --- must not be truncated
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest common/tests/test_wiki_io.py -v`
Expected: FAIL at collection — `ModuleNotFoundError: No module named 'common.wiki_io'`.

- [ ] **Step 3: Write the minimal implementation**

Create `common/wiki_io.py`:

```python
"""wiki_io — read a wiki page's body by slug + page_type.

The wiki/ content store (KDB/wiki/<subdir>/<slug>.md) holds compiled page prose;
bodies are NOT in the graph (thin-node decision). This is the read accessor shared
by the Phase-3 MCP server (get_body tool) and the graph viewer. Read-only — the
compiler's page_writer owns writes.

Composes two existing primitives:
  * paths.slug_to_abspath   -> resolves the path (validates slug + page_type)
  * source_io.parse_existing_frontmatter -> splits (frontmatter, body)
"""
from __future__ import annotations

from pathlib import Path

from common import paths
from common.paths import PageType
from common.source_io import parse_existing_frontmatter


def get_body(slug: str, page_type: PageType, *, root: Path | None = None) -> str:
    """Return the body (frontmatter stripped) of the wiki page for slug+page_type.

    Raises PathError for an invalid slug or unknown page_type (delegated to
    paths.slug_to_abspath).
    """
    path = paths.slug_to_abspath(slug, page_type, root=root)
    _, body = parse_existing_frontmatter(path.read_text(encoding="utf-8"))
    return body.lstrip("\n")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest common/tests/test_wiki_io.py -v`
Expected: PASS (4 tests — 3 parametrized page types + the horizontal-rule case).

- [ ] **Step 5: Commit**

```bash
git add common/wiki_io.py common/tests/test_wiki_io.py
git commit -m "feat(common): get_body — slug+page_type -> wiki page body (#113 ph2)"
```

---

### Task 2: Missing file raises `ContentNotFoundError`

A wiki file absent for a valid slug+page_type means graph/disk drift. Surface it as a dedicated typed error (base `Exception`, not `ValueError` — the inputs were valid) so the MCP error envelope and the viewer can catch it explicitly.

**Files:**
- Modify: `common/wiki_io.py`
- Test: `common/tests/test_wiki_io.py`

- [ ] **Step 1: Write the failing test**

Append to `common/tests/test_wiki_io.py`, and add `ContentNotFoundError` to the import line:

```python
from common.wiki_io import get_body, ContentNotFoundError
```

```python
def test_get_body_missing_file_raises_content_not_found(tmp_path: Path) -> None:
    # Valid slug + page_type, but no file written -> drift, not a validation error.
    with pytest.raises(ContentNotFoundError) as exc:
        get_body("never-written", "concept", root=tmp_path)
    msg = str(exc.value)
    assert "never-written" in msg
    assert "concept" in msg


def test_content_not_found_is_not_value_error(tmp_path: Path) -> None:
    # Distinct from PathError/ValueError: the inputs were valid; the file is absent.
    with pytest.raises(ContentNotFoundError):
        get_body("never-written", "concept", root=tmp_path)
    assert not issubclass(ContentNotFoundError, ValueError)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest common/tests/test_wiki_io.py -v`
Expected: FAIL at collection — `ImportError: cannot import name 'ContentNotFoundError' from 'common.wiki_io'`.

- [ ] **Step 3: Implement the error class + existence guard**

Edit `common/wiki_io.py`. Add the class after the imports:

```python
class ContentNotFoundError(Exception):
    """No wiki file for a valid slug + page_type (graph/disk drift).

    Base is Exception (not ValueError/PathError): the inputs were valid, so this
    is a state/drift error, not a validation error.
    """

    def __init__(self, slug: str, page_type: str, path: Path) -> None:
        self.slug = slug
        self.page_type = page_type
        self.path = path
        super().__init__(
            f"No wiki page for slug={slug!r} page_type={page_type!r} (expected {path})"
        )
```

Add the existence guard inside `get_body`, right after resolving `path`:

```python
    path = paths.slug_to_abspath(slug, page_type, root=root)
    if not path.exists():
        raise ContentNotFoundError(slug, page_type, path)
    _, body = parse_existing_frontmatter(path.read_text(encoding="utf-8"))
    return body.lstrip("\n")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest common/tests/test_wiki_io.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add common/wiki_io.py common/tests/test_wiki_io.py
git commit -m "feat(common): get_body raises ContentNotFoundError on missing wiki file (#113 ph2)"
```

---

### Task 3: Characterization — invalid slug / unknown page_type delegate to `PathError`

These lock in that validation is delegated to `paths.slug_to_abspath` (not re-implemented here). They pass on first run — `slug_to_abspath` already validates — so they are regression guards, not RED-first tests. That is expected and correct for delegated behavior.

**Files:**
- Test: `common/tests/test_wiki_io.py`

- [ ] **Step 1: Write the characterization tests**

Append to `common/tests/test_wiki_io.py`, and add `PathError` to the imports:

```python
from common.paths import PathError
```

```python
def test_get_body_invalid_slug_raises_path_error(tmp_path: Path) -> None:
    with pytest.raises(PathError):
        get_body("Not A Slug", "concept", root=tmp_path)  # spaces/caps invalid


def test_get_body_unknown_page_type_raises_path_error(tmp_path: Path) -> None:
    with pytest.raises(PathError):
        get_body("valid-slug", "nonsense", root=tmp_path)  # type: ignore[arg-type]
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `pytest common/tests/test_wiki_io.py -v`
Expected: PASS (8 tests). These guard delegated validation; no implementation change.

- [ ] **Step 3: Commit**

```bash
git add common/tests/test_wiki_io.py
git commit -m "test(common): characterize get_body delegated slug/page_type validation (#113 ph2)"
```

---

### Task 4: Full-suite regression + boundary check

**Files:** none (verification only).

- [ ] **Step 1: Run the wiki_io tests and the common suite**

Run: `pytest common/tests/test_wiki_io.py common/tests/test_layering_leaf.py -v`
Expected: PASS. `test_layering_leaf.py` guards `common/`'s leaf layering — confirm `wiki_io`'s imports (`paths`, `source_io`) don't violate it. If that test enumerates modules, ensure `wiki_io` is acceptable (it imports only sibling `common` leaves — same as `source_io`).

- [ ] **Step 2: Run the full suite (offline only)**

Run: `pytest -m "not live" -q`
Expected: PASS, no new failures. (`-m "not live"` is mandatory — `.env` auto-loads API keys and plain `pytest` would fire paid live tests.)

- [ ] **Step 3: Stop — Phase 2 complete**

`get_body` exists, is tested, and is ready to be consumed by the Phase-3 MCP server and the viewer. No wiring is done here (out of scope). Report completion; the next step is updating `docs/TASKS.md` (#113 Phase 2 done) at the commit gate.

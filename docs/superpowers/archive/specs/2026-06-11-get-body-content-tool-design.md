# Phase 2 (#113) — `get_body` content tool design

**Date:** 2026-06-11 · **Status:** ratified (in dialogue) → spec self-review pending
**Parent:** `2026-06-10-graph-access-package-design.md` (v0.3), §3.5(b) content-store join, F3.

## Decision (conclusion-first)

`get_body` is **one tool**: given a wiki page's `slug` + `page_type`, it returns
that page's **body** (markdown prose, frontmatter stripped). Nothing more.

- **It reads files, not the graph.** Bodies are not in Kuzu (thin-node decision);
  they live in `KDB/wiki/<subdir>/<slug>.md`, the slug-addressed content store.
- **Two consumers, so it is built once and shared:** the Phase-3 **MCP server**
  (`get_body` tool) and the **graph viewer** (body-on-node-display). Because more
  than one top-level component depends on it, it cannot live *inside* either — it
  lives in the shared layer both already import, `common/`.
- **It earns its own step (a real Phase 2)** precisely because it is a shared
  prerequisite for both the MCP server and the viewer — built first, not folded
  into Phase 3.

This is the architecturally-honest placement: durable content store → a slug→prose
read tool → shared home (`common/`) → built once. The location follows from the
dependency graph (≥2 consumers), **not** from "what files already sit in `common/`".

## Contract

```python
# common/wiki_io.py
def get_body(slug: str, page_type: PageType, *, root: Path | None = None) -> str:
    """Return the body (frontmatter stripped) of the wiki page for slug+page_type.

    Reads KDB/wiki/<subdir>/<slug>.md. Raises PathError for invalid slug or
    page_type (delegated to paths), ContentNotFoundError if the file is absent.
    """
```

Implementation is a thin composition of two **existing** primitives:

1. `paths.slug_to_abspath(slug, page_type, root=root)` → resolves the absolute
   path (also validates slug + page_type, raising `PathError`).
2. read the file; `source_io.parse_existing_frontmatter(text)` → `(frontmatter, body)`;
   return `body`.

```python
def get_body(slug, page_type, *, root=None):
    path = paths.slug_to_abspath(slug, page_type, root=root)
    if not path.exists():
        raise ContentNotFoundError(slug, page_type, path)
    _, body = parse_existing_frontmatter(path.read_text(encoding="utf-8"))
    return body.lstrip("\n")   # deliberate: drop the blank line between the
                               # closing fence and prose (regex group(2) keeps it)
```

### Integration precondition (verified)

The Phase-3/viewer callers can supply `page_type` without an extra graph round-trip:
`page_type` is a stored `Entity` property (`schema.py:65`) and ships in the **base
entity projection** (`queries.py:23` — `e.slug, e.title, e.page_type, …`), so
`graph_neighborhood` / `get_entity` already return it next to the slug. **No N+1.**

Slugs are **globally unique** (`Entity.slug STRING PRIMARY KEY` — one table across all
page_types), so a slug alone already names one file. `page_type` is retained as an
input anyway because it comes free from the graph and keeps resolution a direct,
deterministic path lookup rather than a 3-subdir filesystem glob. (Not a reason to
reopen F3.)

### Inputs — why slug **and** page_type, not source_id

- The wiki files are named by **slug** (`4-7-8-breath.md`); `page_type` selects the
  subdir (`summaries`/`concepts`/`articles`). Both are needed to name the file.
- `source_id` is the *raw source note's* path and identifies a different store; one
  source → many concepts, so it cannot address a single body. Callers already hold
  the slug + page_type from the prior graph query (node metadata) — `get_body` does
  **not** re-query the graph to look anything up (F3: no hidden coupling).

### Return shape — body only

The frontmatter (title, status, source_refs, …) is metadata the **graph already
serves** via `get_entity`. Returning it here would duplicate that surface for no
consumer that has asked for it. So: prose only. If a "page metadata without a graph
round-trip" need ever appears, add a sibling reader then — not now (YAGNI).

### Errors

- **Invalid slug / unknown page_type** → `PathError` (already raised by
  `slug_to_abspath`; no new handling).
- **File absent** (valid slug+page_type, no file — i.e. graph/disk drift) →
  new `ContentNotFoundError(Exception)` in `common/wiki_io.py`. Base is plain
  `Exception`, **not** `ValueError`/`PathError`: the inputs were valid, so this is a
  state/drift error, not a validation error. A dedicated typed error (not the
  builtin `FileNotFoundError`) so the MCP error envelope and the viewer can catch it
  explicitly without swallowing unrelated I/O errors. Carries `slug`, `page_type`,
  and the resolved `path` for an actionable message.

## What this does NOT do (scope fence)

- No graph access; no `source_id` input; no frontmatter in the return value.
- No FTS / search (separate, deferred store).
- No write side (the compiler's `page_writer` owns writing; this is read-only).
- No MCP wiring and no viewer wiring — those consume `get_body` in their own
  phases/tasks. This step ships the shared tool + its tests.

## Testing (no graph fixture needed — file-based)

Unit tests over a tmp vault root:
1. Happy path for each `page_type` (summary / concept / article) → returns body,
   frontmatter stripped and no leading blank line (asserts the `lstrip("\n")`).
2. Body that itself contains a `---` line → not truncated (relies on
   `parse_existing_frontmatter`'s fence handling; add a regression case).
3. Missing file → raises `ContentNotFoundError` (with slug/page_type/path on it).
4. Invalid slug / unknown page_type → raises `PathError` (delegated).
5. `root` override honored (reads from the passed root, not the env default).

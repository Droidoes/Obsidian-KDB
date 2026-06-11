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

__all__ = ["get_body", "ContentNotFoundError"]


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


def get_body(slug: str, page_type: PageType, *, root: Path | None = None) -> str:
    """Return the body (frontmatter stripped) of the wiki page for slug+page_type.

    Raises PathError for an invalid slug or unknown page_type (delegated to
    paths.slug_to_abspath).

    Leading newlines (the blank line between the frontmatter fence and the prose)
    are stripped; if the page has no frontmatter, the raw text is returned with
    leading newlines stripped.
    """
    path = paths.slug_to_abspath(slug, page_type, root=root)
    if not path.exists():
        raise ContentNotFoundError(slug, page_type, path)
    _, body = parse_existing_frontmatter(path.read_text(encoding="utf-8"))
    return body.lstrip("\n")

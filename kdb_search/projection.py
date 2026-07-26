"""#123 text projection — the fat evidence block (spec §4, blueprint §5).

The grammar is frozen and golden-pinned. Two behaviours look like bugs and are
not (opus5 G7, derived by reproducing the fixture serializer byte-exactly):

  1. the excerpt is split on "\\n", NOT with splitlines() — so a trailing
     newline emits a final whitespace-only line (161/163 fixture excerpts);
  2. blank lines are indented too (377 in the fixture).

Any "tidy" of either breaks the golden tests deliberately.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

from common.paths import PageType
from common.wiki_io import ContentNotFoundError

from .constants import (
    EXCERPT_BLOCK_CEILING_BYTES,
    EXCERPT_SENTENCE_EXTENSION_WORDS,
    EXCERPT_WORD_CAP,
)
from .types import SpaceEntity

BodyReader = Callable[[str, PageType], str]

_INDENT = "    "  # excerpt content — always 4 spaces
_FIELD_INDENT = "  "  # field/delimiter lines — 2 spaces
_DELIMITER = '"""'
_SENTENCE_END = re.compile(r"[.!?](?=\s|$)")


@dataclass(frozen=True)
class ProjectedEntity:
    """One entity's projected evidence. `excerpt is None` means the body was
    missing (graph/disk drift) and the entity degrades to title-only."""

    entity: SpaceEntity
    excerpt: str | None
    truncated: bool
    body_missing: bool = False
    delimiter_collision_guard: int = 0


def render_thin_line(entity: SpaceEntity) -> str:
    """Stage-1 evidence: identity only, no excerpt."""
    return f"- slug: {entity.slug}  title: {entity.title}  type: {entity.page_type}"


def render_fat_block(projected: ProjectedEntity) -> str:
    """Stage-2 evidence for one entity. A title-only degrade renders as the bare
    identity line — no empty excerpt field."""
    identity = render_thin_line(projected.entity)
    if projected.excerpt is None:
        return identity
    lines = [identity, f"{_FIELD_INDENT}excerpt: {_DELIMITER}"]
    # Clause 1: split on "\n" — splitlines() would swallow the trailing newline's
    # final empty field. Clause 2: every line is indented, blank ones included.
    lines += [_INDENT + line for line in projected.excerpt.split("\n")]
    lines.append(f"{_FIELD_INDENT}{_DELIMITER}")
    return "\n".join(lines)


def _excerpt_policy_v1(body: str) -> str:
    """Leading excerpt, EXCERPT_WORD_CAP whitespace-tokenized words, extended to
    the sentence end when that lands inside the +10% window."""
    words = body.split()
    if len(words) <= EXCERPT_WORD_CAP:
        return body

    # Locate the character offset just past the capped word, then look ahead.
    offset, seen = 0, 0
    for match in re.finditer(r"\S+", body):
        seen += 1
        if seen == EXCERPT_WORD_CAP:
            offset = match.end()
            break

    window_words = words[EXCERPT_WORD_CAP : EXCERPT_WORD_CAP + EXCERPT_SENTENCE_EXTENSION_WORDS]
    window_chars = len(" ".join(window_words)) + 1
    lookahead = body[offset : offset + window_chars]
    extension = _SENTENCE_END.search(lookahead)
    if extension:
        return body[: offset + extension.end()]
    return body[:offset]


def stream_contribution_bytes(projected: ProjectedEntity) -> int:
    """The entity's contribution to the concatenated evidence stream: its
    rendered block PLUS the newline that terminates it.

    This — not the bare block — is the quantity the policy-v2 ceiling governs and
    the quantity the M=100 rollup is built from (100 x 2,500 B = 250,000 B
    exactly). The distinction is one byte and was latent in the ratified figures:
    spec §4 enumerates the block as "identity line + excerpt field + delimiters",
    which renders to 2,208 B for fixture v1's largest entity, while the ratified
    "largest rendered block 2,209 B" was measured with the separator included.
    Both are far under the ceiling, so nothing decided moves; the conservative
    reading is adopted because it is the one that bounds the real stream.
    """
    return len(render_fat_block(projected).encode()) + 1


def _truncate_to_block_ceiling(entity: SpaceEntity, excerpt: str) -> tuple[str, bool]:
    """Policy v2: the entity's stream contribution never exceeds the ceiling.
    Truncation is on a character boundary, and byte truncation takes precedence
    over the no-mid-sentence-cut rule — when the ceiling binds, the sentence
    rule yields.
    """
    def rendered_size(text: str) -> int:
        return stream_contribution_bytes(
            ProjectedEntity(entity=entity, excerpt=text, truncated=False)
        )

    if rendered_size(excerpt) <= EXCERPT_BLOCK_CEILING_BYTES:
        return excerpt, False

    # Binary search on the character count: rendered size is monotonic in it, and
    # slicing by character keeps every multi-byte sequence intact.
    lo, hi = 0, len(excerpt)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if rendered_size(excerpt[:mid]) <= EXCERPT_BLOCK_CEILING_BYTES:
            lo = mid
        else:
            hi = mid - 1
    return excerpt[:lo], True


def project_entity(entity: SpaceEntity, *, body_reader: BodyReader) -> ProjectedEntity:
    """Read one entity's body and project it to evidence. Callers never read
    bodies — projection runs inside search (spec §1.1)."""
    try:
        body = body_reader(entity.slug, entity.page_type)
    except ContentNotFoundError:
        return ProjectedEntity(entity=entity, excerpt=None, truncated=False, body_missing=True)

    excerpt = _excerpt_policy_v1(body)
    excerpt, truncated = _truncate_to_block_ceiling(entity, excerpt)
    # The guard counts collisions; it never rewrites content. A collided
    # delimiter is indented as content, so it cannot terminate the block.
    collisions = sum(1 for line in excerpt.split("\n") if line.strip() == _DELIMITER)
    return ProjectedEntity(
        entity=entity,
        excerpt=excerpt,
        truncated=truncated,
        delimiter_collision_guard=collisions,
    )

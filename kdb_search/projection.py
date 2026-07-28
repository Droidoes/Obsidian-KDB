"""#123 text projection — the fat evidence block (spec §4, blueprint §5).

The grammar is frozen and golden-pinned. Two behaviours look like bugs and are
not (opus5 G7, derived by reproducing the fixture serializer byte-exactly):

  1. the excerpt is split on "\\n", NOT with splitlines() — so a trailing
     newline emits a final whitespace-only line (161/163 fixture excerpts);
  2. blank lines are indented too (377 in the fixture).

Any "tidy" of either breaks the golden tests deliberately.

A third rule was added 2026-07-27 (H04, codex): **the identity line is exactly one
line, for any input** — see `_single_line`. It is the only structural boundary in
the block that indentation does not protect, and the whole P10 line-based argument
rests on it.
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
    QUERY_BLOCK_CEILING_BYTES,
    QUERY_FIELD_ALLOCATIONS,
    expression_labels,
)
from .types import SpaceEntity

BodyReader = Callable[[str, PageType], str]

_INDENT = "    "  # excerpt content — always 4 spaces
_FIELD_INDENT = "  "  # field/delimiter lines — 2 spaces
_DELIMITER = '"""'
_SENTENCE_END = re.compile(r"[.!?](?=\s|$)")
_QUERY_HEADER = "- query:"


@dataclass(frozen=True)
class ProjectedEntity:
    """One entity's projected evidence. `excerpt is None` means the body was
    missing (graph/disk drift) and the entity degrades to title-only."""

    entity: SpaceEntity
    excerpt: str | None
    truncated: bool
    body_missing: bool = False
    delimiter_collision_guard: int = 0


#: Every character `str.splitlines()` treats as a line boundary. Stated as that
#: exact set rather than as `"\n\r"`, because the invariant below is what makes
#: every line-based claim about the evidence block true — and `splitlines()` also
#: breaks on `\v`, `\f`, `\x1c-\x1e`, `\x85`, `\u2028` and `\u2029`.
_LINE_BREAKS = "\n\r\v\f\x1c\x1d\x1e\x85\u2028\u2029"


def _single_line(value: str) -> str:
    """Collapse any line boundary in an interpolated identity field to a space.

    **H04 (codex, 2026-07-27), fixed here rather than in the templates.** The
    identity line is the ONE structural boundary in the evidence block that is not
    indent-protected: `_scalar_lines` and `_item_lines` indent every continuation
    line, so an injected `\"\"\"` or `QUERY:` renders as content, but this line
    interpolates three field values into a single f-string. A title containing
    `\\nQUERY:` therefore forged an **unindented** line — the same form the prompt
    template uses for its section headers — and every line-based P10 claim about
    the block was false for that input. A harder delimiter in the template does
    not help: an unescaped title can forge that too.

    Titles reach the graph from `yaml.safe_load` over hand-authored notes
    (`common/source_io.py:39` → `kdb_graph/intake.py:325`) with no single-line
    check, and the 1,586-note vault ingestion is queued — so this is the ingested
    corpus, not a hypothetical. (The *KDB-authored* path was already closed:
    `compiler.page_writer.emit_frontmatter` raises on a newline in any frontmatter
    string.)

    Collapsed to a space rather than escaped to `\\n`, on two grounds: a line
    break in a title is malformed data, not content, so nothing meaningful is
    lost; and one character in, one character out keeps the substitution
    **byte-count preserving**, so no ceiling, maximum or golden figure can move
    because of it. Byte-neutral on today's data outright — 0 of the 163 fixture
    titles contain a line boundary.

    Not counted, deliberately, by the project's own consumer-purpose rule: no
    consumer and no decision rests on the count today, and `delimiter_collision_guard`
    exists because the collided delimiter is *left in place*. Here the anomaly is
    removed, so there is nothing downstream to warn about.
    """
    for char in _LINE_BREAKS:
        value = value.replace(char, " ")
    return value


def render_thin_line(entity: SpaceEntity) -> str:
    """Stage-1 evidence: identity only, no excerpt.

    Also the identity line of every stage-2 block (`render_fat_block`), so the
    one-line guarantee holds on both stages from one place.
    """
    return (
        f"- slug: {_single_line(entity.slug)}"
        f"  title: {_single_line(entity.title)}"
        f"  type: {entity.page_type}"
    )


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


# ---------------------------------------------------------------------------
# the query block (spec §3.1, blueprint §5) — 4,096 B via per-field allocations
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RenderedQuery:
    """The bounded query block plus what bounding it cost.

    Resolves a tension between two ratified passages: spec §1.1 fixes
    `QueryPayload` at `{text, expressions}` and §3.1 states `text` = summary +
    themes + keys + author "rendered into a fixed template", while D7(iv) makes
    the per-field ceiling a *projector* property with per-field counts. Both hold
    if the renderer lives here and the adapter passes `.text` through — so the
    ratified request type is untouched and no per-consumer contract appears (R2).
    `query_truncated` and `original_fields` are archived by P1.4; §3.1's
    "archived QueryPayload records both original and rendered forms" is a
    statement about the artifact, which P1.4 owns.
    """

    text: str
    #: The expressions AS RENDERED — after per-item truncation. Expression
    #: accounting resolves the wire's `matched` labels against these, never
    #: against the caller's originals: §3.1's "accounting runs over the rendered
    #: expressions — what the selector saw". Always populated, truncation or not,
    #: because the consumer needs it on every path.
    rendered_expressions: tuple[str, ...]
    #: Bytes dropped per field. Absent key == that field was not truncated; a
    #: count rather than a flag, because the magnitude is the signal worth
    #: watching (a 3-byte trim and a 19 kB trim are not the same event).
    query_truncated: dict[str, int]
    #: Pre-truncation values, for the archive (§3.1 records BOTH forms).
    original_fields: dict[str, object]
    #: Post-truncation values, keyed alike — the other half of "both forms".
    rendered_fields: dict[str, object]
    delimiter_collision_guard: int = 0


def _line_bytes(lines: list[str]) -> int:
    """A section's contribution to the block: its lines plus their separators."""
    return sum(len(line.encode()) + 1 for line in lines)


def _scalar_lines(label: str, value: str) -> list[str]:
    """`  label: first line`, with any further lines at the content indent — the
    same split-on-"\\n" guard as the excerpt (§5 G7 clauses). An injected
    `  \"\"\"` therefore renders at 4 spaces and cannot terminate anything."""
    head, *rest = value.split("\n")
    return [f"{_FIELD_INDENT}{label}: {head}"] + [_INDENT + line for line in rest]


def _item_lines(marker: str, value: str) -> list[str]:
    head, *rest = value.split("\n")
    return [f"{_INDENT}{marker}{head}"] + [_INDENT + line for line in rest]


def _fit(render: Callable[[str], list[str]], value: str, allowance: int) -> tuple[str, int]:
    """Truncate `value` on a character boundary until its rendered contribution
    fits `allowance`. Returns the value and the bytes dropped."""
    original = _line_bytes(render(value))
    if original <= allowance:
        return value, 0
    lo, hi = 0, len(value)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if _line_bytes(render(value[:mid])) <= allowance:
            lo = mid
        else:
            hi = mid - 1
    return value[:lo], original - _line_bytes(render(value[:lo]))


def render_query_block(
    *,
    summary: str = "",
    domain: str = "",
    author: str = "",
    key_themes: tuple[str, ...] = (),
    expressions: tuple[str, ...] = (),
) -> RenderedQuery:
    """Render the query block, never exceeding QUERY_BLOCK_CEILING_BYTES.

    Allocations bind on each field's *rendered contribution* — see
    `QUERY_FIELD_ALLOCATIONS`. Order is deliberate: the four bounded fields are
    fitted to their own allowances first, then `summary` takes whatever remains,
    which is what makes the total a hard property rather than a property of the
    inputs observed so far.
    """
    truncated: dict[str, int] = {}
    original: dict[str, object] = {}
    rendered: dict[str, object] = {}

    def record(field: str, before: object, after: object, dropped: int) -> None:
        if dropped:
            truncated[field] = dropped
            original[field] = before
            rendered[field] = after

    fitted_domain, dropped = _fit(
        lambda v: _scalar_lines("domain", v), domain, QUERY_FIELD_ALLOCATIONS["domain"]
    )
    record("domain", domain, fitted_domain, dropped)

    fitted_author, dropped = _fit(
        lambda v: _scalar_lines("author", v), author, QUERY_FIELD_ALLOCATIONS["author"]
    )
    record("author", author, fitted_author, dropped)

    # Per-item, so a single oversized key never costs another key its place.
    per_item = QUERY_FIELD_ALLOCATIONS["entity_search_keys_per_item"]
    fitted_expressions, expression_drop = [], 0
    labels = expression_labels(len(expressions))
    for label, expression in zip(labels, expressions):
        marker = f"{label}. "
        fitted, dropped = _fit(lambda v, m=marker: _item_lines(m, v), expression, per_item)
        fitted_expressions.append(fitted)
        expression_drop += dropped
    record("entity_search_keys", tuple(expressions), tuple(fitted_expressions), expression_drop)

    # Aggregate, and measured on the rendered form: the item COUNT is unbounded
    # (no `maxItems`), so the `    - ` prefixes are part of what must be bounded.
    aggregate = QUERY_FIELD_ALLOCATIONS["key_themes_aggregate"]
    fitted_themes, theme_drop, spent = [], 0, 0
    for theme in key_themes:
        remaining = aggregate - spent
        fitted, dropped = _fit(lambda v: _item_lines("- ", v), theme, remaining)
        if not fitted:
            # No room even for the marker: drop this theme and every one after it.
            theme_drop += sum(_line_bytes(_item_lines("- ", t)) for t in key_themes[len(fitted_themes):])
            break
        fitted_themes.append(fitted)
        spent += _line_bytes(_item_lines("- ", fitted))
        theme_drop += dropped
    record("key_themes", tuple(key_themes), tuple(fitted_themes), theme_drop)

    def block(summary_text: str) -> list[str]:
        lines = [_QUERY_HEADER]
        if fitted_domain:
            lines += _scalar_lines("domain", fitted_domain)
        if fitted_author:
            lines += _scalar_lines("author", fitted_author)
        if fitted_themes:
            lines.append(f"{_FIELD_INDENT}key_themes:")
            for theme in fitted_themes:
                lines += _item_lines("- ", theme)
        if fitted_expressions:
            lines.append(f"{_FIELD_INDENT}entity_search_keys:")
            for label, expression in zip(labels, fitted_expressions):
                lines += _item_lines(f"{label}. ", expression)
        if summary_text:
            lines.append(f"{_FIELD_INDENT}summary: {_DELIMITER}")
            lines += [_INDENT + line for line in summary_text.split("\n")]
            lines.append(f"{_FIELD_INDENT}{_DELIMITER}")
        return lines

    # `summary` absorbs the remainder. `_fit` measures the WHOLE block here, so
    # the ceiling is enforced once, on the quantity it is actually stated over
    # (`_line_bytes` counts a separator per line, one more than `"\n".join`, so
    # fitting to the ceiling leaves the joined text strictly under it).
    fitted_summary, dropped = _fit(block, summary, QUERY_BLOCK_CEILING_BYTES)
    record("summary", summary, fitted_summary, dropped)

    lines = block(fitted_summary)
    text = "\n".join(lines)
    assert len(text.encode()) <= QUERY_BLOCK_CEILING_BYTES, (
        f"query block {len(text.encode())} B exceeds the {QUERY_BLOCK_CEILING_BYTES} B ceiling"
    )
    # Counted over the field VALUES, not the rendered lines: the structural
    # delimiters are ours, and an item marker (`    - """`) already neutralizes a
    # collided delimiter without making it any less of an attacker signal.
    collided = [fitted_domain, fitted_author, fitted_summary, *fitted_themes, *fitted_expressions]
    return RenderedQuery(
        text=text,
        rendered_expressions=tuple(fitted_expressions),
        query_truncated=truncated,
        original_fields=original,
        rendered_fields=rendered,
        delimiter_collision_guard=sum(
            1 for value in collided for line in value.split("\n") if line.strip() == _DELIMITER
        ),
    )

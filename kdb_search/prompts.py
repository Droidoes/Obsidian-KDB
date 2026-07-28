"""#123 selector prompt loading + message assembly (spec §2.1, blueprint §5/B4).

One `.txt` per stage, each holding **both halves** of the prompt — the fixed
SYSTEM block and the USER template — separated by a `<<<USER>>>` marker line.
One file per stage because `PromptRef` carries one `version`, one `sha256` and
one `repo_path`: a two-file stage would need two refs, and the owner's prose
review is over the whole rendered prompt, which is exactly one artifact per
stage.

Four rules here are load-bearing, and each exists because the obvious
alternative fails in a way that would not be visible:

1.  **Substitution is single-pass** (`_SLOT.sub`). Sequential `str.replace`
    calls are a P10 injection vector: an evidence excerpt containing the literal
    `{{QUERY}}` would have the query block substituted *into it* on the second
    pass. `re.sub` never rescans replacement text, so a slot marker inside
    evidence or query content is inert.
2.  **Every slot must be known and every value must be used.** An unknown slot
    (`{{EVIDENC}}`) raises rather than shipping a literal brace pair to the
    model, and a value with no slot raises rather than silently dropping — a
    renamed `{{MAX_RESULTS}}` would otherwise remove the result cap from the
    prompt while every test still passed.
3.  **The digest is over the loaded TEXT, not `read_bytes()`.** Text mode
    translates `\\r\\n`, so a CRLF checkout would otherwise move both the sha256
    and the rendered bytes and silently invalidate P2.1f's pins. A test asserts
    neither template carries a `\\r` in the first place.
4.  **`repo_path` is a literal, never computed from `__file__`.** Deriving it via
    `relative_to(repo_root)` raises under an installed layout — the one layout
    the packaging test exists to cover. It is a provenance label, not a path
    anything resolves.

D10 ordering (`EVIDENCE` before `QUERY`, both stages) is a property of the
rendered USER message, so it is asserted there and not on the template source.
The per-request tail — the result cap and the query — follows the invariant
evidence block, and the query is last so it sits adjacent to the generation
point.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from .artifact import PromptRef, RenderedMessages, sha256_digest
from .budget import Stage
from .constants import M, MAX_RESULTS
from .types import SearchConfigError

_PROMPT_DIR = Path(__file__).parent / "prompts"

#: Splits the SYSTEM half from the USER half. Matched on the TEMPLATE only, at
#: load time — evidence and query content are substituted afterwards and are
#: never scanned for it, so a marker inside a document body is inert.
SECTION_MARKER = "<<<USER>>>"

_SLOT = re.compile(r"\{\{[^{}]*\}\}")
_VERSION_RE = re.compile(r"_v(\d+)\.txt\Z")

_FILENAMES: dict[Stage, str] = {
    "thin": "selector_thin_v1.txt",
    "fat": "selector_fat_v1.txt",
}

#: Spec §2.1 names these; both are DERIVED from the filename rather than
#: declared, so the file name is the single source of the version and the two
#: cannot drift. Renaming the file is what bumps the version.
SELECTOR_THIN_PROMPT_VERSION = _VERSION_RE.search(_FILENAMES["thin"]).group(1)  # type: ignore[union-attr]
SELECTOR_FAT_PROMPT_VERSION = _VERSION_RE.search(_FILENAMES["fat"]).group(1)  # type: ignore[union-attr]


class PromptTemplateError(SearchConfigError):
    """A template is missing, malformed, or rendered with the wrong slots.

    A `SearchConfigError` because it is the same kind of event as an unresolvable
    selector route: a precondition of doing any work at all, raised before any
    rendering, body read or call.
    """


@dataclass(frozen=True)
class SelectorTemplate:
    """One stage's loaded prompt: the fixed system block, the user template, and
    the provenance ref stamped onto every `StageRecord` for the stage."""

    stage: Stage
    system: str
    user_template: str
    ref: PromptRef


@cache
def _git_commit() -> str:
    """Best-effort short HEAD, cached, `"unknown"` on failure.

    Same posture as `common/version.py:release_version()` but not that function:
    it returns a `git describe` string (`v0.5.6-12-gd231331-dirty`), and putting
    a describe string in a field named `git_commit` breaks name-matches-contents.

    **Not load-bearing.** A dirty tree means the commit does not fully describe
    the template, which is exactly why `PromptRef` also carries `sha256` over the
    template text: content fidelity rests on the hash, `git_commit` is provenance
    colour. In an installed wheel there is no `.git` and this is `"unknown"`.
    """
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=Path(__file__).resolve().parent.parent,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return out.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


@cache
def load_template(stage: Stage) -> SelectorTemplate:
    """Load and split one stage's template. Cached — a batch of searches pays the
    file read once, and the ref is identical across the batch by construction."""
    filename = _FILENAMES[stage]
    path = _PROMPT_DIR / filename

    version_match = _VERSION_RE.search(filename)
    if version_match is None:
        raise PromptTemplateError(
            f"{filename!r} carries no `_v<N>.txt` version suffix — the filename IS "
            "the prompt version (PromptRef.version), so an unversioned name has no "
            "provenance to stamp"
        )

    try:
        # Text mode: universal newlines, so a CRLF checkout cannot move the digest.
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PromptTemplateError(
            f"selector template {filename!r} is unreadable at {path} — it is "
            "declared package-data (pyproject.toml `kdb_search`), so this is a "
            f"packaging or install fault: {exc}"
        ) from exc

    halves = text.split(SECTION_MARKER)
    if len(halves) != 2:
        raise PromptTemplateError(
            f"{filename!r} must contain the {SECTION_MARKER} section marker exactly "
            f"once (found {len(halves) - 1}); it separates the fixed SYSTEM block "
            "from the USER template"
        )
    system, user_template = (half.strip("\n") for half in halves)

    stray = _SLOT.findall(system)
    if stray:
        raise PromptTemplateError(
            f"{filename!r} has substitution slots in its SYSTEM half ({stray}) — the "
            "system block is fixed and is never substituted, so these would reach "
            "the model verbatim"
        )

    return SelectorTemplate(
        stage=stage,
        system=system,
        user_template=user_template,
        ref=PromptRef(
            version=version_match.group(1),
            sha256=sha256_digest(text),
            # A literal, never computed: `relative_to(repo_root)` raises under an
            # installed layout, which is the layout this has to survive.
            repo_path=f"kdb_search/prompts/{filename}",
            git_commit=_git_commit(),
        ),
    )


def _substitute(template: str, values: dict[str, str], *, filename: str) -> str:
    """Fill every slot in ONE pass. See rules 1 and 2 in the module docstring."""
    used: list[str] = []

    def fill(match: re.Match[str]) -> str:
        name = match.group(0)[2:-2]
        if name not in values:
            raise PromptTemplateError(
                f"{filename!r} has an unknown slot {match.group(0)} — known slots "
                f"are {sorted(values)}"
            )
        used.append(name)
        return values[name]

    rendered = _SLOT.sub(fill, template)
    missing = sorted(set(values) - set(used))
    if missing:
        raise PromptTemplateError(
            f"{filename!r} has no slot for {missing} — the value would be dropped "
            "silently, taking whatever it constrains out of the prompt"
        )
    duplicated = sorted({name for name in used if used.count(name) > 1})
    if duplicated:
        raise PromptTemplateError(
            f"{filename!r} repeats the slot(s) {duplicated}; each value is rendered "
            "once so the byte accounting stays a function of the template"
        )
    return rendered


def _render(stage: Stage, values: dict[str, str]) -> RenderedMessages:
    template = load_template(stage)
    return RenderedMessages(
        system=template.system,
        user=_substitute(template.user_template, values, filename=_FILENAMES[stage]),
    )


def render_thin_messages(*, evidence: str, query: str, retention_cap: int = M) -> RenderedMessages:
    """Stage-1 messages. `evidence` is the joined thin identity lines
    (`projection.render_thin_line`); `query` is `RenderedQuery.text`."""
    return _render(
        "thin",
        {"EVIDENCE": evidence, "QUERY": query, "RETENTION_CAP": str(retention_cap)},
    )


def render_fat_messages(*, evidence: str, query: str, max_results: int) -> RenderedMessages:
    """Stage-2 messages. `evidence` is the joined fat blocks
    (`projection.render_fat_block`); `query` is `RenderedQuery.text`.

    `max_results` is rendered into the prompt rather than left implicit: the
    validator counts an over-cap response as an `over_cap` attempted violation,
    and counting a rule the selector was never told is a measurement of our own
    omission.

    **Required, deliberately no default.** A default would let a call site render
    `MAX_RESULTS` into the prompt while `validate_response` counts against
    `request.max_results` — the selector would then obey the rule it was given and
    be charged against a different one, and the disagreement is invisible at both
    ends. The one caller that legitimately wants the global cap says so.
    """
    return _render(
        "fat",
        {"EVIDENCE": evidence, "QUERY": query, "MAX_RESULTS": str(max_results)},
    )


def template_overhead_bytes(stage: Stage) -> int:
    """The rendered system block + user wrapper, in bytes, with both content
    slots empty — the quantity `SYSTEM_TEMPLATE_BUDGET_BYTES` reserves.

    Measured with the widest cap value the contract allows, so the figure is the
    stage's maximum and not a sample. The evidence stream (M x
    `EXCERPT_BLOCK_CEILING_BYTES`) and the query block
    (`QUERY_BLOCK_CEILING_BYTES`) are budgeted separately by
    `budget.fat_worst_case_request_bytes()`; this is everything else.
    """
    messages = (
        render_thin_messages(evidence="", query="", retention_cap=M)
        if stage == "thin"
        else render_fat_messages(evidence="", query="", max_results=MAX_RESULTS)
    )
    return len(messages.system.encode()) + len(messages.user.encode())


__all__ = [
    "SECTION_MARKER",
    "SELECTOR_FAT_PROMPT_VERSION",
    "SELECTOR_THIN_PROMPT_VERSION",
    "PromptTemplateError",
    "SelectorTemplate",
    "load_template",
    "render_fat_messages",
    "render_thin_messages",
    "template_overhead_bytes",
]

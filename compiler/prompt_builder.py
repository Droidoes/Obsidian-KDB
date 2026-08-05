"""prompt_builder — assemble the system + user prompt for one compile call.

The prompt has two halves:

  system — the KDB compiler system prompt (the LLM's full invariants
           doc, packaged in the repo at compiler/prompts/ post-#115 —
           provenance is git + PASS2_PROMPT_VERSION + the loaded-text
           SHA-256 run stamp) + a locked response-contract block
           that enforces the shape the Python side actually parses.

  user   — source_name (input framing), the verbatim source text,
           a context snapshot from context_loader, the per-source
           response schema, and a minimal exemplar.

`load_system_prompt` and `load_response_schema_text` are memoised so a
batch of compiles pays the file-read cost once. Both live in the package,
so neither takes a key.

The response-contract block below is intentionally terse and mirrors the
PROPOSAL contract (#119): exactly one summary page, NO model-authored
summary slug (Python assigns its identity via the normalization bridge),
concept/article slugs required. If a rule is added to the proposal
schema or the bridge's reject classes, it belongs here too — the contract
the model sees and the contract we enforce must not drift. The contract
is wiki-native (#115): the model authors pages with [[wikilink]] bodies
only; Python owns derivation, link extraction, status, and provenance.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from common.types import ContextSnapshot

_SCHEMA_PATH = Path(__file__).parent / "schemas" / "proposal_response.schema.json"
_PROMPT_PATH = Path(__file__).parent / "prompts" / "KDB-Compiler-System-Prompt.md"

# Code-owned Pass-2 prompt version (D-115-13). Bumped in the SAME commit as
# any prompt-content change — content and version never drift. Stamped on
# every run header alongside the loaded-text SHA-256.
# 2.0.0 = repo-packaged prompt (Phase 0); 3.0.0 = wiki-native contract
# (Phase 1); 4.0.0 = proposal contract (#119 Phase 3): the summary page
# carries NO slug — Python assigns its identity via the normalization bridge.
# 4.0.1 = wording-only patch ("canonical shape" → "proposal response shape",
# Codex exec-review R1 F5); the proposal CONTRACT era is unchanged
# (4.x — replay dispatch accepts all 4.x).
# 4.0.2 = schema link-surface restoration (#120 D1, spec v1.4): the proposal
# schema regains the 3.0.0-era wiki-native clause + body-field wikilink
# instruction (constrained to authoritative targets, Codex R1–R5);
# system-prompt bytes unchanged.
# 4.1.0 = #129 tiered context snapshot: the EXISTING CONTEXT block is
# tier-structured (t1/t2/t3 lists + a one-line legend) with per-tier
# obligations in system-prompt §4 (t1 re-emit/extend, justify drops;
# t2 link-don't-duplicate; t3 weak context). The proposal CONTRACT is
# unchanged — era stays 4.x (replay dispatch accepts all 4.x).
PASS2_PROMPT_VERSION = "4.1.0"

# #129: one-line tier key for the EXISTING CONTEXT block — the full per-tier
# obligations live in §4 of the system prompt. MUST stay brace-free: tests
# locate the snapshot JSON by the first "{" after the section header.
_CONTEXT_TIER_LEGEND = (
    "Tiers: t1 = this source's own prior pages (re-emit or extend; justify "
    "drops); t2 = relevant pages from other sources (link, don't duplicate); "
    "t3 = weak neighborhood context."
)

RESPONSE_CONTRACT = """\
---
RESPONSE CONTRACT (non-negotiable):
- Return EXACTLY ONE JSON object. No other output.
- No markdown code fences around the object.
- No prose before or after the object.
- The object MUST satisfy the schema provided in the user message exactly.
- Every response contains exactly one page with page_type "summary".
  Do NOT emit a "slug" for the summary page — Python assigns its identity.
  Concept and article pages REQUIRE a "slug".
- The optional "compilation_notes" array carries non-fatal observations
  (notable reuse decisions, thin sources). DO NOT fabricate pages to
  satisfy the schema. If the source genuinely contains nothing
  knowledge-worthy, emit a single summary page whose body explains that —
  with honest content — and note it in compilation_notes."""


@dataclass(frozen=True)
class BuiltPrompt:
    system: str
    user: str


@cache
def load_system_prompt() -> str:
    """Read the repo-packaged compiler system prompt
    (`compiler/prompts/KDB-Compiler-System-Prompt.md`, post-#115). Cached —
    the file is static within a process. Raises FileNotFoundError naming
    the packaged path if the file is missing (e.g. a broken wheel)."""
    return _PROMPT_PATH.read_text(encoding="utf-8")


def system_prompt_path() -> Path:
    """Filesystem path of the packaged system prompt. For snapshotting
    (emit_kpis preserves the exact prompt text in each benchmark run dir —
    Task #30 re-runnability), NOT for reading: use load_system_prompt()."""
    return _PROMPT_PATH


@cache
def load_response_schema_text() -> str:
    """Return the per-source response schema as pretty JSON text.

    Re-dumped from the parsed object (not raw file bytes) so whitespace
    is normalised to 2-space indent and the prompt is byte-stable even
    if someone reformats the on-disk schema.
    """
    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    return json.dumps(schema, indent=2, ensure_ascii=False)


def exemplar_response() -> dict:
    """Minimal valid per-source PROPOSAL (#119 prompt 4.0.0 shape). Two
    pages — a summary WITHOUT a `slug` (Python assigns its identity via
    the normalization bridge; the model never authors it) and one concept
    with a slug — so the model sees a concrete target rather than guessing
    shape from the schema alone. `compilation_notes` is omitted to
    demonstrate its optionality."""
    return {
        "pages": [
            {
                "page_type": "summary",
                "title": "Example Summary",
                "body": "A short summary of what this source is about, "
                        "introducing [[example-concept]] as the central idea.",
            },
            {
                "slug": "example-concept",
                "page_type": "concept",
                "title": "Example Concept",
                "body": "Definition and treatment of the concept as the source presents it.",
            },
        ],
    }


_PASS1_META_BLOCK_TEMPLATE = """\
## PASS-1 SOURCE METADATA
The following fields were derived by the Pass-1 enrichment step and are
TRUSTED values — do NOT re-derive them from the source body.

- domain: {domain}
- source_type: {source_type}
- author: {author}

### Source summary (Pass-1 verbatim + appended themes per D-89-19)
{summary}

**Instructions:**
- USE `domain`, `source_type`, and `author` directly. Do NOT re-derive them.
- The summary above is authoritative; you do not need to rewrite or merge it."""


def _build_pass1_meta_block(source_meta: dict) -> str:
    """Render the PASS-1 SOURCE METADATA block from a source_meta dict.

    Excludes kdb_signal — it is the Pass-1 gatekeeper and is noise for
    the compile LLM (signal is already established by the time compile runs).

    v0.2.2 (D-89-19 + D-89-20): no key_themes/key_entities rendering. The
    summary string already carries the appended themes per D-89-19; themes
    participate in the graph via entity_search_keys → context_loader
    T2-rewrite (Task #90), upstream of Pass-2.
    """
    return _PASS1_META_BLOCK_TEMPLATE.format(
        domain=source_meta.get("domain", "(unknown)"),
        source_type=source_meta.get("source_type", "(unknown)"),
        author=source_meta.get("author") or "(unknown)",
        summary=source_meta.get("summary", "(none)"),
    )


def build_prompt(
    *,
    source_name: str,
    source_text: str,
    context_snapshot: ContextSnapshot,
    source_meta: dict | None = None,
) -> BuiltPrompt:
    """Assemble (system, user) strings for one compile call. Pure after
    the load_* calls populate their caches.

    source_meta (optional): dict with Pass-1 enrichment fields
    (domain, source_type, author, summary). Summary is pre-appended with
    key_themes by the caller per D-89-19. When present a 'PASS-1 SOURCE
    METADATA' block is inserted before SOURCE CONTENT with instructions
    per D-89-17 (v0.2.2 amended):
    - USE domain/source_type/author directly (no re-derivation)
    - summary is authoritative (no merge ceremony — D-89-18 retracted by
      D-89-19; themes participate in graph via entity_search_keys → T2-rewrite)
    When None (pre-Pass-1 sources), the block is omitted and the prompt
    renders unchanged for backward compatibility.
    """
    system_prompt = load_system_prompt()
    schema_text = load_response_schema_text()

    system = f"{system_prompt}\n\n{RESPONSE_CONTRACT}"

    context_json = json.dumps(context_snapshot.to_dict(), indent=2, ensure_ascii=False)
    exemplar_json = json.dumps(exemplar_response(), indent=2, ensure_ascii=False)

    # Conditionally prepend the Pass-1 metadata block before SOURCE CONTENT
    pass1_section = (
        f"{_build_pass1_meta_block(source_meta)}\n\n"
        if source_meta is not None
        else ""
    )

    user = (
        f"source_name: {source_name}\n\n"
        f"{pass1_section}"
        f"## SOURCE CONTENT\n{source_text}\n\n"
        f"## EXISTING CONTEXT (graph snapshot)\n"
        f"{_CONTEXT_TIER_LEGEND}\n{context_json}\n\n"
        f"## RESPONSE SCHEMA\n{schema_text}\n\n"
        f"## EXAMPLE RESPONSE\n{exemplar_json}"
    )

    return BuiltPrompt(system=system, user=user)


def main() -> None:  # pragma: no cover
    raise SystemExit("prompt_builder is a library module; not meant to be run directly.")


if __name__ == "__main__":
    main()

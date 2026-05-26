"""prompt_builder — assemble the system + user prompt for one compile call.

The prompt has two halves:

  system — the KDB compiler system prompt (the LLM's full invariants
           doc, served from the vault so the operator can edit it
           without a code change) + a locked response-contract block
           that enforces the shape the Python side actually parses.

  user   — source_name (echoed for semantic check), the verbatim source
           text, a context snapshot from graph_context_loader,
           the per-source response schema, and a minimal exemplar.

`load_system_prompt` and `load_response_schema_text` are memoised so a
batch of compiles pays the file-read cost once. The system prompt is
vault-owned (we load `<vault>/KDB/KDB-Compiler-System-Prompt.md`), so
the cache key is the vault Path. The schema lives in the package and
has no key.

The response-contract block below is intentionally terse and mirrors the
semantic rules in validate_compiled_source_response.semantic_check.
If a rule is added there, it belongs here too — the contract the model
sees and the contract we enforce must not drift. Source-id-space fields
(top-level source_id, per-page supports_page_existence, per-log_entry
related_source_ids) are runner-injected after parse and intentionally
absent from this contract — see Task #41.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from kdb_compiler.types import ContextSnapshot

_SCHEMA_PATH = Path(__file__).parent / "schemas" / "compiled_source_response.schema.json"

RESPONSE_CONTRACT = """\
---
RESPONSE CONTRACT (non-negotiable):
- Return EXACTLY ONE JSON object. No other output.
- No markdown code fences around the object.
- No prose before or after the object.
- The object MUST satisfy the schema provided in the user message exactly.
- The "source_name" field MUST echo the provided source_name verbatim.
- Use the "warnings" array for non-fatal observations about the source
  (ambiguous terms, unresolved references, uncertain categorization). DO NOT
  fabricate pages to satisfy the schema. If the source genuinely contains
  nothing knowledge-worthy, emit a single summary page whose body explains
  that — with honest content — and leave concept/article lists empty."""


@dataclass(frozen=True)
class BuiltPrompt:
    system: str
    user: str


@cache
def load_system_prompt(vault_root: Path) -> str:
    """Read <vault_root>/KDB/KDB-Compiler-System-Prompt.md. Cached per
    vault_root (Path is hashable). Raises FileNotFoundError if the
    vault has no system-prompt file."""
    path = vault_root / "KDB" / "KDB-Compiler-System-Prompt.md"
    return path.read_text(encoding="utf-8")


@cache
def load_response_schema_text() -> str:
    """Return the per-source response schema as pretty JSON text.

    Re-dumped from the parsed object (not raw file bytes) so whitespace
    is normalised to 2-space indent and the prompt is byte-stable even
    if someone reformats the on-disk schema.
    """
    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    return json.dumps(schema, indent=2, ensure_ascii=False)


def exemplar_response(source_name: str) -> dict:
    """Minimal valid per-source response. Satisfies both the JSON-Schema
    and the semantic rules for the supplied source_name, so the model
    sees a concrete target rather than guessing shape from the schema
    alone. Two pages — summary + one concept — so the exemplar
    demonstrates the body↔outgoing_links bidirectional rule by example."""
    return {
        "source_name": source_name,
        "summary_slug": "summary-example",
        "concept_slugs": ["example-concept"],
        "article_slugs": [],
        "pages": [
            {
                "slug": "summary-example",
                "page_type": "summary",
                "title": "Example Summary",
                "body": "A short summary of what this source is about, "
                        "introducing [[example-concept]] as the central idea.",
                "status": "active",
                "outgoing_links": ["example-concept"],
                "confidence": "medium",
            },
            {
                "slug": "example-concept",
                "page_type": "concept",
                "title": "Example Concept",
                "body": "Definition and treatment of the concept as the source presents it.",
                "status": "active",
                "outgoing_links": [],
                "confidence": "medium",
            },
        ],
        "log_entries": [],
        "warnings": [],
    }


_PASS1_META_BLOCK_TEMPLATE = """\
## PASS-1 SOURCE METADATA
The following fields were derived by the Pass-1 enrichment step and are
TRUSTED values — do NOT re-derive them from the source body.

- domain: {domain}
- source_type: {source_type}
- author: {author}

### Source summary (from Pass-1)
{summary}

### Key themes (from Pass-1)
{key_themes_list}

**Instructions:**
- USE `domain`, `source_type`, and `author` directly. Do NOT re-derive them.
- For `Source.summary`: MERGE the Pass-1 summary above with the key themes into
  a single integrated prose narrative. Weave the themes organically — do NOT
  produce a verbatim copy of the Pass-1 summary, and do NOT append a bullet
  list of themes.
- `key_entities` listed below are seed entity-extraction candidates from Pass-1.
  Begin entity extraction with these seeds; verify each is genuinely relevant to
  the body content; supplement with additional entities discovered in the body;
  dedupe against the existing GraphDB context snapshot as usual.

### Key entity seeds (from Pass-1)
{key_entities_list}"""


def _build_pass1_meta_block(source_meta: dict) -> str:
    """Render the PASS-1 SOURCE METADATA block from a source_meta dict.

    Excludes kdb_signal — it is the Pass-1 gatekeeper and is noise for
    the compile LLM (signal is already established by the time compile runs).
    """
    key_themes = source_meta.get("key_themes") or []
    key_entities = source_meta.get("key_entities") or []

    key_themes_list = (
        "\n".join(f"- {t}" for t in key_themes) if key_themes else "(none)"
    )
    key_entities_list = (
        "\n".join(f"- {e}" for e in key_entities) if key_entities else "(none)"
    )

    return _PASS1_META_BLOCK_TEMPLATE.format(
        domain=source_meta.get("domain", "(unknown)"),
        source_type=source_meta.get("source_type", "(unknown)"),
        author=source_meta.get("author") or "(unknown)",
        summary=source_meta.get("summary", "(none)"),
        key_themes_list=key_themes_list,
        key_entities_list=key_entities_list,
    )


def build_prompt(
    *,
    vault_root: Path,
    source_name: str,
    source_text: str,
    context_snapshot: ContextSnapshot,
    source_meta: dict | None = None,
) -> BuiltPrompt:
    """Assemble (system, user) strings for one compile call. Pure after
    the load_* calls populate their caches.

    source_meta (optional): dict with Pass-1 enrichment fields
    (domain, source_type, author, summary, key_themes, key_entities).
    When present a 'PASS-1 SOURCE METADATA' block is inserted before
    SOURCE CONTENT with explicit instructions per D-89-17/D-89-18:
    - USE domain/source_type/author directly (no re-derivation)
    - MERGE summary + key_themes into Source.summary prose (not verbatim copy)
    - TREAT key_entities as seed candidates (verify + supplement + dedupe)
    When None (pre-Pass-1 sources), the block is omitted and the prompt
    renders unchanged for backward compatibility.
    """
    system_prompt = load_system_prompt(vault_root)
    schema_text = load_response_schema_text()

    system = f"{system_prompt}\n\n{RESPONSE_CONTRACT}"

    context_json = json.dumps(context_snapshot.to_dict(), indent=2, ensure_ascii=False)
    exemplar_json = json.dumps(exemplar_response(source_name), indent=2, ensure_ascii=False)

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
        f"## EXISTING CONTEXT (graph snapshot)\n{context_json}\n\n"
        f"## RESPONSE SCHEMA\n{schema_text}\n\n"
        f"## EXAMPLE RESPONSE\n{exemplar_json}"
    )

    return BuiltPrompt(system=system, user=user)


def main() -> None:  # pragma: no cover
    raise SystemExit("prompt_builder is a library module; not meant to be run directly.")


if __name__ == "__main__":
    main()

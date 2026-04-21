"""prompt_builder — assemble the system + user prompt for one compile call.

The prompt has two halves:

  system — the KDB compiler system prompt (the LLM's full invariants
           doc, served from the vault so the operator can edit it
           without a code change) + a locked response-contract block
           that enforces the shape the Python side actually parses.

  user   — source_id (echoed for semantic check), the verbatim source
           text, a body-free manifest snapshot from context_loader,
           the per-source response schema, and a minimal exemplar.

`load_system_prompt` and `load_response_schema_text` are memoised so a
batch of compiles pays the file-read cost once. The system prompt is
vault-owned (we load `<vault>/KDB/KDB-Compiler-System-Prompt.md`), so
the cache key is the vault Path. The schema lives in the package and
has no key.

The response-contract block below is intentionally terse and mirrors the
four semantic rules in validate_compiled_source_response.semantic_check.
If a rule is added there, it belongs here too — the contract the model
sees and the contract we enforce must not drift.
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
- The "source_id" field MUST echo the provided source_id verbatim.
- Every page's "supports_page_existence" array MUST contain the provided source_id.
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


def exemplar_response(source_id: str) -> dict:
    """Minimal valid per-source response. Satisfies both the JSON-Schema
    and the four semantic rules for the supplied source_id, so the model
    sees a concrete target rather than guessing shape from the schema
    alone."""
    return {
        "source_id": source_id,
        "summary_slug": "example-summary",
        "concept_slugs": [],
        "article_slugs": [],
        "pages": [
            {
                "slug": "example-summary",
                "page_type": "summary",
                "title": "Example Summary",
                "body": "A short summary of what this source is about.",
                "status": "active",
                "supports_page_existence": [source_id],
                "outgoing_links": [],
                "confidence": "medium",
            }
        ],
        "log_entries": [],
        "warnings": [],
    }


def build_prompt(
    *,
    vault_root: Path,
    source_id: str,
    source_text: str,
    context_snapshot: ContextSnapshot,
) -> BuiltPrompt:
    """Assemble (system, user) strings for one compile call. Pure after
    the load_* calls populate their caches."""
    system_prompt = load_system_prompt(vault_root)
    schema_text = load_response_schema_text()

    system = f"{system_prompt}\n\n{RESPONSE_CONTRACT}"

    context_json = json.dumps(context_snapshot.to_dict(), indent=2, ensure_ascii=False)
    exemplar_json = json.dumps(exemplar_response(source_id), indent=2, ensure_ascii=False)

    user = (
        f"source_id: {source_id}\n\n"
        f"## SOURCE CONTENT\n{source_text}\n\n"
        f"## EXISTING CONTEXT (manifest snapshot)\n{context_json}\n\n"
        f"## RESPONSE SCHEMA\n{schema_text}\n\n"
        f"## EXAMPLE RESPONSE\n{exemplar_json}"
    )

    return BuiltPrompt(system=system, user=user)


def main() -> None:  # pragma: no cover
    raise SystemExit("prompt_builder is a library module; not meant to be run directly.")


if __name__ == "__main__":
    main()

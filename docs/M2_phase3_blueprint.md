# M2 Phase 3 Blueprint — Schema-First Compile + Resp-Stats at Get-Go

**Authored**: 2026-04-19 (Opus 4.7)
**Consensus input**: GPT-5.4 (schema-first revision) + Opus 4.7 (resp-stats hooks, semantic checks)
**Scope**: M2 v1 — first real LLM compile. Schema-first contract. Minimal Python cleanup. Always-on per-call audit trail. Slim replay harness.

This blueprint is the locked design for M2. Once approved, implementation proceeds step-by-step per §11. Each step is commit-gated.

---

## 1. Locked Decisions (shared across all steps)

| Decision | Value |
|---|---|
| Compile granularity | 1 source per model call |
| Model contract | Per-source JSON object matching `compiled_source_response.schema.json` |
| Model response schema | Provided in the prompt (text), not via API-native structured output |
| Provider default | `anthropic` |
| Model default | `claude-opus-4-7` |
| Temperature | `0.0` |
| `max_tokens` | `4096` |
| `json_mode` | Dropped from the contract (Anthropic SDK path in `call_model.py` ignores it) |
| `run_id` source | `ctx.run_id` threaded through orchestrator → compiler → resp-stats → compile_result |
| UNCHANGED sources | Skipped entirely (already excluded by `scan.to_compile`) |
| Binary sources | Filtered out of compile jobs by the planner — v1.1 will add a metadata-only page path; M2 v1 just leaves them in manifest |
| Error tolerance | Per-source try/except; partial success continues the run |
| `success` semantics | `success = (len(errors) == 0)` — an empty run with no errors is successful (clean scan / no-op) |
| Nothing-to-compile | Successful no-op: synthesize empty `CompileResult` with success=true, skip model calls, proceed to apply |
| Resp-stats invariant | Exactly one record per `compile_one` call — scaffolded at entry, populated as stages run, written in a `finally` block so source-read / prompt-build failures are also captured |
| Context snapshot fields | `{slug, title, page_type, outgoing_links}` — no bodies, no paths, no timestamps |
| Context page cap | 50 |
| Resp-stats path | `KDB/state/llm_resp/<run_id>/<safe_source_id>.json` |
| Resp-stats always-on | metadata + hashes + four classification flags + `parsed_summary` + error lists |
| Resp-stats env-gated | `KDB_RESP_CAPTURE_FULL=1` → include `parsed_json` + full system/user/raw bodies |
| Python post-processing | JSON extract, schema validate, semantic check, aggregate, write. **Not**: rename, coerce, slug-fix, infer missing fields. |
| Kdb_compile seam | Hybrid: fixture-if-present else compile-if-to_compile-non-empty else fail |

---

## 2. File Manifest

### Add (14 files)

| Path | Est LOC | Purpose |
|---|---|---|
| `kdb_compiler/schemas/compiled_source_response.schema.json` | ~140 | Per-source model contract |
| `kdb_compiler/validate_compiled_source_response.py` | ~110 | Schema + semantic validator |
| `kdb_compiler/resp_stats_writer.py` | ~100 | RespStatsRecord builder + atomic writer |
| `kdb_compiler/response_replay.py` | ~170 | `kdb-replay --replay <dir>` + report |
| `kdb_compiler/tests/test_validate_compiled_source_response.py` | ~200 | |
| `kdb_compiler/tests/test_response_normalizer.py` | ~110 | |
| `kdb_compiler/tests/test_resp_stats_writer.py` | ~130 | |
| `kdb_compiler/tests/test_context_loader.py` | ~160 | |
| `kdb_compiler/tests/test_prompt_builder.py` | ~160 | Snapshot tests |
| `kdb_compiler/tests/test_planner.py` | ~100 | |
| `kdb_compiler/tests/test_compiler.py` | ~310 | Mocked seam; no live API |
| `kdb_compiler/tests/test_response_replay.py` | ~110 | |
| `kdb_compiler/tests/test_m2_first_compile.py` | ~70 | **Env-blocked**; one live call |
| `kdb_compiler/tests/fixtures/response_replay/` (3 cases × ~80 lines) | ~240 | Replay fixtures |

### Change (9 files)

| Path | Est Δ | Purpose |
|---|---|---|
| `kdb_compiler/schemas/compile_result.schema.json` | +12 | Additive `compile_meta` def under `$defs.compiledSource` |
| `kdb_compiler/types.py` | +160 | New dataclasses (+ `ParsedSummary`) + extend `CompiledSource` |
| `kdb_compiler/call_model.py` | +3 | Add `attempts: int = 1` to `ModelResponse` |
| `kdb_compiler/call_model_retry.py` | +5 | Set `response.attempts = attempt` before return |
| `kdb_compiler/planner.py` | rewrite stub → ~120 | |
| `kdb_compiler/context_loader.py` | rewrite stub → ~160 | |
| `kdb_compiler/prompt_builder.py` | rewrite stub → ~160 | |
| `kdb_compiler/response_normalizer.py` | rewrite stub → ~60 | Shrink hard |
| `kdb_compiler/compiler.py` | rewrite stub → ~300 | |
| `kdb_compiler/kdb_compile.py` | ~25 line Δ | Step 5 hybrid |
| `pyproject.toml` | +3 lines | `kdb-plan`, `kdb-compile-sources`, `kdb-replay`, `kdb-validate-response` scripts |

**Total**: ~1,400 production LOC + ~1,600 test/fixture LOC ≈ 3,000 lines of M2 work.

---

## 3. Schemas

### 3.1 `compiled_source_response.schema.json` (NEW)

This is the contract the model sees in the prompt and must satisfy.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://obsidian-kdb.local/schemas/compiled_source_response.schema.json",
  "title": "KDB Compiled Source Response (per-call model output)",
  "description": "Exactly one source → exactly one response object. Run-level fields (run_id, success, aggregate errors) are Python-owned and NOT present here. See docs/M2_phase3_blueprint.md §3.1.",
  "type": "object",
  "additionalProperties": false,
  "required": ["source_id", "summary_slug", "pages", "log_entries", "warnings"],
  "properties": {
    "source_id": { "$ref": "#/$defs/sourceId" },
    "summary_slug": { "$ref": "#/$defs/slug" },
    "concept_slugs": { "type": "array", "items": { "$ref": "#/$defs/slug" } },
    "article_slugs": { "type": "array", "items": { "$ref": "#/$defs/slug" } },
    "pages": {
      "type": "array",
      "minItems": 1,
      "items": { "$ref": "#/$defs/pageIntent" }
    },
    "log_entries": {
      "type": "array",
      "items": { "$ref": "#/$defs/logEntry" }
    },
    "warnings": {
      "type": "array",
      "items": { "type": "string" }
    }
  },
  "$defs": {
    "slug": {
      "type": "string",
      "pattern": "^[a-z0-9]+(?:-[a-z0-9]+)*$",
      "minLength": 1,
      "maxLength": 120
    },
    "sourceId": {
      "type": "string",
      "pattern": "^KDB/raw/.+",
      "minLength": 1
    },
    "pageType": {
      "type": "string",
      "enum": ["summary", "concept", "article"]
    },
    "pageStatus": {
      "type": "string",
      "enum": ["active", "stale", "archived"]
    },
    "confidence": {
      "type": "string",
      "enum": ["low", "medium", "high"]
    },
    "pageIntent": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "slug", "page_type", "title", "body",
        "status", "supports_page_existence", "outgoing_links", "confidence"
      ],
      "properties": {
        "slug": { "$ref": "#/$defs/slug" },
        "page_type": { "$ref": "#/$defs/pageType" },
        "title": { "type": "string", "minLength": 1, "maxLength": 200 },
        "body": { "type": "string", "minLength": 1 },
        "status": { "$ref": "#/$defs/pageStatus" },
        "supports_page_existence": {
          "type": "array",
          "minItems": 1,
          "items": { "$ref": "#/$defs/sourceId" }
        },
        "outgoing_links": {
          "type": "array",
          "items": { "$ref": "#/$defs/slug" }
        },
        "confidence": { "$ref": "#/$defs/confidence" }
      }
    },
    "logEntry": {
      "type": "object",
      "additionalProperties": false,
      "required": ["level", "message", "related_slugs", "related_source_ids"],
      "properties": {
        "level": {
          "type": "string",
          "enum": ["info", "notice", "contradiction", "warning"]
        },
        "message": { "type": "string", "minLength": 1 },
        "related_slugs": {
          "type": "array",
          "items": { "$ref": "#/$defs/slug" }
        },
        "related_source_ids": {
          "type": "array",
          "items": { "$ref": "#/$defs/sourceId" }
        }
      }
    }
  }
}
```

**Contract intent**: the per-source schema is *stricter* than `compile_result.schema.json`'s `pageIntent` — all 8 fields required. This forces the model to commit to status, support, links, and confidence on every page. Python doesn't backfill defaults.

### 3.2 `compile_result.schema.json` additive edit

Add under `$defs.compiledSource.properties`:

```json
"compile_meta": {
  "type": "object",
  "description": "Per-source model-call metadata stamped by Python. Present only when this entry came from a live compile; omitted for fixture-backed compile_result.json.",
  "additionalProperties": false,
  "required": ["provider", "model", "input_tokens", "output_tokens", "latency_ms", "attempts", "ok"],
  "properties": {
    "provider": { "type": "string" },
    "model": { "type": "string" },
    "input_tokens": { "type": "integer", "minimum": 0 },
    "output_tokens": { "type": "integer", "minimum": 0 },
    "latency_ms": { "type": "integer", "minimum": 0 },
    "attempts": { "type": "integer", "minimum": 1 },
    "ok": { "type": "boolean" },
    "error": { "type": ["string", "null"] }
  }
}
```

`compile_meta` is **optional** at the top level (not added to `required`) → M1 fixture tests continue to pass untouched.

---

## 4. `types.py` Additions

Add after existing compile artifact shapes:

```python
@dataclass
class ContextPage:
    slug: str
    title: str
    page_type: PageType
    outgoing_links: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ContextSnapshot:
    source_id: str
    pages: list[ContextPage] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "source_id": self.source_id,
            "pages": [p.to_dict() for p in self.pages],
        }


@dataclass
class CompileJob:
    source_id: str                 # "KDB/raw/..."
    abs_path: str                  # absolute filesystem path
    context_snapshot: ContextSnapshot


@dataclass
class CompileMeta:
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    attempts: int
    ok: bool
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ParsedSummary:
    """Lossy reduction of parsed_json used when capture-full is off.
    Preserves the shape information useful for aggregate analytics without
    storing generated bodies (which are the bulk of the payload)."""
    summary_slug: Optional[str]
    page_count: int
    page_types: dict[str, int]          # {"summary": 1, "concept": 3, ...}
    slugs: list[str]
    outgoing_link_count: int
    log_entry_count: int
    warning_count: int
    source_id_echoed: Optional[str]     # value of parsed_json["source_id"] if present

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RespStatsRecord:
    run_id: str
    source_id: str
    provider: str
    model: str
    attempts: int
    latency_ms: int
    input_tokens: int
    output_tokens: int
    prompt_hash: str              # "sha256:<hex>"
    response_hash: str            # "sha256:<hex>"  (sentinel "sha256:none" if no response)
    extract_ok: bool
    parse_ok: bool
    schema_ok: bool
    semantic_ok: bool
    schema_errors: list[str] = field(default_factory=list)
    semantic_errors: list[str] = field(default_factory=list)
    parsed_summary: Optional[ParsedSummary] = None   # always-on shape digest (None if parse failed)
    parsed_json: Optional[dict] = None               # gated — full parsed object when capture-full on
    system_prompt: Optional[str] = None              # gated
    user_prompt: Optional[str] = None                # gated
    raw_response_text: Optional[str] = None          # gated

    def to_dict(self) -> dict:
        return asdict(self)
```

Extend `CompiledSource`:

```python
@dataclass
class CompiledSource:
    source_id: str
    summary_slug: str
    pages: list[PageIntent]
    concept_slugs: list[str] = field(default_factory=list)
    article_slugs: list[str] = field(default_factory=list)
    compile_meta: Optional[CompileMeta] = None     # NEW

    def to_dict(self) -> dict:
        d = {
            "source_id": self.source_id,
            "summary_slug": self.summary_slug,
            "concept_slugs": list(self.concept_slugs),
            "article_slugs": list(self.article_slugs),
            "pages": [p.to_dict() for p in self.pages],
        }
        if self.compile_meta is not None:
            d["compile_meta"] = self.compile_meta.to_dict()
        return d
```

Also extend `ModelResponse` in `call_model.py`:

```python
@dataclass
class ModelResponse:
    text: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    model: str
    provider: str
    attempts: int = 1            # NEW — stamped by call_model_with_retry
    raw: Any = None
```

And `call_model_retry.py`: on success, set `response.attempts = attempt` before returning.

---

## 5. Per-Module Signatures

### 5.1 `response_normalizer.py` (shrink hard)

```python
"""response_normalizer — strict JSON extraction. No semantic repair."""

def extract_json_text(raw_text: str) -> str:
    """
    Accept only:
      1. bare JSON object text (starts with '{', ends with '}')
      2. single fenced block: ```json\n{...}\n``` or ```\n{...}\n```
    Leading/trailing whitespace is stripped before checking.
    Raises ValueError for any other shape.
    """

def parse_json_object(raw_text: str) -> dict:
    """extract_json_text + json.loads. Raises ValueError on failure."""
```

**Forbidden behaviors** (enforced by code review, not tests):
- No regex to "find the first JSON-looking substring"
- No prose stripping
- No key renaming
- No enum coercion
- No field invention
- No slug normalization
- No multi-object recovery

### 5.2 `validate_compiled_source_response.py` (new)

```python
"""Validator for one model response (per-source contract)."""

from functools import cache
from typing import Any
from jsonschema import Draft202012Validator

@cache
def _validator() -> Draft202012Validator: ...

def validate(payload: Any) -> list[str]:
    """Schema validation. Returns [] if valid.
    Errors formatted as '$.pages[0].slug: <message>'.
    """

def semantic_check(payload: dict, *, source_id: str) -> list[str]:
    """Run AFTER schema validation passes. Returns [] if valid.
    Checks:
      1. payload['source_id'] == source_id (model echoed the id)
      2. summary_slug appears in [p['slug'] for p in pages]
      3. exactly one page has page_type='summary' AND slug == summary_slug
      4. every page's supports_page_existence[] contains source_id
    """

def main(argv: list[str] | None = None) -> int:
    """CLI: kdb-validate-response <file.json> [--source-id <id>]"""
```

### 5.3 `context_loader.py`

```python
"""Build a compact manifest snapshot for one source.

The LLM sees only {slug, title, page_type, outgoing_links}. No bodies,
paths, or timestamps (D8).
"""

from kdb_compiler.types import ContextPage, ContextSnapshot, PageType

def build_context_snapshot(
    manifest: dict,
    *,
    source_id: str,
    source_text: str,
    page_cap: int = 50,
) -> ContextSnapshot:
    """Pure. Scoped slice + depth-1 expansion, deterministic order, capped."""

# private helpers
def _seed_page_keys(manifest: dict, *, source_id: str, source_text: str) -> list[str]: ...
def _expand_depth1(manifest: dict, page_keys: list[str]) -> list[str]: ...
def _page_record_to_context(page_record: dict) -> ContextPage: ...
```

**Selection rule (locked)**:
1. **Seed pages** = union of:
   - pages whose `source_refs[].source_id == source_id`
   - pages whose `slug` appears as a whole-word match in `source_text`
2. **Depth-1 expansion** = targets of `outgoing_links[]` from seed pages, resolved against manifest
3. **Deduplicate**, preserving first-seen order
4. **Order** = seeds (sorted by slug) then depth-1 (sorted by slug)
5. **Cap** at `page_cap` (default 50) — seeds always in

**Emit per page**: only `{slug, title, page_type, outgoing_links}`. Drop bodies, paths, timestamps, hashes, source_refs.

### 5.4 `prompt_builder.py`

```python
"""Assemble the system + user prompt for one compile call."""

from dataclasses import dataclass
from functools import cache
from pathlib import Path
from kdb_compiler.types import ContextSnapshot

@dataclass
class BuiltPrompt:
    system: str
    user: str

@cache
def load_system_prompt(vault_root: Path) -> str:
    """Load <vault-root>/KDB/KDB-Compiler-System-Prompt.md. Cached per-process by vault_root.
    Path is hashable — no need to stringify at the call site."""

@cache
def load_response_schema_text() -> str:
    """Load compiled_source_response.schema.json as pretty JSON text (2-space indent)."""

def exemplar_response(source_id: str) -> dict:
    """One minimal valid response object for prompt inclusion.
    Always includes: source_id, summary_slug, pages (one summary page with
    supports_page_existence=[source_id]), log_entries, warnings.
    """

def build_prompt(
    *,
    vault_root: Path,
    source_id: str,
    source_text: str,
    context_snapshot: ContextSnapshot,
) -> BuiltPrompt:
    """Assemble (system, user) strings. Pure after load_* calls."""
```

**System prompt structure (locked)**:
```
<KDB-Compiler-System-Prompt.md full content>

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
  that — with honest content — and leave concept/article lists empty.
```

Rationale for removing the old "still return one object with warnings describing why" line: it contradicted `pages.minItems=1` + `supports_page_existence.minItems=1` and pressured the model to fabricate filler. Schema-level failure of the response is caught by `schema_ok=False`; that's the honest failure channel. The `warnings[]` field is for non-fatal observations, not as an escape hatch for non-compliance.

**User prompt structure (locked)**:
```
source_id: <source_id>

## SOURCE CONTENT
<verbatim source_text, no truncation>

## EXISTING CONTEXT (manifest snapshot)
<json.dumps(context_snapshot.to_dict(), indent=2)>

## RESPONSE SCHEMA
<load_response_schema_text() output>

## EXAMPLE RESPONSE
<json.dumps(exemplar_response(source_id), indent=2)>
```

### 5.5 `planner.py`

```python
"""Build CompileJob list from last_scan + manifest."""

from pathlib import Path
from kdb_compiler.types import CompileJob

def load_manifest(state_root: Path) -> dict:
    """Return {} if manifest.json is missing or empty."""

def eligible_source_ids(scan: dict) -> list[str]:
    """Return sorted to_compile ∖ binary sources.

    Cross-references scan['to_compile'] with scan['files'][*] and drops any
    entry whose matching file record has is_binary=True. Returns paths in
    scan order (already sorted in the scanner).

    Rationale: kdb_scan puts every NEW/CHANGED file into to_compile
    irrespective of is_binary (kdb_scan.py:325). Binaries cannot be read as
    UTF-8 and have no meaningful LLM contract in M2 v1. A later milestone
    (v1.1) will add a metadata-only page path for binaries; for now they
    stay in manifest and are skipped by compile.
    """

def build_jobs(
    scan: dict,
    manifest: dict,
    vault_root: Path,
    *,
    context_page_cap: int = 50,
) -> list[CompileJob]:
    """Pure-ish. Reads source files (for slug-match context selection).
    One job per source_id in eligible_source_ids(scan)."""

def plan(
    vault_root: Path,
    *,
    scan: dict,
    state_root: Path | None = None,
    context_page_cap: int = 50,
) -> list[CompileJob]:
    """I/O shell. Loads manifest, delegates to build_jobs."""

def main(argv: list[str] | None = None) -> int:
    """CLI: kdb-plan --vault-root <path> [--json] [--page-cap 50]"""
```

### 5.6 `resp_stats_writer.py`

```python
"""Atomic resp-stats writer and builder."""

import hashlib
import os
from pathlib import Path
from kdb_compiler.atomic_io import atomic_write_json
from kdb_compiler.call_model import ModelResponse
from kdb_compiler.prompt_builder import BuiltPrompt
from kdb_compiler.run_context import RunContext
from kdb_compiler.types import RespStatsRecord

def safe_source_id(source_id: str) -> str:
    """Filesystem-safe key for resp-stats record filename.
    KDB/raw/foo/bar.md → KDB__raw__foo__bar.md.<8-hex>
    The 8-hex suffix is sha256(source_id)[:8] — disambiguates collisions
    (e.g. 'a/b.md' vs 'a__b.md' would otherwise map to the same name).
    Not round-trippable; the filename is a key, not a path recovery.
    """

def _sha256(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()

def build_parsed_summary(parsed_json: dict) -> ParsedSummary:
    """Reduce a validated (or parse-ok) payload to shape digest.
    Never raises — missing fields produce None / 0 / [] entries.
    """

def build_resp_stats(
    *,
    ctx: RunContext,
    source_id: str,
    prompt: BuiltPrompt | None,             # None only if prompt-build itself failed
    raw_response_text: str,                  # "" if no response captured
    model_response: ModelResponse | None,    # None if call failed pre-response
    extract_ok: bool,
    parse_ok: bool,
    parsed_json: dict | None,
    schema_ok: bool,
    schema_errors: list[str],
    semantic_ok: bool,
    semantic_errors: list[str],
) -> RespStatsRecord:
    """Assemble record. Hashes always computed. See §7 for the gating story.

    Always-on fields: metadata, hashes, flags, error lists, parsed_summary
    (when parse_ok=True). Env-gated by KDB_RESP_CAPTURE_FULL=='1':
    parsed_json, system_prompt, user_prompt, raw_response_text.

    If model_response is None (pre-response failure — SDK error, network,
    config, or prompt-build failure), provider/model are empty strings;
    input_tokens/output_tokens/latency_ms/attempts are 0; response_hash is
    the sentinel "sha256:none" to distinguish 'no response captured' from
    'empty-string response'. If prompt is None (prompt-build failed),
    prompt_hash is also "sha256:none".

    parsed_summary is built from parsed_json when parse_ok=True, else None.
    """

def write_resp_stats(record: RespStatsRecord, state_root: Path) -> Path:
    """Atomic write to <state_root>/llm_resp/<run_id>/<safe_source_id>.json.
    Ensures the parent directory exists via
    `dir.mkdir(parents=True, exist_ok=True)` before the atomic write —
    `atomic_write_json` writes a tempfile next to the target and renames,
    so the directory must pre-exist. Returns the written path.
    """
```

Env contract: `KDB_RESP_CAPTURE_FULL=1` → capture full bodies. Any other value (or unset) → omit.

### 5.7 `compiler.py`

```python
"""Per-source compile orchestration."""

from pathlib import Path
from kdb_compiler.run_context import RunContext
from kdb_compiler.types import CompiledSource, CompileJob, CompileResult

def source_text_for(job: CompileJob) -> str:
    """Read job.abs_path as UTF-8."""

def compile_one(
    job: CompileJob,
    *,
    vault_root: Path,
    state_root: Path,
    ctx: RunContext,
    provider: str,
    model: str,
    max_tokens: int,
) -> tuple[CompiledSource | None, list[dict], list[str], str | None]:
    """
    Returns (compiled_source | None, log_entries, warnings, error_str | None).

    ALWAYS writes one RespStatsRecord per call, regardless of outcome.

    See §9 for the locked step-by-step flow.
    """

def run_compile(
    vault_root: Path,
    *,
    state_root: Path,
    scan: dict,
    ctx: RunContext,
    provider: str = "anthropic",
    model: str = "claude-opus-4-7",
    max_tokens: int = 4096,
    write: bool = True,
) -> CompileResult:
    """Plan → per-source compile → aggregate → optionally write compile_result.json."""

def write_compile_result(result: CompileResult, state_root: Path) -> None:
    """Atomic write to state_root/compile_result.json."""

def main(argv: list[str] | None = None) -> int:
    """CLI: kdb-compile-sources --vault-root <path> [--provider anthropic]
    [--model claude-opus-4-7] [--max-tokens 4096] [--dry-run]"""
```

### 5.8 `response_replay.py`

```python
"""Replay harness: run stored responses through normalizer + validators."""

@dataclass
class ReplayFixture:
    case_id: str
    source_id: str
    stored_response_text: str
    expected_extract_ok: bool
    expected_parse_ok: bool
    expected_schema_ok: bool
    expected_semantic_ok: bool
    notes: str

@dataclass
class ReplayResult:
    case_id: str
    extract_ok: bool
    parse_ok: bool
    schema_ok: bool
    semantic_ok: bool
    matches_expected: bool
    error_detail: str | None

def load_fixtures(fixtures_dir: Path) -> list[ReplayFixture]: ...
def replay_case(fixture: ReplayFixture) -> ReplayResult: ...
def print_report(results: list[ReplayResult]) -> None: ...

def main(argv: list[str] | None = None) -> int:
    """CLI: kdb-replay --replay <fixtures-dir>
    Exit 0 iff all cases match expectations."""
```

**Fixture layout** per case:
```
kdb_compiler/tests/fixtures/response_replay/case01_minimal/
  source.md                  # raw input (informational, not replayed)
  stored_response.txt        # raw model output string (may include fences/prose)
  case.json                  # { "source_id": "...",
                             #   "expected_extract_ok": true,
                             #   "expected_parse_ok": true,
                             #   "expected_schema_ok": true,
                             #   "expected_semantic_ok": true,
                             #   "notes": "..." }
```

**Seed cases** (3 to ship in Step I):
1. `case01_minimal_summary` — happy path, single summary page
2. `case02_schema_violation` — bad slug pattern
3. `case03_semantic_violation` — summary_slug not in pages

---

## 6. Prompt Skeleton (see §5.4)

Token budget sanity check (back-of-envelope):
- KDB-Compiler-System-Prompt.md: ~1,500 tokens
- Response contract rules: ~200 tokens
- Schema JSON pretty-printed: ~1,200 tokens
- Exemplar JSON: ~400 tokens
- Context snapshot (50 pages × ~40 tokens): ~2,000 tokens
- Source content: typical 500-5,000 tokens

**Typical prompt**: 5,800-10,300 input tokens. Well inside any provider's context window. `compile_meta.input_tokens` will capture the actual cost on every call — if token bloat is real we'll see it immediately.

---

## 7. Resp-Stats Record — Exact Shape

Per the always-on vs. gated split:

Default (capture-full OFF):
```json
{
  "run_id": "2026-04-19T14-30-00Z_a3f9",
  "source_id": "KDB/raw/foo.md",
  "provider": "anthropic",
  "model": "claude-opus-4-7",
  "attempts": 1,
  "latency_ms": 4321,
  "input_tokens": 7234,
  "output_tokens": 1850,

  "prompt_hash": "sha256:...",
  "response_hash": "sha256:...",

  "extract_ok": true,
  "parse_ok": true,
  "schema_ok": true,
  "semantic_ok": true,

  "schema_errors": [],
  "semantic_errors": [],

  "parsed_summary": {
    "summary_slug": "transformer-architecture",
    "page_count": 4,
    "page_types": {"summary": 1, "concept": 2, "article": 1},
    "slugs": ["transformer-architecture", "self-attention", "positional-encoding", "paper-vaswani-2017"],
    "outgoing_link_count": 7,
    "log_entry_count": 0,
    "warning_count": 1,
    "source_id_echoed": "KDB/raw/foo.md"
  },

  "parsed_json": null,
  "system_prompt": null,
  "user_prompt": null,
  "raw_response_text": null
}
```

With `KDB_RESP_CAPTURE_FULL=1`, the four trailing `null`s become:
- `parsed_json` — full validated object (with generated page bodies)
- `system_prompt`, `user_prompt` — full prompt strings
- `raw_response_text` — unparsed model output (may include fences/prose)

`parsed_summary` is always present when `parse_ok=True`. Hashes are always computed (prompt_hash from BuiltPrompt; response_hash from raw_response_text or `"sha256:none"` sentinel if no response). This enables aggregate analytics from default records and full debugging via env flag.

Rationale: `parsed_json` contains `pages[].body` which is the bulk of the response payload. Gating it under the same flag as raw bodies keeps the default record lightweight (metadata + shape digest + hashes + flags) while preserving a full debug path when needed.

---

## 8. `kdb_compile.py` Step 5 Change

**Current** (`kdb_compile.py:60-66`):
```python
cr_path = state_root / "compile_result.json"
if not cr_path.exists():
    return _fail([
        f"compile_result.json not found at {cr_path} — "
        "M2 compile step is not implemented yet; supply a pre-made compile_result.json "
        "fixture or run planner/compiler once available"
    ])
```

**New**:
```python
cr_path = state_root / "compile_result.json"
if cr_path.exists():
    # Branch 1 — fixture-backed (M1.7 path, unchanged)
    try:
        cr = json.loads(cr_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return _fail([f"compile_result.json unreadable: {exc}"])
else:
    # Branch 2 — live compile (no fixture present). Covers both the
    # "sources to compile" case and the clean-scan no-op case.
    from kdb_compiler import compiler
    try:
        cr_obj = compiler.run_compile(
            vault_root,
            state_root=state_root,
            scan=scan_dict,
            ctx=ctx,
            write=not dry_run,
        )
    except Exception as exc:
        return _fail([f"compiler.run_compile failed: {type(exc).__name__}: {exc}"])
    cr = cr_obj.to_dict()
```

`compiler.run_compile` handles the empty-jobs case internally (see §9):
when `planner.plan` returns `[]` (no eligible sources — clean scan or
binary-only changes), it synthesizes a successful empty `CompileResult`
with a single info-level log entry and `success=True`. The orchestrator
then proceeds through apply / write as a no-op (new manifest equals prior
manifest, no pages written, journal records the no-op run).

M1.7's fixture-backed tests continue to exercise branch 1 unchanged. New
tests cover branch 2 (live compile with sources) and branch 2-empty
(clean scan, no sources, no error).

---

## 9. `compile_one` Flow — Locked Step-by-Step

The implementation uses a **scaffold-and-fill** pattern: a mutable state dict is
initialized at function entry, each stage updates it, and a single
`finally` block writes the resp-stats record. This guarantees the invariant:
**exactly one resp-stats record per `compile_one` call — including source-read
failures and prompt-build failures.**

```
# --- scaffold (before any work that can raise) ---
state = {
    "prompt": None,                 # BuiltPrompt | None
    "raw_response_text": "",
    "model_response": None,         # ModelResponse | None
    "extract_ok": False,
    "parse_ok": False,
    "parsed_json": None,
    "schema_ok": False,
    "schema_errors": [],
    "semantic_ok": False,
    "semantic_errors": [],
    "error": None,                  # str | None  — first failure reason
    "compiled_source": None,        # CompiledSource | None
    "log_entries": [],
    "warnings": [],
}

try:
    # --- read source ---
    try:
        source_text = Path(job.abs_path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        state["error"] = f"{source_id}: source read failed: {type(e).__name__}: {e}"
        return (None, [], [], state["error"])

    # --- build prompt ---
    try:
        state["prompt"] = prompt_builder.build_prompt(
            vault_root=vault_root,
            source_id=source_id,
            source_text=source_text,
            context_snapshot=job.context_snapshot,
        )
    except Exception as e:
        state["error"] = f"{source_id}: prompt build failed: {type(e).__name__}: {e}"
        return (None, [], [], state["error"])

    # --- model call ---
    try:
        state["model_response"] = call_model_with_retry(
            ModelRequest(
                provider=provider, model=model,
                system=state["prompt"].system,
                prompt=state["prompt"].user,
                temperature=0.0, max_tokens=max_tokens,
            )
        )
        state["raw_response_text"] = state["model_response"].text
    except Exception as e:
        state["error"] = f"{source_id}: model call failed: {type(e).__name__}: {e}"
        return (None, [], [], state["error"])

    # --- extract ---
    try:
        json_text = response_normalizer.extract_json_text(state["raw_response_text"])
        state["extract_ok"] = True
    except ValueError:
        state["error"] = f"{source_id}: response was not a bare object or single fenced block"
        return (None, [], [], state["error"])

    # --- parse ---
    try:
        state["parsed_json"] = json.loads(json_text)
        state["parse_ok"] = True
    except json.JSONDecodeError as e:
        state["error"] = f"{source_id}: invalid JSON: {e.msg} at line {e.lineno}"
        return (None, [], [], state["error"])

    # --- schema ---
    state["schema_errors"] = validate_compiled_source_response.validate(state["parsed_json"])
    state["schema_ok"] = (state["schema_errors"] == [])
    if not state["schema_ok"]:
        state["error"] = f"{source_id}: schema validation failed: {state['schema_errors'][0]}"
        return (None, [], [], state["error"])

    # --- semantic ---
    state["semantic_errors"] = validate_compiled_source_response.semantic_check(
        state["parsed_json"], source_id=source_id
    )
    state["semantic_ok"] = (state["semantic_errors"] == [])
    if not state["semantic_ok"]:
        state["error"] = f"{source_id}: semantic check failed: {state['semantic_errors'][0]}"
        return (None, [], [], state["error"])

    # --- success ---
    parsed = state["parsed_json"]
    mr = state["model_response"]
    state["compiled_source"] = CompiledSource(
        source_id=parsed["source_id"],
        summary_slug=parsed["summary_slug"],
        pages=[PageIntent(**p) for p in parsed["pages"]],
        concept_slugs=parsed.get("concept_slugs", []),
        article_slugs=parsed.get("article_slugs", []),
        compile_meta=CompileMeta(
            provider=mr.provider, model=mr.model,
            input_tokens=mr.input_tokens, output_tokens=mr.output_tokens,
            latency_ms=mr.latency_ms, attempts=mr.attempts,
            ok=True, error=None,
        ),
    )
    state["log_entries"] = parsed["log_entries"]
    state["warnings"]    = parsed["warnings"]
    return (
        state["compiled_source"],
        state["log_entries"],
        state["warnings"],
        None,
    )

finally:
    # --- ALWAYS write exactly one resp-stats record, regardless of which stage failed ---
    record = build_resp_stats(
        ctx=ctx,
        source_id=source_id,
        prompt=state["prompt"],                     # None if prompt-build failed
        raw_response_text=state["raw_response_text"],
        model_response=state["model_response"],     # None if model call failed
        extract_ok=state["extract_ok"],
        parse_ok=state["parse_ok"],
        parsed_json=state["parsed_json"],
        schema_ok=state["schema_ok"],
        schema_errors=state["schema_errors"],
        semantic_ok=state["semantic_ok"],
        semantic_errors=state["semantic_errors"],
    )
    write_resp_stats(record, state_root)
```

**Key invariants** (enforced by code structure):
- Exactly one `write_resp_stats` per `compile_one` call, via the single `finally` block.
- Every early-return goes through the same `finally`.
- `state` is the only mutable carrier — no duplicate resp-stats construction sprinkled through the flow.
- Source-read failures and prompt-build failures are also captured (with `model_response=None` and `prompt=None` respectively).

### `run_compile` aggregation

```
jobs = planner.plan(vault_root, scan=scan, state_root=state_root, context_page_cap=50)

compiled_sources: list[CompiledSource] = []
all_log_entries: list[dict] = []
all_warnings: list[str] = []
errors: list[str] = []

# Empty-jobs no-op: record it as an info log for downstream visibility,
# but treat as success (see success semantics below).
if not jobs:
    all_log_entries.append({
        "level": "info",
        "message": "no eligible sources to compile (empty to_compile or all filtered)",
        "related_slugs": [],
        "related_source_ids": [],
    })

for job in jobs:
    cs, logs, warns, err = compile_one(job, vault_root=..., state_root=..., ctx=ctx, ...)
    if cs is not None:
        compiled_sources.append(cs)
        all_log_entries.extend(logs)
        all_warnings.extend(warns)
    if err is not None:
        errors.append(err)

result = CompileResult(
    run_id=ctx.run_id,
    success=(len(errors) == 0),     # empty+clean = success; any per-source failure = false
    compiled_sources=compiled_sources,
    log_entries=[LogEntry(**le) for le in all_log_entries],
    errors=errors,
    warnings=all_warnings,
)

if write:
    write_compile_result(result, state_root)

return result
```

Success semantics clarified: `success = (len(errors) == 0)`. This means:
- Clean scan with no sources → `success=True`, `compiled_sources=[]`, no errors. Valid no-op.
- 3 sources, all compile → `success=True`, `compiled_sources=[3]`, no errors.
- 3 sources, 1 fails → `success=False`, `compiled_sources=[2]`, `errors=[1]`. Partial result.
- 3 sources, all fail → `success=False`, `compiled_sources=[]`, `errors=[3]`.

Prior rule `len(compiled_sources) > 0` conflated "did anything compile"
with "is the run valid"; the clarified rule separates them.

---

## 10. Test Matrix

### `test_response_normalizer.py` (5 cases)
- bare object accepted
- fenced ` ```json ` block accepted
- fenced ` ``` ` block (no lang) accepted
- prose-before-object → ValueError
- prose-after-object → ValueError
- malformed JSON → ValueError (through parse_json_object)
- multiple-objects-in-one-string → ValueError

### `test_validate_compiled_source_response.py` (~10 cases)
- minimal valid object passes schema
- minimal valid object passes semantic
- missing `summary_slug` → schema error
- bad slug pattern → schema error
- `supports_page_existence` empty → schema error
- `source_id` mismatch → semantic error
- `summary_slug` not in pages → semantic error
- two summary pages → semantic error
- page without source_id in `supports_page_existence` → semantic error
- extra field → schema error (additionalProperties:false)

### `test_resp_stats_writer.py` (~9 cases)
- `safe_source_id` stable + sha256 suffix disambiguates `a/b.md` vs `a__b.md`
- **metadata+parsed_summary record written when env unset; parsed_json is null**
- **full record (parsed_json + bodies) written when env=`1`**
- atomic write path correct
- hashes deterministic
- `model_response=None` → response_hash="sha256:none", tokens/latency=0
- **`prompt=None` → prompt_hash="sha256:none"**
- state dir created if missing (`mkdir(parents=True, exist_ok=True)`)
- `parsed_summary` correctly reduces a full parsed_json (counts, page_types, slugs)

### `test_context_loader.py` (~8 cases)
- source_refs match selection
- slug-in-text match selection
- depth-1 expansion via outgoing_links
- dedup (page matches both source_refs and slug-in-text)
- cap honored (seeds > cap → only first N)
- empty manifest → empty snapshot
- fields filtered (no body, no path, no timestamps)
- deterministic ordering across runs

### `test_prompt_builder.py` (~6 cases, snapshot-based)
- `load_system_prompt` returns vault file
- `load_response_schema_text` returns schema with expected keys
- `build_prompt` system snapshot includes KDB-Compiler-System-Prompt.md + contract rules
- `build_prompt` user snapshot includes source_id, source_text, context, schema, exemplar
- exemplar includes the supplied source_id
- contract lines "EXACTLY ONE JSON object" and "source_id MUST echo" present

### `test_planner.py` (~7 cases)
- one job per to_compile entry
- `abs_path` resolution
- `context_snapshot` populated per job
- empty to_compile → empty job list
- manifest missing → jobs still produced with minimal context
- **binary filter**: to_compile=[a.md, b.pdf] with b.pdf is_binary=True → only a.md in jobs
- **all-binary case**: to_compile entries all is_binary=True → empty job list (no crash)

### `test_compiler.py` (~15 cases, all with mocked `call_model_with_retry`)
- happy path: 1 source → 1 compiled_source, meta threaded
- **source-read failure** (missing file) → errors[], resp-stats record with model_response=None, prompt=None
- **prompt-build failure** (mocked to raise) → errors[], resp-stats record written with prompt=None
- SDK exception → errors[], no compiled_source, resp-stats record model_response=None
- extract failure (prose around object) → errors[], resp-stats record extract_ok=False
- parse failure (broken JSON) → resp-stats record parse_ok=False, parsed_json=None, parsed_summary=None
- schema failure (bad slug) → resp-stats record schema_ok=False, parsed_summary populated
- semantic failure (no summary page) → resp-stats record semantic_ok=False
- mixed run: 3 sources, 1 pass + 2 fail → **success=false**, errors has 2, compiled_sources has 1
- **empty-jobs run** (planner returns []) → success=true, compiled_sources=[], log has 1 info entry
- all-fail run → success=false
- `compile_meta` threaded correctly from ModelResponse
- `dry_run=True` skips compile_result.json write
- **resp-stats record written exactly once per `compile_one` call** — including source-read and prompt-build failure paths
- `run_compile` returns a valid `CompileResult` that passes `validate_compile_result`

### `test_response_replay.py` (~4 cases)
- happy fixture: all flags match expected
- schema-fail fixture: matches expected
- semantic-fail fixture: matches expected
- CLI exit 0 iff all match, 1 otherwise

### `test_m2_first_compile.py` (env-blocked)
- Excluded from default CI via pytest `--ignore`
- Loads 1 real source from `kdb_compiler/tests/fixtures/response_replay/case01_minimal/source.md`
- Calls real Anthropic API
- Asserts: compiled_source returned, passes schema + semantic checks, resp-stats record written

### `test_kdb_compile.py` additions (~3 cases — extend existing)
- compile_result.json absent + to_compile non-empty + mocked compiler → success, compiler invoked
- **compile_result.json absent + to_compile empty + mocked compiler → success (no-op), no pages written, manifest and journal still written**
- compile_result.json present → existing fixture branch unchanged (no compiler invocation)

---

## 11. Implementation Order (11 commits, sequential)

Each step: implement → tests green → user approves → commit.

| # | Step | Files | Commit gate |
|---|---|---|---|
| A1 | Schemas + types additions | `compiled_source_response.schema.json`, `compile_result.schema.json` edit, `types.py` (ContextPage, ContextSnapshot, CompileJob, CompileMeta, RespStatsRecord, extend CompiledSource) | Full existing suite green (207) + new types importable; schema file loads via `Draft202012Validator` |
| A2 | `ModelResponse.attempts` threading | `call_model.py` (+3 lines), `call_model_retry.py` (+5 lines) | Existing `test_call_model*.py` green (env-blocked tests unchanged); one new unit test confirms `response.attempts` reflects actual retry count |
| B | `validate_compiled_source_response` | `validate_compiled_source_response.py`, tests | All validator tests pass |
| C | `response_normalizer` shrink | `response_normalizer.py`, tests | Normalizer tests pass; grep confirms no semantic code |
| D | `resp_stats_writer` | `resp_stats_writer.py`, tests | Writer tests pass under both env states |
| E | `context_loader` | `context_loader.py`, tests | Loader tests pass; deterministic ordering verified |
| F | `prompt_builder` + `KDB/KDB-Compiler-System-Prompt.md` verified present | `prompt_builder.py`, tests | Snapshot tests pass; contract lines present |
| G | `planner` | `planner.py`, tests, `pyproject.toml` (kdb-plan) | Planner tests pass; CLI smoke works |
| H | `compiler` (mocked seam) | `compiler.py`, tests, `pyproject.toml` | All compiler tests pass; resp-stats record written every case |
| I | `kdb_compile.py` Step 5 hybrid | `kdb_compile.py`, `test_kdb_compile.py` new cases | M1.7 existing tests unchanged; new cases pass |
| J | `response_replay` + 3 fixtures + **first real compile** | `response_replay.py`, fixtures, `test_m2_first_compile.py`, `pyproject.toml` | Replay tests pass; **user runs `kdb-compile` against real `~/Droidoes/*/docs/` seeds and inspects wiki/ output for quality** |

Step J is the green-light — all prior steps are preparation.

---

## 12. Open Verifications for Phase 4 (resolve at Step A)

Before any implementation on a given step, verify these:

- [ ] `~/Obsidian/KDB/KDB-Compiler-System-Prompt.md` is readable. If not, Step F is blocked.
- [ ] `ModelResponse` in `call_model.py` has `attempts` field after Step A's edit.
- [ ] `pyproject.toml` accepts 4 new `[project.scripts]` entries: `kdb-plan`, `kdb-compile-sources`, `kdb-replay`, `kdb-validate-response`.
- [ ] `PageType`, `PageStatus`, `Confidence` literals in `types.py` match the per-source schema enums exactly.

---

## 13. Explicit Non-Goals for M2 v1 (defer to v1.1+)

- Batching (N sources per call)
- Multi-provider benchmark (E3)
- Anthropic tool-use-as-structured-output
- Baseline diff dashboard
- p50/p95 latency/cost metrics in replay report
- Re-compile of UNCHANGED sources via concept propagation
- Prompt caching (Anthropic cache breakpoints)

None of these are blocked by M2 v1's shape — they're additive when evidence motivates them.

---

## 14. Success Criteria for M2

1. `python3 -m pytest kdb_compiler/tests --ignore=...env-blocked...` → 207 + ~74 new = ~281 tests green.
2. `kdb-replay --replay kdb_compiler/tests/fixtures/response_replay/` → all seed cases match expectations.
3. `kdb-compile --vault-root ~/Obsidian` with 3-5 real seed docs in `KDB/raw/` → produces valid `compile_result.json`, applies to `KDB/wiki/`, and user confirms output quality on inspection.
4. Resp-stats records exist under `KDB/state/llm_resp/<run_id>/` for every call made.
5. `compile_meta` present on every `compiled_sources[i]` in live compiles; absent in fixture-backed runs.
6. User approves commit of Step J.

---

**End of blueprint.** Once approved, Phase 4 begins at Step A.

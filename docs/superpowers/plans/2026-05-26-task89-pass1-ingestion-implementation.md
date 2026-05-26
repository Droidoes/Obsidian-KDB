# Task #89 Pass-1 Ingestion + Compile-side Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended for this plan size) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship Task #89 Component #1 (Enrichment) end-to-end — Pass-1 LLM producer that emits sectionalized YAML frontmatter on every in-scope source, plus the compile-side consumption layer that uses Pass-1 output for Source-node population (D-89-17/D-89-18). This is the first ingestion-pipeline component to land code (Task #88 end B of the tunnel).

**Architecture:** Two-pass enrichment pipeline. Pass-1 (this plan): per-source LLM call returns structured JSON envelope (D-89-13) → deterministic post-processor applies `force_signal`/`force_noise` overrides (§4) → serializes JSON to YAML frontmatter (D-89-16 sectionalized: GraphDB-input + Audit) → atomically writes the source in-place (body untouched) → emits replay archive sidecar + run journal entry. Pass-2 (existing compile, amended): `source_text_for()` parses the GraphDB-input section to populate `Source.{domain, source_type, author, summary}` columns + seed entity extraction with `key_entities` + merge `summary + key_themes` via LLM (D-89-18). Audit section ignored by Pass-2.

**Tech Stack:** Python 3.10+, existing `call_model.py` LLM proxy (structured-output via `json_mode=True` and `response_format`), Jinja2 prompt templates, PyYAML for frontmatter, JSON Schema validation, Kuzu GraphDB (schema migration v2.2 → v2.3), pytest TDD throughout.

---

## §0 — Plan setup, locks, and sequencing rationale

### Locked decisions inherited (do not re-litigate)

From Task #89 v0.2.1 blueprint (commit `1664053`):
- **D-89-12** Option B — Pass-1 emits flat `key_entities` only; compile owns `LINKS_TO` resolution against live GraphDB. No corpus_index. No wikilink suggestions in v1.
- **D-89-13** Structured JSON envelope from LLM; deterministic Python embeds YAML frontmatter; body never present in LLM output.
- **D-89-14** Daily Notes default to `force_noise: [Daily Notes/**]`; LLM judges content substance only.
- **D-89-15** LLM runs on every in-scope source; no pre-LLM short-circuit on `force_noise` matches.
- **D-89-16** Frontmatter sectionalized — GraphDB-input section (Pass-2 reads) + Audit section (Pass-2 ignores).
- **D-89-17** Compile consumes frontmatter in v1 (NOT v1.x deferral); required Source schema additions: `Source.summary STRING`, `Source.author STRING`, `Source.domain STRING`.
- **D-89-18** Compile LLM merges `summary + key_themes` into `Source.summary` (NOT verbatim copy).

From this session 2026-05-26 evening:
- **F1 (Source.domain shape)** — STRING column on Source (NOT new Source→Domain edge). Rationale: NW-4 v0.4 is flat-single-domain; column is contained to schema.py + ingestor.py write paths; no `verifier.py`/`snapshot.py` churn.
- **F2 (scope-config location)** — `kdb_compiler/config/scope-config.yaml`. Mirrors NW-4's planned `domains.json` sibling.
- **CLI entry point** — `kdb-enrich`. Reserve `kdb-ingest` for the Component #3/#6 umbrella when those land.
- **NW-4 v0.4 ratified** — 23 domains; this plan materializes the never-written `kdb_compiler/config/domains.json` file from `docs/task88-nw4-domain-list-v0.4.md`.
- **NW-7 v0.2 ratified** — 21 source_types; this plan materializes `kdb_compiler/config/source_types.json` from `docs/task89-nw7-source-type-list-v0.2.md`.

### Phase sequencing rationale

Phases run in this order: **Phase 0 (pre-flight scan) → Phase A (provider verification) → Phase C (Pass-1 producer) → Phase B (schema migration) → Phase D (compile-side integration) → Phase E (end-to-end acceptance)**.

**Why C before B (not the natural-feeling B before C):** Per D-89-6, Pass-1 is purely filesystem-native — it does NOT write to GraphDB in v1. Schema migration v2.2 → v2.3 is needed ONLY by Phase D (compile-side consumption). Doing C first means schema migration runs against real Pass-1 output, not paper specs. Lower risk than the inverse.

### Naming collision callout

A `graphdb_kdb/ingestor.py` module already exists — it is the GraphDB-write-path ingestor (consumes compile output, writes Source/Entity/Page nodes + edges). This plan creates `kdb_compiler/ingestion/` — the Pass-1 producer that writes enriched source markdown back to disk. **Different scope, different package, near-identical names. Do not confuse the two when navigating the codebase.**

### Execution recommendation

Subagent-driven execution per `superpowers:subagent-driven-development`. Fresh subagent per task; Joseph reviews between tasks. Inline batch execution is feasible but risks context bloat across 22 tasks.

---

## §1 — File structure map

### New files (create)

```
kdb_compiler/
├── config/                                          (NEW DIRECTORY)
│   ├── domains.json                                 (NEW — NW-4 v0.4, 23 entries)
│   ├── source_types.json                            (NEW — NW-7 v0.2, 21 entries)
│   └── scope-config.yaml                            (NEW — F2 lock)
└── ingestion/                                       (NEW DIRECTORY — Pass-1 package)
    ├── __init__.py                                  (NEW)
    ├── config_loader.py                             (NEW — loads domains/source_types/scope-config)
    ├── pass1_schema.py                              (NEW — JSON Schema + dataclass for envelope)
    ├── pass1_prompt.py                              (NEW — Jinja2-based prompt construction)
    ├── pass1_prompt.j2                              (NEW — Jinja2 template)
    ├── pass1_caller.py                              (NEW — LLM call + retry + parse)
    ├── overrides.py                                 (NEW — force_signal/force_noise post-LLM layer)
    ├── frontmatter_embedder.py                      (NEW — YAML serialize + merge + atomic write)
    ├── replay_archive.py                            (NEW — sidecar writer)
    ├── run_journal.py                               (NEW — Pass-1 run journal)
    ├── enrich.py                                    (NEW — enrich_one() top-level orchestrator)
    └── kdb_enrich.py                                (NEW — CLI entry point)

kdb_compiler/tests/                                  (EXISTING — add test files here per convention)
├── test_pass1_config_loader.py                      (NEW)
├── test_pass1_schema.py                             (NEW)
├── test_pass1_prompt.py                             (NEW)
├── test_pass1_overrides.py                          (NEW)
├── test_pass1_frontmatter_embedder.py               (NEW)
├── test_pass1_replay_archive.py                     (NEW)
├── test_pass1_run_journal.py                        (NEW)
├── test_pass1_enrich.py                             (NEW)
└── test_pass1_end_to_end.py                         (NEW — Phase E acceptance test)

scripts/                                             (EXISTING)
└── verify_structured_output_parity.py               (NEW — Phase A provider smoke test)

docs/                                                (EXISTING)
└── task89-pass1-provider-parity-2026-05-26.md       (NEW — Phase A findings)
```

### Existing files (modify)

```
kdb_compiler/
├── compiler.py                                      (line 104-107: rewrite source_text_for())
├── prompt_builder.py                                (compile prompt template amendments)
└── pyproject.toml                                   (add `kdb-enrich` entry point + new deps)

graphdb_kdb/
├── schema.py                                        (add Source.summary/author/domain + _migrate_2_2_to_2_3)
└── ingestor.py                                      (write Source.summary/author/domain columns)

graphdb_kdb/tests/
└── test_schema_migration.py                         (add v2.2 → v2.3 migration tests)
```

### Acceptance file (read at end)

Phase E asserts the integration via a real enriched source flow: write to `tests/fixtures/sample_source.md`, run Pass-1, run compile, inspect Source-node properties + Entity nodes in test GraphDB.

---

## §2 — Tasks

---

### Phase 0 — Pre-flight (5 min, manual)

#### Task 0.1: Vault alias scan

**Files:**
- Inspect: `~/Obsidian/**/*.md` for pre-existing `source_type:` or `domain:` frontmatter values

- [ ] **Step 1: Scan vault for existing frontmatter values**

Run:
```bash
grep -rh "^source_type:" ~/Obsidian/ 2>/dev/null | sort -u
grep -rh "^domain:" ~/Obsidian/ 2>/dev/null | sort -u
```

- [ ] **Step 2: Record findings**

For each unique value found that does NOT appear in NW-7 v0.2 list (21 IDs) or NW-4 v0.4 list (23 IDs):
- Note in `docs/task89-pass1-provider-parity-2026-05-26.md` (or new file `docs/task89-pass1-vault-alias-scan-2026-05-26.md`)
- Decide: alias to a current ID, or force re-enrichment on next Pass-1 run

Expected outcome: most likely the vault has zero such frontmatter (NW-4/NW-7 vocabs never had a Pass-1 producer); document the finding to confirm.

- [ ] **Step 3: Commit findings doc**

```bash
git add docs/task89-pass1-vault-alias-scan-2026-05-26.md
git commit -m "docs(task89): pre-Pass-1 vault alias scan — record any existing source_type/domain values"
```

---

### Phase A — Provider structured-output verification (OQ-89-13)

#### Task A.1: Write provider smoke script

**Files:**
- Create: `scripts/verify_structured_output_parity.py`
- Test: (manual; this IS the test script)

- [ ] **Step 1: Write the smoke script**

```python
"""verify_structured_output_parity — fire a minimal Pass-1-shaped JSON envelope
request at each candidate provider; record pass/fail.

Usage:
    python scripts/verify_structured_output_parity.py

Output:
    Per-provider pass/fail printed to stdout + recorded to
    docs/task89-pass1-provider-parity-2026-05-26.md
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from kdb_compiler.call_model import ModelRequest, call_model, ModelConfigError

# Candidate models for Pass-1 (subset of kdb_benchmark/models.json that advertises
# structured-output support). Adjust based on registry state.
CANDIDATES = [
    ("deepseek", "deepseek-v4-flash"),
    ("gemini", "gemini-3.1-flash-lite"),
    ("anthropic", "claude-haiku-4-5"),
    ("openai", "gpt-5.4-mini"),
    ("xai", "grok-4-1-fast-reasoning"),
]

PROMPT = """Given this source content, return a JSON envelope matching the
schema below.

SOURCE:
This is a test source about value investing principles, focusing on margin
of safety and circle of competence. Written by Joseph (2026-05-26).

Return ONLY a valid JSON object with these fields:
{
  "kdb_signal": "signal" or "noise",
  "domain": one of ["value-investing", "ai-ml", "other"],
  "source_type": one of ["blog", "post", "article", "other"],
  "author": string or null,
  "summary": string (1-3 sentences),
  "key_entities": list of strings,
  "key_themes": list of strings,
  "confidence": number 0.0 to 1.0
}
"""

def smoke(provider: str, model: str) -> tuple[bool, str]:
    req = ModelRequest(
        provider=provider,
        model=model,
        prompt=PROMPT,
        json_mode=True,
        temperature=0.0,
        max_tokens=1024,
    )
    try:
        resp = call_model(req)
        parsed = json.loads(resp.text)
        required = {"kdb_signal", "domain", "source_type", "summary", "key_entities"}
        missing = required - set(parsed.keys())
        if missing:
            return False, f"missing fields: {missing}"
        return True, f"ok ({resp.latency_ms}ms, {resp.input_tokens}/{resp.output_tokens} tok)"
    except json.JSONDecodeError as e:
        return False, f"non-JSON output: {e}"
    except ModelConfigError as e:
        return False, f"config error: {e}"
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"


def main():
    results = []
    for provider, model in CANDIDATES:
        ok, msg = smoke(provider, model)
        verdict = "PASS" if ok else "FAIL"
        print(f"{verdict}  {provider:12s} {model:30s}  {msg}")
        results.append((provider, model, ok, msg))
    fail_count = sum(1 for _, _, ok, _ in results if not ok)
    sys.exit(fail_count)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit the script**

```bash
git add scripts/verify_structured_output_parity.py
git commit -m "scripts(task89): add provider structured-output parity smoke for Pass-1"
```

#### Task A.2: Run the smoke and record findings

- [ ] **Step 1: Joseph runs the script** (API-cost gate per [[feedback_user_fires_api_cost_runs]])

```bash
cd /home/ftu/Droidoes/Obsidian-KDB
python scripts/verify_structured_output_parity.py
```

- [ ] **Step 2: Write findings to docs**

Create `docs/task89-pass1-provider-parity-2026-05-26.md` with the table of results. For each FAIL, document the failure mode (non-JSON output, config error, exception). For each PASS, record latency + token usage.

- [ ] **Step 3: Decide Pass-1 candidate set**

Lock the Pass-1 model candidates for v1:
- Primary: `deepseek-v4-flash:direct` (matches compile-side default per `kdb_compiler/kdb_compile.py:51`)
- Backup: `gemini-3.1-flash-lite` (cost-quality frontier sibling)
- Any others passing parity

Record selection in the findings doc.

- [ ] **Step 4: Commit findings**

```bash
git add docs/task89-pass1-provider-parity-2026-05-26.md
git commit -m "docs(task89): Phase A provider parity verified — lock Pass-1 model candidates"
```

---

### Phase C — Pass-1 producer

#### Task C.1: Materialize config files

**Files:**
- Create: `kdb_compiler/config/__init__.py` (empty)
- Create: `kdb_compiler/config/domains.json`
- Create: `kdb_compiler/config/source_types.json`
- Create: `kdb_compiler/config/scope-config.yaml`

- [ ] **Step 1: Create config directory + __init__.py**

```bash
mkdir -p kdb_compiler/config
touch kdb_compiler/config/__init__.py
```

- [ ] **Step 2: Write domains.json from NW-4 v0.4**

Transcribe all 23 entries from `docs/task88-nw4-domain-list-v0.4.md` §3 (Science & Technology cluster 8 + Investing & Business 4 + Human & Society 5 + Humanities & Aesthetics 3 + Lifestyle 1 + Content-type & residual 2) into a JSON array. Each entry has 4 fields: `id`, `display`, `scope`, `aliases`. Include all aliases listed in §7 of NW-4 v0.4 ("Aliases needed for v0.4 renames" — 6 aliases).

```json
[
  {
    "id": "ai-ml",
    "display": "AI & Machine Learning",
    "scope": "LLMs, prompt engineering, RAG, models, MLOps, AI tools, knowledge graphs / GraphDB as AI harness, ontology engineering for AI/LLM systems. Technical and foundational content about how AI/ML systems work.",
    "aliases": []
  },
  ... (22 more entries)
]
```

- [ ] **Step 3: Write source_types.json from NW-7 v0.2**

Transcribe all 21 entries from `docs/task89-nw7-source-type-list-v0.2.md` §2 (Written-prose 10 + Spoken-transcribed 3 + Conversational-interactive 2 + Primary-document 3 + Vault-meta 2 + Residual 1). Each entry has 4 fields: `id`, `display`, `scope`, `aliases`. Include 2 aliases from §5 of NW-7 v0.2:
- `transcript-video` ← `transcript-youtube`
- `interview` ← `transcript-interview`

- [ ] **Step 4: Write scope-config.yaml from F2 lock**

```yaml
# kdb_compiler/config/scope-config.yaml
# Pass-1 ingestion scope configuration. Per Task #89 v0.2.1 §4.
#
# exclude_paths    — never read; circularity guards (parent #88 §3.3 reserved)
# force_signal     — read + run Pass-1 + deterministically override to signal
# force_noise      — read + run Pass-1 + deterministically override to noise
#
# Precedence: blacklist (force_noise) wins ties per D-89-3 §4.4.
# LLM never sees these lists per D-89-3 §4.5.

exclude_paths: []

force_signal: []

force_noise:
  - "Daily Notes/**"
  - "Projects/**"
```

- [ ] **Step 5: Commit config files**

```bash
git add kdb_compiler/config/
git commit -m "config(task89): materialize domains.json + source_types.json + scope-config.yaml

Transcribes NW-4 v0.4 (23 domains) and NW-7 v0.2 (21 source_types) into
runtime-loadable JSON. scope-config.yaml ships with Daily Notes + Projects
force_noise defaults per D-89-4."
```

#### Task C.2: Config loader module

**Files:**
- Create: `kdb_compiler/ingestion/__init__.py` (empty)
- Create: `kdb_compiler/ingestion/config_loader.py`
- Test: `kdb_compiler/tests/test_pass1_config_loader.py`

- [ ] **Step 1: Write the failing test**

```python
# kdb_compiler/tests/test_pass1_config_loader.py
import pytest
from kdb_compiler.ingestion.config_loader import (
    load_domains, load_source_types, load_scope_config,
    DomainEntry, SourceTypeEntry, ScopeConfig,
)


def test_load_domains_returns_23_entries():
    domains = load_domains()
    assert len(domains) == 23
    assert all(isinstance(d, DomainEntry) for d in domains)
    ids = {d.id for d in domains}
    assert "ai-ml" in ids
    assert "value-investing" in ids
    assert "undecided" in ids


def test_load_source_types_returns_21_entries():
    sts = load_source_types()
    assert len(sts) == 21
    ids = {s.id for s in sts}
    assert "blog" in ids
    assert "interview" in ids
    assert "chat-log" in ids
    assert "other" in ids


def test_source_types_aliases_resolve_for_renames():
    sts = load_source_types()
    interview = next(s for s in sts if s.id == "interview")
    assert "transcript-interview" in interview.aliases
    video = next(s for s in sts if s.id == "transcript-video")
    assert "transcript-youtube" in video.aliases


def test_scope_config_loads_defaults():
    cfg = load_scope_config()
    assert isinstance(cfg, ScopeConfig)
    assert cfg.exclude_paths == []
    assert cfg.force_signal == []
    assert "Daily Notes/**" in cfg.force_noise
    assert "Projects/**" in cfg.force_noise


def test_domain_ids_are_unique():
    domains = load_domains()
    ids = [d.id for d in domains]
    assert len(ids) == len(set(ids))


def test_source_type_ids_are_unique():
    sts = load_source_types()
    ids = [s.id for s in sts]
    assert len(ids) == len(set(ids))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest kdb_compiler/tests/test_pass1_config_loader.py -v`
Expected: FAIL with `ModuleNotFoundError: kdb_compiler.ingestion.config_loader`

- [ ] **Step 3: Write the loader**

```python
# kdb_compiler/ingestion/config_loader.py
"""Pass-1 config loader.

Reads domains.json (NW-4 v0.4 vocabulary), source_types.json (NW-7 v0.2
vocabulary), and scope-config.yaml (force_signal / force_noise path
globs). Loaded once at process start; cached for the run.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


CONFIG_DIR = Path(__file__).parent.parent / "config"


@dataclass(frozen=True)
class DomainEntry:
    id: str
    display: str
    scope: str
    aliases: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class SourceTypeEntry:
    id: str
    display: str
    scope: str
    aliases: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ScopeConfig:
    exclude_paths: tuple[str, ...]
    force_signal: tuple[str, ...]
    force_noise: tuple[str, ...]


def _load_entries(path: Path, cls):
    data: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
    return [
        cls(
            id=e["id"],
            display=e["display"],
            scope=e["scope"],
            aliases=tuple(e.get("aliases", []) or []),
        )
        for e in data
    ]


@lru_cache(maxsize=1)
def load_domains() -> list[DomainEntry]:
    return _load_entries(CONFIG_DIR / "domains.json", DomainEntry)


@lru_cache(maxsize=1)
def load_source_types() -> list[SourceTypeEntry]:
    return _load_entries(CONFIG_DIR / "source_types.json", SourceTypeEntry)


@lru_cache(maxsize=1)
def load_scope_config() -> ScopeConfig:
    data: dict = yaml.safe_load((CONFIG_DIR / "scope-config.yaml").read_text(encoding="utf-8"))
    return ScopeConfig(
        exclude_paths=tuple(data.get("exclude_paths", []) or []),
        force_signal=tuple(data.get("force_signal", []) or []),
        force_noise=tuple(data.get("force_noise", []) or []),
    )
```

- [ ] **Step 4: Run tests; expect pass**

Run: `pytest kdb_compiler/tests/test_pass1_config_loader.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add kdb_compiler/ingestion/__init__.py kdb_compiler/ingestion/config_loader.py kdb_compiler/tests/test_pass1_config_loader.py
git commit -m "feat(ingestion): config_loader for domains/source_types/scope-config"
```

#### Task C.3: Pass-1 output schema

**Files:**
- Create: `kdb_compiler/ingestion/pass1_schema.py`
- Test: `kdb_compiler/tests/test_pass1_schema.py`

- [ ] **Step 1: Write the failing test**

```python
# kdb_compiler/tests/test_pass1_schema.py
import json
import pytest
from kdb_compiler.ingestion.pass1_schema import (
    Pass1Envelope, OverrideAudit, validate_envelope, build_json_schema,
    PASS1_SCHEMA_VERSION,
)


def test_envelope_dataclass_has_graphdb_input_section():
    """All 7 GraphDB-input fields per D-89-16."""
    fields = {f.name for f in Pass1Envelope.__dataclass_fields__.values()}
    assert {"kdb_signal", "domain", "source_type", "author", "summary",
            "key_entities", "key_themes"}.issubset(fields)


def test_envelope_dataclass_has_audit_section():
    """All audit fields per D-89-16 + other_reason per OQ-NW7-7."""
    fields = {f.name for f in Pass1Envelope.__dataclass_fields__.values()}
    assert {"confidence", "uncertainty_reason", "reject_reason",
            "prompt_version", "model", "schema_version", "override",
            "other_reason"}.issubset(fields)


def test_validate_envelope_accepts_signal_envelope():
    payload = {
        "kdb_signal": "signal", "domain": "value-investing",
        "source_type": "letter", "author": "Warren Buffett",
        "summary": "Annual letter.", "key_entities": ["Berkshire"],
        "key_themes": ["intrinsic value"],
        "confidence": 0.9, "uncertainty_reason": None, "reject_reason": None,
        "prompt_version": "1.0.0", "model": "deepseek-v4-flash",
        "schema_version": 1,
        "override": {"applied": None, "rule": None, "match": None,
                     "llm_original": "signal", "reject_reason_cleared": None},
        "other_reason": None,
    }
    validate_envelope(payload)  # no raise


def test_validate_envelope_rejects_invalid_domain():
    payload = _valid_payload()
    payload["domain"] = "not-a-real-domain"
    with pytest.raises(ValueError, match="domain"):
        validate_envelope(payload)


def test_validate_envelope_rejects_invalid_source_type():
    payload = _valid_payload()
    payload["source_type"] = "podcast"  # dropped from NW-7
    with pytest.raises(ValueError, match="source_type"):
        validate_envelope(payload)


def test_validate_envelope_rejects_kdb_signal_outside_enum():
    payload = _valid_payload()
    payload["kdb_signal"] = "uncertain"  # not in enum
    with pytest.raises(ValueError, match="kdb_signal"):
        validate_envelope(payload)


def test_validate_envelope_requires_other_reason_when_other():
    payload = _valid_payload()
    payload["source_type"] = "other"
    payload["other_reason"] = None  # but other_reason is required when other
    with pytest.raises(ValueError, match="other_reason"):
        validate_envelope(payload)


def test_json_schema_is_valid_jsonschema():
    schema = build_json_schema()
    assert schema["type"] == "object"
    assert "kdb_signal" in schema["required"]
    assert "domain" in schema["required"]


def _valid_payload():
    return {
        "kdb_signal": "signal", "domain": "ai-ml",
        "source_type": "paper", "author": None,
        "summary": "Test.", "key_entities": [],
        "key_themes": [],
        "confidence": 0.8, "uncertainty_reason": None, "reject_reason": None,
        "prompt_version": "1.0.0", "model": "deepseek-v4-flash",
        "schema_version": 1,
        "override": {"applied": None, "rule": None, "match": None,
                     "llm_original": "signal", "reject_reason_cleared": None},
        "other_reason": None,
    }
```

- [ ] **Step 2: Run test; expect failure**

- [ ] **Step 3: Write the schema module**

```python
# kdb_compiler/ingestion/pass1_schema.py
"""Pass-1 output schema (D-89-16 sectionalized: GraphDB-input + Audit).

The Pass-1 LLM returns a structured JSON envelope; a deterministic
post-processor validates it against this schema, applies overrides
(overrides.py), serializes to YAML frontmatter (frontmatter_embedder.py),
and atomically writes the source. The LLM never sees the source body in
its output; never re-emits the body.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from kdb_compiler.ingestion.config_loader import load_domains, load_source_types

PASS1_SCHEMA_VERSION = 1


@dataclass
class OverrideAudit:
    """Per D-89-3 §4.6: override block is always emitted, never omitted.
    `applied: None` indicates no override fired."""
    applied: str | None  # "signal" | "noise" | None
    rule: str | None  # "force_signal" | "force_noise" | None
    match: str | None  # which glob fired
    llm_original: str  # the LLM's pre-override kdb_signal
    reject_reason_cleared: str | None  # original reject_reason if force_signal cleared it


@dataclass
class Pass1Envelope:
    # GraphDB-input section (Pass-2 consumes; D-89-17)
    kdb_signal: str  # "signal" | "noise"
    domain: str  # one of 23 NW-4 v0.4 IDs
    source_type: str  # one of 21 NW-7 v0.2 IDs
    author: str | None
    summary: str
    key_entities: list[str]
    key_themes: list[str]

    # Audit section (Pass-2 ignores; D-89-16)
    confidence: float
    uncertainty_reason: str | None
    reject_reason: str | None
    prompt_version: str
    model: str
    schema_version: int = PASS1_SCHEMA_VERSION
    override: OverrideAudit = field(default_factory=lambda: OverrideAudit(
        applied=None, rule=None, match=None, llm_original="signal",
        reject_reason_cleared=None,
    ))
    other_reason: str | None = None  # required-non-null when source_type=other (OQ-NW7-7)


def build_json_schema() -> dict[str, Any]:
    """Build the JSON Schema used by the LLM's structured-output mode.
    Enums are loaded from domains.json + source_types.json (D-NW4-4 /
    D-NW7-3 — config is the source of truth, not Python constants)."""
    domain_ids = [d.id for d in load_domains()]
    source_type_ids = [s.id for s in load_source_types()]

    return {
        "type": "object",
        "required": [
            "kdb_signal", "domain", "source_type", "author", "summary",
            "key_entities", "key_themes",
            "confidence", "uncertainty_reason", "reject_reason",
            "prompt_version", "model", "schema_version", "override",
            "other_reason",
        ],
        "properties": {
            "kdb_signal": {"enum": ["signal", "noise"]},
            "domain": {"enum": domain_ids},
            "source_type": {"enum": source_type_ids},
            "author": {"type": ["string", "null"]},
            "summary": {"type": "string"},
            "key_entities": {"type": "array", "items": {"type": "string"}},
            "key_themes": {"type": "array", "items": {"type": "string"}},
            "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "uncertainty_reason": {"type": ["string", "null"]},
            "reject_reason": {"type": ["string", "null"]},
            "prompt_version": {"type": "string"},
            "model": {"type": "string"},
            "schema_version": {"type": "integer"},
            "override": {
                "type": "object",
                "required": ["applied", "rule", "match", "llm_original", "reject_reason_cleared"],
                "properties": {
                    "applied": {"enum": ["signal", "noise", None]},
                    "rule": {"enum": ["force_signal", "force_noise", None]},
                    "match": {"type": ["string", "null"]},
                    "llm_original": {"enum": ["signal", "noise"]},
                    "reject_reason_cleared": {"type": ["string", "null"]},
                },
            },
            "other_reason": {"type": ["string", "null"]},
        },
    }


def validate_envelope(payload: dict[str, Any]) -> None:
    """Validate a parsed JSON envelope. Raises ValueError on failure.

    Uses jsonschema (already in pyproject.toml deps). Adds the OQ-NW7-7
    cross-field rule: other_reason must be non-null when source_type='other'.
    """
    import jsonschema
    schema = build_json_schema()
    try:
        jsonschema.validate(payload, schema)
    except jsonschema.ValidationError as e:
        # Bubble up with cleaner message
        path = ".".join(str(p) for p in e.absolute_path) or "<root>"
        raise ValueError(f"Pass-1 envelope invalid at {path}: {e.message}") from e

    if payload["source_type"] == "other" and not payload.get("other_reason"):
        raise ValueError(
            "Pass-1 envelope invalid at other_reason: "
            "must be non-null string when source_type='other' (OQ-NW7-7)"
        )
```

- [ ] **Step 4: Run tests; expect pass**

- [ ] **Step 5: Commit**

```bash
git add kdb_compiler/ingestion/pass1_schema.py kdb_compiler/tests/test_pass1_schema.py
git commit -m "feat(ingestion): Pass1Envelope + JSON Schema validation (D-89-16 sectionalized)"
```

#### Task C.4: Pass-1 prompt template

**Files:**
- Create: `kdb_compiler/ingestion/pass1_prompt.j2`
- Create: `kdb_compiler/ingestion/pass1_prompt.py`
- Test: `kdb_compiler/tests/test_pass1_prompt.py`

- [ ] **Step 1: Write the failing test**

```python
# kdb_compiler/tests/test_pass1_prompt.py
from kdb_compiler.ingestion.pass1_prompt import build_pass1_prompt, PASS1_PROMPT_VERSION


def test_build_pass1_prompt_includes_all_domain_ids():
    prompt = build_pass1_prompt(source_text="dummy", source_path="dummy.md")
    # All 23 domain IDs must appear in the prompt for LLM to classify
    assert "ai-ml" in prompt
    assert "value-investing" in prompt
    assert "undecided" in prompt


def test_build_pass1_prompt_includes_all_source_type_ids():
    prompt = build_pass1_prompt(source_text="dummy", source_path="dummy.md")
    assert "blog" in prompt
    assert "interview" in prompt
    assert "chat-log" in prompt
    assert "other" in prompt


def test_build_pass1_prompt_includes_source_text():
    prompt = build_pass1_prompt(source_text="my essay content", source_path="x.md")
    assert "my essay content" in prompt


def test_prompt_version_is_set():
    assert PASS1_PROMPT_VERSION  # truthy, semver-shaped
    parts = PASS1_PROMPT_VERSION.split(".")
    assert len(parts) == 3


def test_prompt_does_not_use_shape_word():
    """Per [[feedback_drop_the_word_shape]]."""
    prompt = build_pass1_prompt(source_text="x", source_path="x.md")
    assert "shape" not in prompt.lower()


def test_prompt_renders_boundary_rules_as_separate_block():
    """Per D-NW7-6: scope texts + §3 boundary rules render as sibling blocks."""
    prompt = build_pass1_prompt(source_text="x", source_path="x.md")
    # Look for a header indicating boundary rules section
    assert "boundary" in prompt.lower() or "disambiguation" in prompt.lower()


def test_prompt_does_not_mention_force_signal_or_force_noise():
    """Per D-89-3 §4.5: LLM does not see the path lists."""
    prompt = build_pass1_prompt(source_text="x", source_path="Daily Notes/2026-05-26.md")
    assert "force_signal" not in prompt
    assert "force_noise" not in prompt
```

- [ ] **Step 2: Run test; expect failure**

- [ ] **Step 3: Write the Jinja2 template**

```jinja2
{# kdb_compiler/ingestion/pass1_prompt.j2 #}
You are the Pass-1 enrichment classifier for a personal knowledge-base
pipeline. Given a source markdown document, emit a structured JSON envelope
classifying its substantive content along multiple axes.

Judge content substance only. Do not consider file location, file name, or
any non-content metadata in your judgment. If uncertain whether content is
signal or noise, bias to signal (preserve for human review).

## Output schema

Return ONLY a valid JSON object with these fields. Do not include the source
body in your output. Do not include any explanatory text outside the JSON.

### GraphDB-input section

- `kdb_signal`: "signal" or "noise". Pick "signal" if the source contains
  substantive knowledge content (idea, observation, explanation, framework,
  theory, case study, argument, analysis, novel information). Pick "noise"
  if the source is workflow/task tracking, conversational fragments, logs,
  empty content, or meta-commentary without substantive content.

- `domain`: one of the following IDs. Pick the one that best captures the
  source's primary substantive subject. If genuinely uncategorizable, pick
  `undecided` (last resort).

{% for d in domains %}
  - `{{ d.id }}` — {{ d.display }}: {{ d.scope }}
{%- endfor %}

- `source_type`: one of the following IDs. Pick the publication-form shape
  of the source. If genuinely uncategorizable, pick `other` (last resort,
  with `other_reason` filled in).

{% for s in source_types %}
  - `{{ s.id }}` — {{ s.display }}: {{ s.scope }}
{%- endfor %}

### Boundary disambiguation rules

When content sits at a domain or source_type edge, apply these rules to
choose between candidates. (These are classification rules, not
relationships.)

**Domain boundaries:**
{% for boundary in domain_boundaries %}
- {{ boundary }}
{%- endfor %}

**Source_type boundaries:**
{% for boundary in source_type_boundaries %}
- {{ boundary }}
{%- endfor %}

### Other GraphDB-input fields

- `author`: string or null. Extract the source's primary author from the
  content if attributable; null otherwise.
- `summary`: 1-3 sentences distilling the substantive content. Plain prose.
- `key_entities`: list of strings. People, companies, places, concepts
  surfaced by the source. Flat string list; the downstream compile stage
  resolves these against the live knowledge graph.
- `key_themes`: list of 2-5 strings. Finer-grained themes than `domain`
  capturing substantive sub-topics within the source.

### Audit section

- `confidence`: 0.0 to 1.0. Your confidence in the kdb_signal call.
- `uncertainty_reason`: string or null. When `confidence < 0.6` OR when
  `kdb_signal=signal` but with doubt, populate with the doubt's nature.
- `reject_reason`: string or null. When `kdb_signal=noise`, populate with
  the reason.
- `prompt_version`: "{{ prompt_version }}"
- `model`: the model name will be filled in by the deterministic layer.
  Emit "model_to_be_filled" here.
- `schema_version`: {{ schema_version }}
- `override`: emit `{"applied": null, "rule": null, "match": null,
  "llm_original": <your kdb_signal>, "reject_reason_cleared": null}`.
  The deterministic post-processor will overwrite this block if an override
  fires.
- `other_reason`: string or null. Required-non-null when `source_type=other`
  — name the specific missing publication form/shape. Null otherwise.

## Source content to classify

Path: {{ source_path }}

```
{{ source_text }}
```

Return the JSON envelope now.
```

- [ ] **Step 4: Write the Python wrapper**

```python
# kdb_compiler/ingestion/pass1_prompt.py
"""Pass-1 prompt construction (Jinja2 template rendering)."""
from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from kdb_compiler.ingestion.config_loader import load_domains, load_source_types
from kdb_compiler.ingestion.pass1_schema import PASS1_SCHEMA_VERSION

PASS1_PROMPT_VERSION = "1.0.0"

_TEMPLATE_DIR = Path(__file__).parent
_env = Environment(
    loader=FileSystemLoader(_TEMPLATE_DIR),
    autoescape=select_autoescape(disabled_extensions=("j2",)),
)


# Hardcoded boundary rule strings from NW-4 v0.4 §4 + NW-7 v0.2 §3.
# These are NOT in the config files (per D-NW7-6: scope texts in config are
# purely content-descriptive; boundary rules live in the prompt as a sibling
# block). Adjust here when boundary docs are amended.
_DOMAIN_BOUNDARIES: tuple[str, ...] = (
    "ai-ml ↑ software ↑ hardware: compute stack — AI algorithms/models → ai-ml; OS/dev tools/programming → software; chips/silicon/electronics → hardware. Content classifies at the layer it primarily operates on.",
    "neuroscience-cognition ↑ biology: brain mechanisms, cognition (above) vs cellular/genetic/evolutionary (below).",
    "psychology ↑ neuroscience-cognition: behavior/self-improvement/applied (above) vs mechanism-level empirical brain science (below).",
    "health-wellbeing ↑ biology: applied personal-health decisions (above) vs biological mechanisms without personal application (below).",
    "personal-finance ↑ value-investing: applied/situational (sector analysis, portfolio, tax) above vs investment philosophy/methods/models (below).",
    "value-investing ↔ economy-markets: investment-decision lens (what to buy/sell, valuation) vs market-mechanism lens (how markets/economies function).",
    "literature ↔ philosophy: narrative form (fiction, poetry) vs argumentative form (systematic thought).",
    "lifestyle ↔ personal-finance: experiential/personal-living (travel, hobbies, retirement activities) vs resource-management (retirement planning, tax, portfolio).",
    "lifestyle ↔ health-wellbeing: living-experiential focus vs health-focused (nutrition for longevity, fitness protocols).",
    "geopolitics ⇄ history: current/recent → geopolitics; completed historical period → history.",
    "science-technology (catch-all): use ONLY when no specific S&T domain (#1-7) fits AND you can articulate why.",
)

_SOURCE_TYPE_BOUNDARIES: tuple[str, ...] = (
    "blog ↔ post: blog = own publication (personal blog, Substack on own subdomain); post = community/forum/aggregator. When venue cannot be inferred, classify by authorial stance: self-contained piece → blog; community-participation → post.",
    "article ↔ news: article = analysis/argument/extended take; news = event reporting. Hybrid: classify by dominant mode.",
    "Transcript family: Q&A dominates → interview regardless of medium; one-direction educational delivery → transcript-lecture regardless of medium; otherwise medium-based (transcript-podcast vs transcript-video).",
    "book-chapter ↔ book-summary: chapter = verbatim book text; summary = ABOUT the book. Annotated excerpts classified by volume: verbatim majority → book-chapter; user-authored majority → book-summary.",
    "letter ↔ email: letter = curated public-facing addressed correspondence; email = informal individual/small-group.",
    "speech ↔ transcript-lecture: speech = prepared text form of address; transcript-lecture = transcribed-from-delivery.",
    "wiki ↔ article: wiki = encyclopedic register (third-person, neutral, multi-source citations); article = editorial (author voice, argument).",
    "social-thread ↔ post: social-thread = platform-native substantive authored content (multi-tweet thread, LinkedIn long-form post, substantive single-post platform essay); post = community comment or short casual share.",
    "interview ↔ meeting-notes: interview = verbatim Q&A (transcribed or text-native); meeting-notes = user-summarized.",
    "daily-note ↔ meeting-notes: daily-note = date-stamped omnibus log; meeting-notes = single-meeting dedicated artifact.",
    "documentation ↔ wiki: documentation = product/instructional reference (READMEs, runbooks, tutorials — reader does); wiki = descriptive encyclopedic entry (reader learns about).",
    "chat-log ↔ interview: chat-log = informal multi-party / human↔AI exchange (no curated questioner/subject roles); interview = curated Q&A (clear interlocutor + subject).",
)


def build_pass1_prompt(*, source_text: str, source_path: str) -> str:
    template = _env.get_template("pass1_prompt.j2")
    return template.render(
        source_text=source_text,
        source_path=source_path,
        domains=load_domains(),
        source_types=load_source_types(),
        domain_boundaries=_DOMAIN_BOUNDARIES,
        source_type_boundaries=_SOURCE_TYPE_BOUNDARIES,
        prompt_version=PASS1_PROMPT_VERSION,
        schema_version=PASS1_SCHEMA_VERSION,
    )
```

- [ ] **Step 5: Add jinja2 + pyyaml to pyproject.toml deps**

Edit `pyproject.toml`'s `dependencies` list. `jinja2>=3.0` and `pyyaml>=6.0` are likely missing — confirm and add.

- [ ] **Step 6: Run tests; expect pass**

- [ ] **Step 7: Commit**

```bash
git add kdb_compiler/ingestion/pass1_prompt.j2 kdb_compiler/ingestion/pass1_prompt.py kdb_compiler/tests/test_pass1_prompt.py pyproject.toml
git commit -m "feat(ingestion): Pass-1 prompt template (Jinja2) + boundary-rules block"
```

#### Task C.5: LLM caller module

**Files:**
- Create: `kdb_compiler/ingestion/pass1_caller.py`
- Test: (deferred to integration tests in C.11; mocking the LLM at this layer is brittle)

- [ ] **Step 1: Write the caller**

```python
# kdb_compiler/ingestion/pass1_caller.py
"""Pass-1 LLM call: fire the prompt at the configured provider/model;
parse the JSON envelope; raise on parse / schema failure.

Single retry on transient failures per Task #89 §5.1. The LLM call goes
through call_model.py; structured-output is requested via json_mode=True.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from kdb_compiler.call_model import ModelRequest, call_model, ModelResponse
from kdb_compiler.ingestion.pass1_prompt import build_pass1_prompt, PASS1_PROMPT_VERSION
from kdb_compiler.ingestion.pass1_schema import validate_envelope

log = logging.getLogger(__name__)


@dataclass
class Pass1CallResult:
    parsed: dict  # the validated envelope dict
    raw_response_text: str  # the raw LLM text response
    request_prompt: str  # the rendered prompt sent
    request_model: str
    request_provider: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    attempts: int


class Pass1CallError(Exception):
    """Pass-1 call failed after all retries."""


def call_pass1(
    *, source_text: str, source_path: str, provider: str, model: str,
    max_retries: int = 1,
) -> Pass1CallResult:
    """Fire one Pass-1 LLM call. Returns parsed + validated envelope.

    Per Task #89 §5.1: retry once on schema validation failure; on second
    failure raise Pass1CallError. Caller (enrich.py) emits enrich_failed
    lifecycle event.
    """
    prompt = build_pass1_prompt(source_text=source_text, source_path=source_path)

    last_err: Exception | None = None
    raw_text = ""
    last_resp: ModelResponse | None = None
    for attempt in range(1, max_retries + 2):  # initial + retries
        req = ModelRequest(
            provider=provider, model=model, prompt=prompt,
            json_mode=True, temperature=0.0, max_tokens=4096,
        )
        try:
            resp = call_model(req)
            last_resp = resp
            raw_text = resp.text
            parsed = json.loads(raw_text)
            # Stamp prompt_version + model into the parsed envelope
            # (LLM emits "model_to_be_filled"; we replace with the actual model id)
            parsed["prompt_version"] = PASS1_PROMPT_VERSION
            parsed["model"] = model
            validate_envelope(parsed)
            return Pass1CallResult(
                parsed=parsed,
                raw_response_text=raw_text,
                request_prompt=prompt,
                request_model=model,
                request_provider=provider,
                input_tokens=resp.input_tokens,
                output_tokens=resp.output_tokens,
                latency_ms=resp.latency_ms,
                attempts=attempt,
            )
        except (json.JSONDecodeError, ValueError) as e:
            last_err = e
            log.warning(f"Pass-1 attempt {attempt}/{max_retries+1} failed: {e}")
            continue

    raise Pass1CallError(
        f"Pass-1 call failed after {max_retries + 1} attempts: {last_err}"
    )
```

- [ ] **Step 2: Commit (test via integration test in C.11)**

```bash
git add kdb_compiler/ingestion/pass1_caller.py
git commit -m "feat(ingestion): pass1_caller — single-retry LLM call + schema validate"
```

#### Task C.6: Override layer (force_signal / force_noise)

**Files:**
- Create: `kdb_compiler/ingestion/overrides.py`
- Test: `kdb_compiler/tests/test_pass1_overrides.py`

- [ ] **Step 1: Write the failing test**

```python
# kdb_compiler/tests/test_pass1_overrides.py
from kdb_compiler.ingestion.overrides import apply_overrides


def _envelope(kdb_signal="signal", reject_reason=None):
    return {
        "kdb_signal": kdb_signal,
        "domain": "ai-ml", "source_type": "post", "author": None,
        "summary": "x", "key_entities": [], "key_themes": [],
        "confidence": 0.9, "uncertainty_reason": None,
        "reject_reason": reject_reason,
        "prompt_version": "1.0.0", "model": "x", "schema_version": 1,
        "override": {"applied": None, "rule": None, "match": None,
                     "llm_original": kdb_signal, "reject_reason_cleared": None},
        "other_reason": None,
    }


def test_no_match_emits_null_override_block():
    """Per D-89-3 §4.6 + Grok OQ-3: block always emitted; null when no override."""
    env = _envelope()
    out = apply_overrides(env, source_path="essays/buffett.md",
                          force_signal=(), force_noise=("Daily Notes/**",))
    assert out["kdb_signal"] == "signal"
    assert out["override"]["applied"] is None
    assert out["override"]["rule"] is None
    assert out["override"]["match"] is None
    assert out["override"]["llm_original"] == "signal"


def test_force_noise_match_overrides_to_noise():
    env = _envelope(kdb_signal="signal")
    out = apply_overrides(env, source_path="Daily Notes/2026-05-26.md",
                          force_signal=(), force_noise=("Daily Notes/**",))
    assert out["kdb_signal"] == "noise"
    assert out["override"]["applied"] == "noise"
    assert out["override"]["rule"] == "force_noise"
    assert out["override"]["match"] == "Daily Notes/**"
    assert out["override"]["llm_original"] == "signal"


def test_force_noise_signal_to_noise_populates_reject_reason():
    """Per §4.6 reject_reason survival rule."""
    env = _envelope(kdb_signal="signal", reject_reason=None)
    out = apply_overrides(env, source_path="Daily Notes/x.md",
                          force_signal=(), force_noise=("Daily Notes/**",))
    assert out["reject_reason"]
    assert "force_noise" in out["reject_reason"]


def test_force_signal_match_overrides_to_signal():
    env = _envelope(kdb_signal="noise", reject_reason="diary-shaped")
    out = apply_overrides(env, source_path="curated/essay.md",
                          force_signal=("curated/**",), force_noise=())
    assert out["kdb_signal"] == "signal"
    assert out["override"]["applied"] == "signal"
    assert out["override"]["rule"] == "force_signal"


def test_force_signal_noise_to_signal_clears_reject_reason():
    env = _envelope(kdb_signal="noise", reject_reason="diary-shaped")
    out = apply_overrides(env, source_path="curated/essay.md",
                          force_signal=("curated/**",), force_noise=())
    assert out["reject_reason"] is None
    assert out["override"]["reject_reason_cleared"] == "diary-shaped"


def test_blacklist_wins_ties():
    """Per D-89-3 §4.4: when both lists match, force_noise wins."""
    env = _envelope(kdb_signal="signal")
    out = apply_overrides(env, source_path="Daily Notes/x.md",
                          force_signal=("**/*.md",), force_noise=("Daily Notes/**",))
    assert out["kdb_signal"] == "noise"
    assert out["override"]["rule"] == "force_noise"
```

- [ ] **Step 2: Run; expect failure**

- [ ] **Step 3: Write the override layer**

```python
# kdb_compiler/ingestion/overrides.py
"""Post-LLM deterministic override layer (Task #89 §4).

Per D-89-3 §4.4: blacklist (force_noise) wins ties.
Per D-89-3 §4.5: LLM never sees the path lists.
Per D-89-3 §4.6 + Grok OQ-3: override block always emitted (null when no
  override fired) + reject_reason survival rule across overrides.
Per D-89-15: LLM runs on every in-scope source; this layer applies AFTER.
"""
from __future__ import annotations

import fnmatch
from pathlib import PurePosixPath
from typing import Iterable


def _match_any(source_path: str, globs: Iterable[str]) -> str | None:
    """Return the first matching glob, or None. Match against POSIX-style
    vault-relative path (forward slashes only)."""
    path = str(PurePosixPath(source_path))
    for glob in globs:
        if fnmatch.fnmatch(path, glob):
            return glob
    return None


def apply_overrides(
    envelope: dict, *, source_path: str,
    force_signal: Iterable[str], force_noise: Iterable[str],
) -> dict:
    """Apply force_signal / force_noise overrides to a parsed envelope.

    Returns a new envelope dict with override applied (mutates `override`
    sub-dict and possibly `kdb_signal` + `reject_reason`).
    """
    llm_original = envelope["kdb_signal"]

    # Blacklist wins ties: check force_noise first.
    noise_match = _match_any(source_path, force_noise)
    signal_match = _match_any(source_path, force_signal) if not noise_match else None

    if noise_match is not None:
        envelope["kdb_signal"] = "noise"
        envelope["override"] = {
            "applied": "noise",
            "rule": "force_noise",
            "match": noise_match,
            "llm_original": llm_original,
            "reject_reason_cleared": None,
        }
        # reject_reason survival: if LLM had emitted signal, synthesize a reject_reason
        if llm_original == "signal":
            envelope["reject_reason"] = (
                f"deterministic override via force_noise: {noise_match}"
            )
    elif signal_match is not None:
        envelope["kdb_signal"] = "signal"
        cleared = envelope["reject_reason"]
        envelope["override"] = {
            "applied": "signal",
            "rule": "force_signal",
            "match": signal_match,
            "llm_original": llm_original,
            "reject_reason_cleared": cleared,
        }
        # reject_reason survival: if LLM had emitted noise + reject_reason, clear it.
        if llm_original == "noise":
            envelope["reject_reason"] = None
    else:
        envelope["override"] = {
            "applied": None,
            "rule": None,
            "match": None,
            "llm_original": llm_original,
            "reject_reason_cleared": None,
        }

    return envelope
```

- [ ] **Step 4: Run tests; expect pass**

- [ ] **Step 5: Commit**

```bash
git add kdb_compiler/ingestion/overrides.py kdb_compiler/tests/test_pass1_overrides.py
git commit -m "feat(ingestion): force_signal/force_noise post-LLM override layer (§4)"
```

#### Task C.7: Frontmatter embedder

**Files:**
- Create: `kdb_compiler/ingestion/frontmatter_embedder.py`
- Test: `kdb_compiler/tests/test_pass1_frontmatter_embedder.py`

- [ ] **Step 1: Write the failing test**

```python
# kdb_compiler/tests/test_pass1_frontmatter_embedder.py
from pathlib import Path

import pytest

from kdb_compiler.ingestion.frontmatter_embedder import (
    embed_frontmatter, parse_existing_frontmatter, build_yaml_block,
)


def test_build_yaml_block_has_sectionalized_comments():
    """Per D-89-16: frontmatter has GraphDB-input + Audit section comments."""
    env = {
        "kdb_signal": "signal", "domain": "ai-ml", "source_type": "blog",
        "author": "Joseph", "summary": "test", "key_entities": ["x"],
        "key_themes": ["y"],
        "confidence": 0.9, "uncertainty_reason": None, "reject_reason": None,
        "prompt_version": "1.0.0", "model": "deepseek-v4-flash",
        "schema_version": 1,
        "override": {"applied": None, "rule": None, "match": None,
                     "llm_original": "signal", "reject_reason_cleared": None},
        "other_reason": None,
    }
    block = build_yaml_block(env)
    assert block.startswith("---\n")
    assert block.endswith("---\n")
    assert "# GraphDB-input section" in block
    assert "# Audit section" in block
    # Field order check: kdb_signal should appear before confidence
    assert block.index("kdb_signal:") < block.index("confidence:")


def test_embed_frontmatter_on_pristine_source(tmp_path):
    src = tmp_path / "essay.md"
    src.write_text("# My Essay\n\nThe body content.\n", encoding="utf-8")
    env = _make_envelope()
    embed_frontmatter(src, env)
    out = src.read_text(encoding="utf-8")
    assert out.startswith("---\n")
    assert "kdb_signal: signal" in out
    assert "# My Essay" in out
    assert "The body content." in out


def test_embed_frontmatter_preserves_body_bytes(tmp_path):
    """The body must be byte-identical to the pre-enrichment version."""
    src = tmp_path / "essay.md"
    body = "# Essay\n\nLine 1\n\nLine 2 with `code`.\n"
    src.write_text(body, encoding="utf-8")
    embed_frontmatter(src, _make_envelope())
    out = src.read_text(encoding="utf-8")
    assert body in out


def test_embed_frontmatter_atomic_via_temp(tmp_path):
    """The write goes through atomic_io: temp file rename, no partial state."""
    # We don't directly test atomicity, but we verify no .tmp files are left behind
    src = tmp_path / "essay.md"
    src.write_text("body\n", encoding="utf-8")
    embed_frontmatter(src, _make_envelope())
    leftover = list(tmp_path.glob("*.tmp"))
    assert leftover == []


def test_re_enrichment_replaces_pass1_fields(tmp_path):
    """When existing frontmatter has stale Pass-1 fields matching previous
    archive, new values replace them."""
    src = tmp_path / "essay.md"
    initial = """---
kdb_signal: noise
domain: undecided
source_type: other
author: null
summary: stale
key_entities: []
key_themes: []
confidence: 0.5
uncertainty_reason: null
reject_reason: stale
prompt_version: 1.0.0
model: old-model
schema_version: 1
override:
  applied: null
  rule: null
  match: null
  llm_original: noise
  reject_reason_cleared: null
other_reason: null
---
The body.
"""
    src.write_text(initial, encoding="utf-8")
    env = _make_envelope()
    env["domain"] = "ai-ml"  # new value
    embed_frontmatter(src, env)
    out = src.read_text(encoding="utf-8")
    assert "domain: ai-ml" in out
    assert "domain: undecided" not in out
    assert "The body." in out


def test_user_added_frontmatter_keys_preserved(tmp_path):
    """User-added non-Pass-1 frontmatter keys must be preserved verbatim."""
    src = tmp_path / "essay.md"
    initial = """---
title: My Custom Title
tags: [favorite, important]
---
The body.
"""
    src.write_text(initial, encoding="utf-8")
    embed_frontmatter(src, _make_envelope())
    out = src.read_text(encoding="utf-8")
    assert "title: My Custom Title" in out
    assert "favorite" in out


def test_parse_existing_frontmatter_handles_missing(tmp_path):
    src = tmp_path / "essay.md"
    src.write_text("Just body. No frontmatter.\n", encoding="utf-8")
    fm, body = parse_existing_frontmatter(src.read_text(encoding="utf-8"))
    assert fm == {}
    assert body == "Just body. No frontmatter.\n"


def _make_envelope():
    return {
        "kdb_signal": "signal", "domain": "ai-ml", "source_type": "blog",
        "author": "Joseph", "summary": "test", "key_entities": ["x"],
        "key_themes": ["y"],
        "confidence": 0.9, "uncertainty_reason": None, "reject_reason": None,
        "prompt_version": "1.0.0", "model": "deepseek-v4-flash",
        "schema_version": 1,
        "override": {"applied": None, "rule": None, "match": None,
                     "llm_original": "signal", "reject_reason_cleared": None},
        "other_reason": None,
    }
```

- [ ] **Step 2: Run; expect failure**

- [ ] **Step 3: Write the embedder**

```python
# kdb_compiler/ingestion/frontmatter_embedder.py
"""Deterministic YAML frontmatter embedder (Task #89 §3 + D-89-13).

The LLM returns structured JSON; this module serializes the JSON envelope
as YAML, merges with any existing user-added frontmatter keys, and writes
atomically to disk. The body content is never modified by Pass-1.

Per D-89-16 sectionalized layout: GraphDB-input section first, Audit section
second, both within the same YAML block. Comments in the YAML separate them.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

from kdb_compiler.atomic_io import atomic_write_text

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)\Z", re.DOTALL)

# Pass-1 schema fields (the keys this module owns).
_GRAPHDB_INPUT_FIELDS = (
    "kdb_signal", "domain", "source_type", "author", "summary",
    "key_entities", "key_themes",
)
_AUDIT_FIELDS = (
    "confidence", "uncertainty_reason", "reject_reason",
    "prompt_version", "model", "schema_version", "override", "other_reason",
)
_PASS1_FIELDS = frozenset(_GRAPHDB_INPUT_FIELDS + _AUDIT_FIELDS)


def parse_existing_frontmatter(text: str) -> tuple[dict, str]:
    """Split (frontmatter_dict, body_text). Returns ({}, text) if no
    frontmatter block."""
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    fm_text, body = m.group(1), m.group(2)
    try:
        fm = yaml.safe_load(fm_text) or {}
    except yaml.YAMLError:
        return {}, text
    return fm, body


def build_yaml_block(envelope: dict) -> str:
    """Build the sectionalized YAML frontmatter block (with --- delimiters
    and section comments). Pass-1 fields only; user-added keys merged
    separately by embed_frontmatter."""
    graphdb_input = {f: envelope[f] for f in _GRAPHDB_INPUT_FIELDS}
    audit = {f: envelope[f] for f in _AUDIT_FIELDS}

    gi_yaml = yaml.safe_dump(graphdb_input, sort_keys=False, allow_unicode=True,
                             default_flow_style=False)
    au_yaml = yaml.safe_dump(audit, sort_keys=False, allow_unicode=True,
                             default_flow_style=False)

    return (
        "---\n"
        "# GraphDB-input section — Pass-2 (compile) consumes (D-89-17)\n"
        f"{gi_yaml}"
        "\n"
        "# Audit section — Pass-1's own; Pass-2 ignores (D-89-16)\n"
        f"{au_yaml}"
        "---\n"
    )


def embed_frontmatter(source_path: Path, envelope: dict) -> None:
    """Embed the Pass-1 envelope as YAML frontmatter at the top of the
    source. Preserves existing user-added non-Pass-1 keys. Body byte-identical."""
    raw = source_path.read_text(encoding="utf-8")
    existing_fm, body = parse_existing_frontmatter(raw)

    # User-added keys = anything in existing_fm not in _PASS1_FIELDS
    user_keys = {k: v for k, v in existing_fm.items() if k not in _PASS1_FIELDS}

    pass1_block = build_yaml_block(envelope)

    if user_keys:
        user_yaml = yaml.safe_dump(user_keys, sort_keys=False, allow_unicode=True,
                                   default_flow_style=False)
        # Append user keys as a third sub-block within the same frontmatter
        pass1_block = (
            pass1_block.rstrip("---\n")
            + "\n# User-added keys (preserved)\n"
            + user_yaml
            + "---\n"
        )

    new_text = pass1_block + body
    atomic_write_text(source_path, new_text, encoding="utf-8")
```

- [ ] **Step 4: Confirm `atomic_io.py` provides `atomic_write_text`**

Check `kdb_compiler/atomic_io.py` for `atomic_write_text(path, text, encoding=...)`. If the function name differs, adjust the import.

- [ ] **Step 5: Run tests; expect pass**

- [ ] **Step 6: Commit**

```bash
git add kdb_compiler/ingestion/frontmatter_embedder.py kdb_compiler/tests/test_pass1_frontmatter_embedder.py
git commit -m "feat(ingestion): frontmatter_embedder — sectionalized YAML + atomic write"
```

#### Task C.8: Replay archive sidecar

**Files:**
- Create: `kdb_compiler/ingestion/replay_archive.py`
- Test: `kdb_compiler/tests/test_pass1_replay_archive.py`

- [ ] **Step 1: Write the failing test**

```python
# kdb_compiler/tests/test_pass1_replay_archive.py
import json
from pathlib import Path

from kdb_compiler.ingestion.replay_archive import (
    encode_source_id, write_sidecar, SidecarPayload,
)


def test_encode_source_id_replaces_slash_with_double_underscore():
    assert encode_source_id("Investing/Buffett-letter-2020.md") == "Investing__Buffett-letter-2020.md"
    assert encode_source_id("top-level-note.md") == "top-level-note.md"
    assert encode_source_id("a/b/c.md") == "a__b__c.md"


def test_write_sidecar_creates_json_at_expected_path(tmp_path):
    runs_root = tmp_path / "ingest_runs"
    payload = SidecarPayload(
        source_id="Notes/Quick-thoughts.md",
        source_path="/home/x/Obsidian/Notes/Quick-thoughts.md",
        source_content_hash="sha256:abc123",
        request={"prompt": "...", "model": "deepseek-v4-flash"},
        raw_response={"body": "{...}", "usage": {"in": 100, "out": 50}},
        parsed_envelope={"kdb_signal": "signal", "domain": "ai-ml"},
        override={"applied": None, "rule": None, "match": None,
                  "llm_original": "signal", "reject_reason_cleared": None},
        user_overrides_detected=[],
        timestamp="2026-05-26T20:30:00-04:00",
        outcome="enriched",
    )
    written = write_sidecar(runs_root, "ingest-2026-05-26", payload)
    expected = runs_root / "ingest-2026-05-26" / "Notes__Quick-thoughts.md.json"
    assert written == expected
    data = json.loads(written.read_text(encoding="utf-8"))
    assert data["source_id"] == "Notes/Quick-thoughts.md"
    assert data["outcome"] == "enriched"
    assert data["parsed_envelope"]["kdb_signal"] == "signal"
```

- [ ] **Step 2: Run; expect failure**

- [ ] **Step 3: Write the module**

```python
# kdb_compiler/ingestion/replay_archive.py
"""Pass-1 replay archive sidecar (Task #89 §5.3 + D-89-13).

One JSON sidecar per Pass-1 call (success or fail) at
~/Obsidian/KDB/state/ingest_runs/<run_id>/<encoded_source_id>.json.

Encoded source ID replaces `/` with `__` (Codex F-4 + Gemini F-3).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path


def encode_source_id(source_id: str) -> str:
    """Source IDs are vault-relative paths; encode `/` → `__` for flat
    sidecar lookup (per Task #89 §5.3)."""
    return source_id.replace("/", "__")


@dataclass
class SidecarPayload:
    source_id: str
    source_path: str
    source_content_hash: str
    request: dict
    raw_response: dict
    parsed_envelope: dict
    override: dict
    user_overrides_detected: list
    timestamp: str  # local ISO with offset per [[feedback_local_time_everywhere]]
    outcome: str  # "enriched" | "enriched_force_overridden" | "enrich_failed" | "enrich_skipped"


def write_sidecar(runs_root: Path, run_id: str, payload: SidecarPayload) -> Path:
    """Write the sidecar JSON. Returns the path written."""
    run_dir = runs_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    filename = encode_source_id(payload.source_id) + ".json"
    out_path = run_dir / filename
    out_path.write_text(json.dumps(asdict(payload), indent=2, ensure_ascii=False),
                        encoding="utf-8")
    return out_path
```

- [ ] **Step 4: Run; expect pass**

- [ ] **Step 5: Commit**

```bash
git add kdb_compiler/ingestion/replay_archive.py kdb_compiler/tests/test_pass1_replay_archive.py
git commit -m "feat(ingestion): replay archive sidecar with __-encoded source IDs"
```

#### Task C.9: Run journal

**Files:**
- Create: `kdb_compiler/ingestion/run_journal.py`
- Test: `kdb_compiler/tests/test_pass1_run_journal.py`

- [ ] **Step 1: Write test + implementation following Task #89 §5.4 schema**

```python
# kdb_compiler/ingestion/run_journal.py
"""Pass-1 run journal (Task #89 §5.4). Mirrors kdb_compile journal pattern."""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path


@dataclass
class IngestRunJournal:
    run_id: str
    schema_version: str = "1.0"
    event_type: str = "ingest"
    sources_processed: int = 0
    by_outcome: dict[str, int] = field(default_factory=lambda: {
        "enriched": 0, "enriched_force_overridden": 0,
        "enrich_skipped": 0, "enrich_failed": 0,
    })
    prompt_version: str = ""
    model: str = ""
    force_signal_globs: list[str] = field(default_factory=list)
    force_noise_globs: list[str] = field(default_factory=list)
    timestamp: str = ""  # local ISO with offset
    duration_seconds: float = 0.0


def write_journal(runs_root: Path, journal: IngestRunJournal) -> Path:
    run_dir = runs_root / journal.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    out_path = run_dir / "journal.json"
    out_path.write_text(json.dumps(asdict(journal), indent=2),
                        encoding="utf-8")
    return out_path
```

Test mirrors the dataclass shape; one happy-path test confirming write.

- [ ] **Step 2: Commit**

```bash
git add kdb_compiler/ingestion/run_journal.py kdb_compiler/tests/test_pass1_run_journal.py
git commit -m "feat(ingestion): Pass-1 run journal (Task #89 §5.4)"
```

#### Task C.10: enrich_one() orchestrator

**Files:**
- Create: `kdb_compiler/ingestion/enrich.py`
- Test: `kdb_compiler/tests/test_pass1_enrich.py` (uses real call_model.py call OR mocks at the call_model boundary; lean on real LLM call for integration confidence — gated by `pytest.mark.live` or env var)

- [ ] **Step 1: Write enrich_one() top-level**

```python
# kdb_compiler/ingestion/enrich.py
"""Pass-1 enrichment orchestrator. One source → enriched + audit + journal entry."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from kdb_compiler.ingestion.config_loader import load_scope_config
from kdb_compiler.ingestion.pass1_caller import call_pass1, Pass1CallError
from kdb_compiler.ingestion.overrides import apply_overrides
from kdb_compiler.ingestion.frontmatter_embedder import (
    embed_frontmatter, parse_existing_frontmatter,
)
from kdb_compiler.ingestion.replay_archive import write_sidecar, SidecarPayload


@dataclass
class EnrichResult:
    source_id: str
    outcome: str  # enriched | enriched_force_overridden | enrich_failed | enrich_skipped
    parsed_envelope: dict | None
    sidecar_path: Path | None
    error: str | None


def enrich_one(
    *, source_path: Path, source_id: str, runs_root: Path, run_id: str,
    provider: str, model: str,
) -> EnrichResult:
    scope = load_scope_config()

    raw_text = source_path.read_text(encoding="utf-8")
    existing_fm, body = parse_existing_frontmatter(raw_text)
    content_hash = "sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest()

    # Empty source short-circuit per Task #89 §5.1
    if not body.strip():
        envelope = _empty_source_envelope(model)
        sidecar = _write_sidecar_skipped(
            runs_root, run_id, source_id, source_path, content_hash, envelope
        )
        return EnrichResult(source_id, "enrich_skipped", envelope, sidecar, None)

    try:
        call_result = call_pass1(
            source_text=body, source_path=str(source_path),
            provider=provider, model=model,
        )
    except Pass1CallError as e:
        sidecar = _write_sidecar_failed(
            runs_root, run_id, source_id, source_path, content_hash, str(e), model,
        )
        return EnrichResult(source_id, "enrich_failed", None, sidecar, str(e))

    envelope = apply_overrides(
        call_result.parsed, source_path=source_id,
        force_signal=scope.force_signal, force_noise=scope.force_noise,
    )

    embed_frontmatter(source_path, envelope)

    outcome = ("enriched_force_overridden"
               if envelope["override"]["applied"] is not None
               else "enriched")
    sidecar_payload = SidecarPayload(
        source_id=source_id,
        source_path=str(source_path),
        source_content_hash=content_hash,
        request={"prompt": call_result.request_prompt,
                 "model": call_result.request_model,
                 "provider": call_result.request_provider},
        raw_response={"body": call_result.raw_response_text,
                      "input_tokens": call_result.input_tokens,
                      "output_tokens": call_result.output_tokens,
                      "latency_ms": call_result.latency_ms,
                      "attempts": call_result.attempts},
        parsed_envelope=envelope,
        override=envelope["override"],
        user_overrides_detected=[],  # OQ-89-9 / §3.3 user-collision; v1.1+ feature
        timestamp=_local_iso(),
        outcome=outcome,
    )
    sidecar = write_sidecar(runs_root, run_id, sidecar_payload)
    return EnrichResult(source_id, outcome, envelope, sidecar, None)


def _local_iso() -> str:
    """Local time with offset per [[feedback_local_time_everywhere]]."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _empty_source_envelope(model: str) -> dict:
    """Per Task #89 §5.1: empty source → kdb_signal=noise with reason."""
    return {
        "kdb_signal": "noise",
        "domain": "undecided", "source_type": "other", "author": None,
        "summary": "", "key_entities": [], "key_themes": [],
        "confidence": 1.0, "uncertainty_reason": None,
        "reject_reason": "empty source",
        "prompt_version": "1.0.0", "model": model, "schema_version": 1,
        "override": {"applied": None, "rule": None, "match": None,
                     "llm_original": "noise", "reject_reason_cleared": None},
        "other_reason": "empty source — no content shape to classify",
    }


def _write_sidecar_skipped(runs_root, run_id, source_id, source_path,
                            content_hash, envelope):
    payload = SidecarPayload(
        source_id=source_id, source_path=str(source_path),
        source_content_hash=content_hash,
        request={"prompt": "<skipped — empty source>", "model": envelope["model"]},
        raw_response={"body": "", "input_tokens": 0, "output_tokens": 0,
                      "latency_ms": 0, "attempts": 0},
        parsed_envelope=envelope,
        override=envelope["override"],
        user_overrides_detected=[],
        timestamp=_local_iso(),
        outcome="enrich_skipped",
    )
    return write_sidecar(runs_root, run_id, payload)


def _write_sidecar_failed(runs_root, run_id, source_id, source_path,
                           content_hash, error_msg, model):
    payload = SidecarPayload(
        source_id=source_id, source_path=str(source_path),
        source_content_hash=content_hash,
        request={"prompt": "<see error>", "model": model},
        raw_response={"body": "", "error": error_msg},
        parsed_envelope=None,
        override={"applied": None, "rule": None, "match": None,
                  "llm_original": "?", "reject_reason_cleared": None},
        user_overrides_detected=[],
        timestamp=_local_iso(),
        outcome="enrich_failed",
    )
    return write_sidecar(runs_root, run_id, payload)
```

- [ ] **Step 2: Integration test (live LLM optional)**

Mark with `@pytest.mark.live` to make it opt-in:

```python
# kdb_compiler/tests/test_pass1_enrich.py
import os
import pytest
from pathlib import Path

from kdb_compiler.ingestion.enrich import enrich_one


@pytest.mark.live
@pytest.mark.skipif(not os.getenv("DEEPSEEK_API_KEY"),
                     reason="No DEEPSEEK_API_KEY in env")
def test_enrich_one_smoke(tmp_path):
    src = tmp_path / "sample.md"
    src.write_text(
        "# On Margin of Safety\n\n"
        "Warren Buffett's investment philosophy centers on margin of safety:\n"
        "buying at a substantial discount to intrinsic value.\n",
        encoding="utf-8",
    )
    runs_root = tmp_path / "ingest_runs"
    result = enrich_one(
        source_path=src, source_id="sample.md",
        runs_root=runs_root, run_id="test-run",
        provider="deepseek", model="deepseek-v4-flash",
    )
    assert result.outcome == "enriched"
    out_text = src.read_text(encoding="utf-8")
    assert out_text.startswith("---\n")
    assert "kdb_signal:" in out_text
    assert result.sidecar_path.exists()


def test_enrich_one_empty_source_skipped(tmp_path):
    src = tmp_path / "empty.md"
    src.write_text("", encoding="utf-8")
    runs_root = tmp_path / "ingest_runs"
    result = enrich_one(
        source_path=src, source_id="empty.md",
        runs_root=runs_root, run_id="test-run",
        provider="deepseek", model="deepseek-v4-flash",
    )
    assert result.outcome == "enrich_skipped"
    assert result.parsed_envelope["kdb_signal"] == "noise"
```

Add `live` marker to `pyproject.toml`'s `[tool.pytest.ini_options].markers` if not present (existing pattern from #81's `bench` marker).

- [ ] **Step 3: Commit**

```bash
git add kdb_compiler/ingestion/enrich.py kdb_compiler/tests/test_pass1_enrich.py pyproject.toml
git commit -m "feat(ingestion): enrich_one() orchestrator + live smoke test"
```

#### Task C.11: kdb-enrich CLI entry point

**Files:**
- Create: `kdb_compiler/ingestion/kdb_enrich.py`
- Modify: `pyproject.toml` (add entry point)

- [ ] **Step 1: Write the CLI**

```python
# kdb_compiler/ingestion/kdb_enrich.py
"""kdb-enrich — fire Pass-1 enrichment on one or more sources.

Usage:
    kdb-enrich <source.md> [<source.md> ...] [--provider deepseek] [--model deepseek-v4-flash]
    kdb-enrich --vault ~/Obsidian --include 'essays/**' [--provider ...] [--model ...]
    kdb-enrich --dry-run <source.md>     # show what would be enriched; no write
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

from kdb_compiler.ingestion.enrich import enrich_one
from kdb_compiler.ingestion.run_journal import IngestRunJournal, write_journal
from kdb_compiler.ingestion.config_loader import load_scope_config


DEFAULT_PROVIDER = "deepseek"
DEFAULT_MODEL = "deepseek-v4-flash"


def main():
    parser = argparse.ArgumentParser(prog="kdb-enrich")
    parser.add_argument("sources", nargs="*", type=Path,
                        help="Specific source files to enrich.")
    parser.add_argument("--vault", type=Path, default=None,
                        help="Vault root for --include glob mode.")
    parser.add_argument("--include", type=str, action="append", default=[],
                        help="Glob pattern relative to --vault.")
    parser.add_argument("--provider", default=DEFAULT_PROVIDER)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--runs-root", type=Path,
                        default=Path.home() / "Obsidian/KDB/state/ingest_runs")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    # Resolve source files
    sources = _resolve_sources(args)
    if not sources:
        print("No sources to enrich.", file=sys.stderr)
        sys.exit(1)

    run_id = f"ingest-{datetime.now().astimezone().strftime('%Y-%m-%dT%H-%M-%S')}"
    scope = load_scope_config()
    journal = IngestRunJournal(
        run_id=run_id,
        prompt_version="1.0.0",
        model=args.model,
        force_signal_globs=list(scope.force_signal),
        force_noise_globs=list(scope.force_noise),
        timestamp=datetime.now().astimezone().isoformat(timespec="seconds"),
    )

    if args.dry_run:
        print(f"[DRY-RUN] would enrich {len(sources)} sources with run_id={run_id}")
        for s in sources:
            print(f"  {s}")
        return

    t0 = time.monotonic()
    for source_path, source_id in sources:
        result = enrich_one(
            source_path=source_path, source_id=source_id,
            runs_root=args.runs_root, run_id=run_id,
            provider=args.provider, model=args.model,
        )
        print(f"  {result.outcome:30s}  {source_id}")
        journal.sources_processed += 1
        journal.by_outcome[result.outcome] += 1
    journal.duration_seconds = round(time.monotonic() - t0, 2)
    journal_path = write_journal(args.runs_root, journal)
    print(f"\nrun_id={run_id}")
    print(f"journal={journal_path}")
    print(f"sources_processed={journal.sources_processed}")
    print(f"by_outcome={journal.by_outcome}")


def _resolve_sources(args) -> list[tuple[Path, str]]:
    """Returns list of (absolute_path, vault_relative_id) pairs."""
    out: list[tuple[Path, str]] = []
    if args.sources:
        for s in args.sources:
            out.append((s.resolve(), s.name))
    if args.vault and args.include:
        for pattern in args.include:
            for p in args.vault.glob(pattern):
                if p.suffix == ".md":
                    rel = str(p.relative_to(args.vault))
                    out.append((p.resolve(), rel))
    return out


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Add CLI entry point to pyproject.toml**

In `[project.scripts]` block, add:
```toml
kdb-enrich           = "kdb_compiler.ingestion.kdb_enrich:main"
```

- [ ] **Step 3: Reinstall editable to pick up entry point**

```bash
pip install -e .
```

- [ ] **Step 4: Smoke test the CLI**

```bash
echo "# Test\n\nMargin of safety in value investing." > /tmp/smoke.md
kdb-enrich /tmp/smoke.md --dry-run
```

Expected: `[DRY-RUN] would enrich 1 sources with run_id=ingest-...`

- [ ] **Step 5: Commit**

```bash
git add kdb_compiler/ingestion/kdb_enrich.py pyproject.toml
git commit -m "feat(ingestion): kdb-enrich CLI entry point + dry-run mode"
```

---

### Phase B — GraphDB schema migration v2.2 → v2.3

#### Task B.1: Schema delta + migration

**Files:**
- Modify: `graphdb_kdb/schema.py` (add columns + _migrate_2_2_to_2_3)
- Modify: `graphdb_kdb/tests/test_schema_migration.py` (add v2.2 → v2.3 tests)

- [ ] **Step 1: Write the failing test**

```python
# graphdb_kdb/tests/test_schema_migration.py (extend existing file)
def test_migrate_2_2_to_2_3_adds_source_columns(empty_db):
    """Per Task #89 D-89-17: Source schema gains summary, author, domain."""
    conn = empty_db.conn
    # Set up schema at v2.2
    from graphdb_kdb.schema import _ensure_schema_at_version
    _ensure_schema_at_version(conn, "2.2")

    # Apply migration
    from graphdb_kdb.schema import _migrate_2_2_to_2_3
    _migrate_2_2_to_2_3(conn)

    # Verify columns exist
    result = conn.execute("CALL SHOW_TABLES() RETURN *")
    # Verify each column via PRAGMA / CALL TABLE_INFO equivalent
    info = conn.execute("CALL TABLE_INFO('Source') RETURN *").get_as_df()
    cols = set(info["name"])
    assert "summary" in cols
    assert "author" in cols
    assert "domain" in cols


def test_full_migration_chain_walks_to_2_3(empty_db):
    """Schema starts at v1.0; full _ensure_schema walks to current (2.3)."""
    from graphdb_kdb.schema import ensure_schema, SCHEMA_VERSION
    assert SCHEMA_VERSION == "2.3"
    ensure_schema(empty_db.conn)
    info = empty_db.conn.execute("CALL TABLE_INFO('Source') RETURN *").get_as_df()
    cols = set(info["name"])
    assert {"summary", "author", "domain"}.issubset(cols)
```

- [ ] **Step 2: Run; expect failure**

- [ ] **Step 3: Write the migration**

In `graphdb_kdb/schema.py`:

```python
SCHEMA_VERSION = "2.3"  # bumped from 2.2


def _migrate_2_2_to_2_3(conn) -> None:
    """Add Source.summary, Source.author, Source.domain columns (Task #89 D-89-17).
    
    Pass-1 enrichment now populates these directly via frontmatter; compile's
    Source-node writer reads them from the parsed frontmatter (no LLM re-derivation).
    Existing Source rows get NULL until next compile run."""
    conn.execute("ALTER TABLE Source ADD summary STRING")
    conn.execute("ALTER TABLE Source ADD author STRING")
    conn.execute("ALTER TABLE Source ADD domain STRING")


# Extend MIGRATIONS dict:
MIGRATIONS = {
    ("1.0", "2.0"): _migrate_1_0_to_2_0,
    ("2.0", "2.1"): _migrate_2_0_to_2_1,
    ("2.1", "2.2"): _migrate_2_1_to_2_2,
    ("2.2", "2.3"): _migrate_2_2_to_2_3,
}
```

Also bump base table definition (so fresh DBs start at v2.3 with the columns):
```python
# In _create_source_table() or equivalent
"""
CREATE NODE TABLE Source (
    slug STRING,
    source_type STRING,
    ...,
    summary STRING,  -- new in 2.3
    author STRING,   -- new in 2.3
    domain STRING,   -- new in 2.3
    PRIMARY KEY (slug)
)
"""
```

- [ ] **Step 4: Run; expect pass**

- [ ] **Step 5: Verifier + snapshot coverage** (per #79 / #80 precedent)

Schema additions need verifier coverage (replay vs live diff catches drift) AND snapshot coverage (Source.summary/author/domain must survive snapshot+restore cycles). Add tests + code per `graphdb_kdb/verifier.py` + `graphdb_kdb/snapshot.py` patterns. SNAPSHOT_FORMAT_VERSION bump 3 → 4 (purely additive — Source.jsonl columns expanded).

- [ ] **Step 6: Commit**

```bash
git add graphdb_kdb/schema.py graphdb_kdb/snapshot.py graphdb_kdb/verifier.py graphdb_kdb/tests/test_schema_migration.py graphdb_kdb/tests/test_snapshot.py graphdb_kdb/tests/test_verifier.py
git commit -m "feat(schema): v2.2 → v2.3 Source.summary/author/domain (Task #89 D-89-17)

Adds three string columns to Source node table + chained migration. Verifier
gains shared-keys diff coverage; snapshot format bumped 3→4 (purely additive)."
```

---

### Phase D — Compile-side integration (D-89-17 / D-89-18)

#### Task D.1: source_text_for() rewrite

**Files:**
- Modify: `kdb_compiler/compiler.py` (lines 104-107 + ripple callers)
- Add tests: `kdb_compiler/tests/test_compiler.py` (extend)

- [ ] **Step 1: Write the failing test**

```python
# Extend kdb_compiler/tests/test_compiler.py
from kdb_compiler.compiler import source_text_for, SourceFrontmatter

def test_source_text_for_returns_tuple_with_frontmatter(tmp_path):
    """Per D-89-17 + §10.5: source_text_for splits frontmatter from body."""
    src = tmp_path / "essay.md"
    src.write_text(
        "---\n"
        "kdb_signal: signal\n"
        "domain: ai-ml\n"
        "source_type: blog\n"
        "author: Joseph\n"
        "summary: Test.\n"
        "key_entities: [x]\n"
        "key_themes: [y]\n"
        "confidence: 0.9\n"
        "uncertainty_reason: null\n"
        "reject_reason: null\n"
        "prompt_version: 1.0.0\n"
        "model: deepseek\n"
        "schema_version: 1\n"
        "override:\n"
        "  applied: null\n"
        "  rule: null\n"
        "  match: null\n"
        "  llm_original: signal\n"
        "  reject_reason_cleared: null\n"
        "other_reason: null\n"
        "---\n"
        "The body content here.\n",
        encoding="utf-8",
    )
    job = _make_compile_job(src)
    fm, body = source_text_for(job)
    assert isinstance(fm, SourceFrontmatter)
    assert fm.domain == "ai-ml"
    assert fm.source_type == "blog"
    assert fm.author == "Joseph"
    assert fm.summary == "Test."
    assert fm.key_entities == ["x"]
    assert fm.key_themes == ["y"]
    assert "The body content here." in body
    assert "kdb_signal" not in body  # frontmatter stripped from body


def test_source_text_for_handles_pristine_source(tmp_path):
    """A source without frontmatter (pre-Pass-1) still works."""
    src = tmp_path / "essay.md"
    src.write_text("# Essay\n\nBody only.\n", encoding="utf-8")
    job = _make_compile_job(src)
    fm, body = source_text_for(job)
    assert fm is None or fm.is_empty()
    assert "# Essay" in body
```

- [ ] **Step 2: Rewrite source_text_for()**

```python
# kdb_compiler/compiler.py — replace lines 104-107
from dataclasses import dataclass
from kdb_compiler.ingestion.frontmatter_embedder import parse_existing_frontmatter


@dataclass
class SourceFrontmatter:
    """Parsed GraphDB-input section of Pass-1 frontmatter. Audit section + user-added
    keys are ignored by compile per D-89-16."""
    kdb_signal: str
    domain: str
    source_type: str
    author: str | None
    summary: str
    key_entities: list[str]
    key_themes: list[str]

    @classmethod
    def from_dict(cls, fm: dict) -> "SourceFrontmatter | None":
        """Return None if frontmatter does not contain Pass-1 GraphDB-input keys."""
        required = {"kdb_signal", "domain", "source_type", "summary"}
        if not required.issubset(fm.keys()):
            return None
        return cls(
            kdb_signal=fm["kdb_signal"],
            domain=fm["domain"],
            source_type=fm["source_type"],
            author=fm.get("author"),
            summary=fm["summary"],
            key_entities=fm.get("key_entities", []) or [],
            key_themes=fm.get("key_themes", []) or [],
        )


def source_text_for(job: "CompileJob") -> tuple[SourceFrontmatter | None, str]:
    """Read job.abs_path as UTF-8; split frontmatter from body.

    Returns (frontmatter, body) where:
    - frontmatter is a SourceFrontmatter dataclass if the file has a Pass-1
      enriched frontmatter block (GraphDB-input section present); None otherwise.
    - body is the body text without the frontmatter YAML block.

    The compile LLM receives only `body`. The Source-node writer + entity
    extractor seed reads `frontmatter` (D-89-17).

    Propagates OSError / UnicodeDecodeError so compile_one's scaffold-and-fill
    can classify the failure.
    """
    raw = Path(job.abs_path).read_text(encoding="utf-8")
    fm_dict, body = parse_existing_frontmatter(raw)
    fm = SourceFrontmatter.from_dict(fm_dict)
    return fm, body
```

- [ ] **Step 3: Update ALL callers** of `source_text_for()` in the codebase

Grep first:
```bash
grep -rn "source_text_for" kdb_compiler/ --include="*.py"
```

Each caller needs to unpack the tuple. Most use the body text only; just update the call sites to `_, body = source_text_for(job)` if they don't need frontmatter, or `fm, body = source_text_for(job)` if they do.

- [ ] **Step 4: Run full test suite**

```bash
pytest kdb_compiler/tests/ -v
```

Expected: all existing tests still pass (or have been updated to match new signature) + new tests pass.

- [ ] **Step 5: Commit**

```bash
git add kdb_compiler/compiler.py kdb_compiler/tests/test_compiler.py <ripple-affected-files>
git commit -m "feat(compile): source_text_for returns (frontmatter, body) tuple (D-89-17)

SourceFrontmatter dataclass captures the Pass-1 GraphDB-input section (audit
section + user-added keys ignored per D-89-16). Compile LLM receives body only;
Source-node writer + entity extractor will consume frontmatter in subsequent
tasks."
```

#### Task D.2: Source-node writer uses frontmatter

**Files:**
- Modify: `graphdb_kdb/ingestor.py` — `_ingest_source()` or equivalent populates Source.summary/author/domain from `frontmatter` parameter
- Modify: callers in compile to pass frontmatter through

- [ ] **Step 1: Write the failing test (in graphdb_kdb/tests/)**

Test: ingestor writes Source.summary/author/domain populated from a payload that includes those fields. Verify via graph query post-ingest.

- [ ] **Step 2: Update ingestor.py to accept + write these columns**

- [ ] **Step 3: Update producer_contract.md and graphdb-kdb-producer-contract.md** to document the new Source columns + their source (Pass-1 frontmatter)

- [ ] **Step 4: Commit**

```bash
git add graphdb_kdb/ingestor.py graphdb_kdb/tests/ docs/graphdb-kdb-producer-contract.md
git commit -m "feat(graphdb): Source-node writer populates summary/author/domain from Pass-1 frontmatter"
```

#### Task D.3: Compile prompt template amendments

**Files:**
- Modify: `kdb_compiler/prompt_builder.py` (and `.j2` template if used)
- Tests: `kdb_compiler/tests/test_prompt_builder.py`

- [ ] **Step 1: Write tests**

Tests assert the compile prompt instructs the LLM to:
- USE `frontmatter.domain` / `source_type` / `author` (do NOT re-derive)
- MERGE `frontmatter.summary + frontmatter.key_themes` into final Source.summary (D-89-18)
- TREAT `frontmatter.key_entities` as seed candidates for entity extraction (verify, dedupe, supplement)

- [ ] **Step 2: Update prompt_builder + template per D-89-17/D-89-18**

- [ ] **Step 3: Test + commit**

```bash
git add kdb_compiler/prompt_builder.py kdb_compiler/tests/test_prompt_builder.py <template-files>
git commit -m "feat(compile): prompt amendments to consume Pass-1 frontmatter (D-89-17/D-89-18)"
```

---

### Phase E — End-to-end acceptance

#### Task E.1: Full Pass-1 → compile flow acceptance test

**Files:**
- Create: `kdb_compiler/tests/test_pass1_end_to_end.py`

- [ ] **Step 1: Write the acceptance test**

Marked `@pytest.mark.live` since it needs a real LLM call.

```python
# kdb_compiler/tests/test_pass1_end_to_end.py
import os
import pytest
from pathlib import Path

from kdb_compiler.ingestion.enrich import enrich_one
# ... compile pipeline imports ...


@pytest.mark.live
@pytest.mark.skipif(not os.getenv("DEEPSEEK_API_KEY"),
                     reason="No DEEPSEEK_API_KEY in env")
def test_tunnel_ends_meet(tmp_path, isolated_vault, fresh_graphdb):
    """Per Task #89 §10.5 acceptance criteria — the 'tunnel ends meet'
    integration check. Run Pass-1 on a pristine source, then run compile,
    then assert:

    1. Source.domain / author / summary / source_type populated from frontmatter
       (no LLM re-derivation by compile).
    2. key_entities from frontmatter appear as seeded Entity nodes + SUPPORTS edges
       (compile may add more from body discovery; minimum check is frontmatter seeds present).
    3. Compile LLM does NOT emit entities for metadata values
       (e.g., 'Warren Buffett' from frontmatter.author should not appear as
       a body-discovered entity; it's seeded from frontmatter).
    4. Audit section does not influence Source node properties
       (Source has no `confidence` column; audit fields are dropped on read).
    5. Source.summary is a merged prose integrating Pass-1 summary + key_themes,
       NOT a verbatim copy (D-89-18).
    """
    # Setup
    src = isolated_vault / "raw/buffett-essay.md"
    src.write_text(
        "# Buffett on Margin of Safety\n\n"
        "Warren Buffett emphasizes buying at substantial discount to intrinsic value.\n"
        "Berkshire Hathaway has applied this principle for decades, citing examples like\n"
        "See's Candies and Coca-Cola as illustrations of compounding capital.\n",
        encoding="utf-8",
    )

    # Pass-1
    result = enrich_one(
        source_path=src, source_id="raw/buffett-essay.md",
        runs_root=isolated_vault / "state/ingest_runs", run_id="e2e-test",
        provider="deepseek", model="deepseek-v4-flash",
    )
    assert result.outcome in ("enriched", "enriched_force_overridden")

    # Verify Pass-1 wrote frontmatter
    enriched_text = src.read_text(encoding="utf-8")
    assert enriched_text.startswith("---\n")
    assert "kdb_signal: signal" in enriched_text or "kdb_signal: noise" in enriched_text
    assert "# Buffett on Margin of Safety" in enriched_text  # body preserved

    # Compile
    # ... run compile pipeline on isolated_vault ...

    # Assert 1: Source columns populated from frontmatter
    source_row = fresh_graphdb.conn.execute(
        "MATCH (s:Source {slug: 'raw/buffett-essay'}) RETURN s.*"
    ).get_as_df().iloc[0]
    assert source_row["domain"] in [d.id for d in load_domains()]
    assert source_row["source_type"] in [s.id for s in load_source_types()]
    assert source_row["summary"]  # populated
    assert source_row["summary"] != result.parsed_envelope["summary"]  # MERGED, not verbatim

    # Assert 2: key_entities seeded as Entity + SUPPORTS
    key_entities = result.parsed_envelope["key_entities"]
    for entity in key_entities:
        # ... verify Entity node exists for each ...
        pass

    # Assert 3: audit fields not on Source
    assert "confidence" not in source_row.index
    assert "prompt_version" not in source_row.index

    # Assert 4 + 5 covered by inspection of source_row["summary"] above
```

- [ ] **Step 2: Joseph runs the acceptance test**

```bash
DEEPSEEK_API_KEY=... pytest kdb_compiler/tests/test_pass1_end_to_end.py -v -m live
```

- [ ] **Step 3: Inspect any failures + fix**

- [ ] **Step 4: Commit**

```bash
git add kdb_compiler/tests/test_pass1_end_to_end.py
git commit -m "test(task89): end-to-end acceptance — tunnel ends meet (§10.5)"
```

#### Task E.2: Milestone Changelog entry + Pass-1 v1 declared

- [ ] **Step 1: Append a one-line dated entry to `docs/CODEBASE_OVERVIEW.md` Milestone Changelog**

Per [[feedback_milestone_closure_rule]]: when a multi-iteration architectural objective closes, add a dated entry in the same commit.

The entry records: Pass-1 producer shipped + compile-side integration shipped + GraphDB schema v2.3 + tunnel ends meet (acceptance test passes).

- [ ] **Step 2: Update TASKS.md #89 status from in-progress to closed (with summary)**

- [ ] **Step 3: Commit**

```bash
git add docs/CODEBASE_OVERVIEW.md docs/TASKS.md
git commit -m "docs(task89): Pass-1 producer + compile integration shipped — Milestone Changelog"
```

---

## §3 — Out-of-scope for this plan (deferred)

These were identified during design but DEFERRED per blueprint scoping:

- **NW-5 (Pass-1 predeclared eval criteria + benchmark)** — separate work item; follows Task #75/#87 pattern. Filed as own task post-this-plan.
- **NW-6 (Pass-2 benchmark enhancement)** — separate work item.
- **Component #2 (Source Storage)** — separate Task #88 sub-task.
- **Component #3 (Trigger / lifecycle event detection)** — separate Task #88 sub-task.
- **Component #6 (Orchestrator v1 minimal script)** — separate Task #88 sub-task.
- **OQ-89-2 (Pristine-source recovery utility)** — v1.1+ candidate.
- **OQ-89-9 (User-frontmatter collision detection mechanism)** — v1.1+ feature; this plan ships `user_overrides_detected: []` placeholder.
- **OQ-89-10 (Pre-LLM short-circuit for `force_noise` matches)** — v1.1+ telemetry-gated.
- **OQ-89-11 (Corpus-aware wikilink suggestions enhancement)** — v1.1+ telemetry-gated; this plan ships D-89-12 Option B.
- **OQ-89-14 (Round-1 property additions deliberation)** — v0.3 of blueprint; not this plan.
- **OQ-89-15 (NW-8 Theme node design)** — v0.3+ deliberation.
- **OQ-NW7-6/8/9/10** — Component #1 implementation details (NW-7 v0.2 §6) or telemetry-deferred.

---

## §4 — Self-review checklist

Run before declaring plan complete:

**Spec coverage** — Walk Task #89 v0.2.1 §§ 2-10 + NW-7 v0.2 §§ 1-5. Each requirement maps to a task?
- §2 Pass-1 output schema → Task C.3 ✓
- §3 Source modification mechanism → Tasks C.7 + C.10 ✓
- §4 Override layer → Task C.6 ✓
- §5 Post-LLM flow + replay + journal → Tasks C.8 + C.9 + C.10 ✓
- §6 Wikilinks (Option B = no Pass-1 wikilinks) → enforced by absence (no wikilink module) ✓
- §7 Model selection → Task A.1-A.3 + DEFAULT_MODEL in C.11 ✓
- §8 NW-1 substance criteria → in Task C.4 prompt template ✓
- §9 NW-7 vocab → Task C.1 + C.4 (prompt) ✓
- §10 Producer contract alignment + compile consumption → Tasks D.1 + D.2 + D.3 ✓
- §11 NW-5 eval criteria → out-of-scope per §3 above ✓

**Placeholder scan** — All "fill in", "TBD", "implement later" eliminated? Code blocks complete?

**Type consistency** — `Pass1Envelope` field names match between C.3 schema + C.10 enrich.py usage + frontmatter_embedder.py field lists?

**File paths exact** — Every `Files:` block lists absolute paths consistent with §1 file structure map?

---

**END OF PLAN**

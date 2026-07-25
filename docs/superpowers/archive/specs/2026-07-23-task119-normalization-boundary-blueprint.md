# Task #119 Blueprint v0.4 — Pass-2 normalization boundary (proposal → canonical)

**Date:** 2026-07-23 (v0.1) · revised 2026-07-23 (v0.2, v0.3, v0.4) · **Author:** Kimi (for Joseph + Codex blueprint review)
**Status:** **v0.4 RATIFIED by Joseph 2026-07-23 (explicit re-ratification — supersedes the v0.3 Proceed gate).** Codex R6/R7 absorbed in v0.2/v0.3 (§13/§14); Codex R8 (REVISE BEFORE RE-RATIFICATION) absorbed — `NormalizationOp` contract + PLAN→APPLY→VERIFY pinned in §3.3, unreachable reject classes removed, telemetry contradictions resolved (§15); Codex R9 **GO FOR EXPLICIT RE-RATIFICATION** (§16). Implementation proceeds per §9/§10 and the companion plan `docs/superpowers/archive/plans/2026-07-23-task119-normalization-boundary.md`.
**Ratified architecture:** D-119 (`docs/CODEBASE_OVERVIEW.md` decision register) = **Option 2 + form (b) + no links-to-current-summary + fail-closed alias handling**, per options doc v1.3 `…/2026-07-23-task119-normalization-boundary-architecture-options.md` (Codex R1–R5 absorbed; R5 GO) and seed v1.2 `…/2026-07-22-task119-phase5-summary-slug-failure-analysis.md`.
**Code anchor:** `f8c9ad8` (current `main` `4d60e6d` is docs-only ahead of it).
**Governing rule (ratified principle):** reject ambiguity, not harmless representational differences — normalize only by deterministic authority (role / provenance / registry / context; never string similarity); reject on no interpretation, multiple plausible interpretations, collision, or information loss.

---

## 1. What is being built (one paragraph)

A **proposal → canonical boundary** inside Pass-2. The prompt-facing contract becomes a new **proposal schema** (discriminated: summary pages carry no `slug` — and tolerate a stray one, ignored with telemetry; concept/article pages require `slug`). After carrier recovery, the parsed proposal is validated for **structural sufficiency** (any proposal-schema violation), then crosses a **typed bridge** that performs deterministic normalization — concept/article slug-form coercion (the #106 machinery, refactored typed + pure), summary-identity stamping (Python-derived, role + `source_id` authority) — and enforces the **semantic reject classes**. The bridge's output must pass the **unchanged canonical validation shape**, the exact summary invariant, and a **conservation invariant** before flowing into the existing downstream (`CompiledSource` build → aggregate gate → canonicalize → post-canon invariant → page_writer → intake → manifest — all unchanged, and **alias-ledger resolution stays exclusively in canonicalize**). The raw parsed proposal is preserved separately for telemetry. The summary slug's raw value — absent, malformed, non-string, or deviating — ceases to exist as a failure cause: **never rejects, never retries.**

## 2. Per-field ownership audit (seed §5 item 4 — the contract-wide classification)

| Field | Owner | Harmless variation (evidence) | Authority | Gate classification | Telemetry |
|---|---|---|---|---|---|
| summary `slug` | **Python** (field not requested; a stray emission is **tolerated, dropped, telemetered** — R6 F1) | n/a — model never asked | role + `source_id` derivation | **never a failure cause, in any form** | `summary_identity_derived`; `summary_slug_ignored` (bounded raw capture, §3.3) when a stray is dropped |
| concept/article `slug` | model | form deviations (case, repeats, punctuation runs — #106 evidence) | mechanical form rule (`collapse_slug`) + response-local collision registry | representational → **normalize** (uncoercible/collision → reject, retriable) | per-decision record (located) |
| `page_type` | model | none observed | enum registry | structural (schema) → retriable reject | schema errors (existing) |
| `title` | model (content) | never | — | structural only (non-empty, ≤200) | — |
| `body` prose | model (content) | never | — | structural only (non-empty) | — |
| body wikilink **targets** | model (references) | form deviations propagate **only** when the token exactly names a response page whose slug was coerced; alias-ledger resolution is **not** a bridge authority (stays in canonicalize — R6 F3) | intra-response page set / role | preserve without authority (nonfatal); rewrite only via the page-slug map; **rewrite-ambiguity → reject (retriable)** | per-decision record (located) |
| `compilation_notes` | model (prose) | none needed | — | structural only (shape) | — |
| `source_id`, `supports_page_existence`, `status` | Python (runner-injected, post-bridge) | n/a | n/a | canonical-side only | — |

**Rejection-gate classification (every current gate, per seed item 4):**
- pre-call underivable stem → **fail-closed, non-retriable** (unchanged).
- recovery failure (no complete document) → **fail-closed, retriable** unless truncation (unchanged, #114).
- proposal-schema violation → **structural insufficiency, retriable** (new home for what the strict schema used to catch — minus the summary-slug exactness it never expressed).
- summary count ≠ 1, model-authored collisions, uncoercible slug → **semantic rejects, retriable**.
- canonical-shape failure, summary-invariant failure, conservation-invariant failure, bridge internal invariant failure → **Python-facing, fail-closed, NON-retriable** (system bug class).
- canonicalize / post-canon invariant / alias-ledger ops on summary identity → **fail-closed** (unchanged; ledger untouched by the bridge).

## 3. Data contracts

### 3.1 Proposal schema (NEW — prompt-facing)

`compiler/schemas/proposal_response.schema.json` (draft 2020-12). Shape:

- Root: object, `additionalProperties: false`, required `["pages"]`; optional `compilation_notes: string[]`.
- `pages`: array, `minItems: 1`; items = discriminated page proposal:
  - common required: `page_type` (enum `summary|concept|article`), `title` (1–200), `body` (non-empty string); `additionalProperties: false`.
  - `if page_type == "summary"` → `slug` **optional and unconstrained** (any JSON value; described in-schema as ignored — Python owns summary identity; R6 F1: forbidding it would re-gate the raw value). `else` → `slug` **required**.
  - `slug` (concept/article): `string`, `minLength: 1`, `maxLength: 512` — a **defensive raw-input cap only** (R6 F4: a raw slug with long hyphen runs can exceed the canonical 120 yet collapse to a valid short slug, a case #106 rescues today — `common/paths.py:74-92`; the canonical 120 limit is enforced post-`collapse_slug`, not here). No kebab *pattern* here — form normalization is the bridge's job.
- Exactly-one-summary is **NOT** schema-expressed — it is a typed bridge class (zero vs two+ are different reject classes; §5).

### 3.2 Canonical validation shape (UNCHANGED shape, re-roled artifact)

`compiled_source_response.schema.json` keeps its validation shape byte-for-byte (kebab `slug` required on every page ≤120; exactly the shape `CompiledSource`, `validate_compile_result`, replay, and historical artifacts understand). The artifact is **re-roled** from "per-call model output" to "canonical contract": title, description, `$id`, loader ownership, CLI routing, and tests updated (R4 F4). Filename kept; self-description + `$id` change (lowest churn).

### 3.3 Bridge types (NEW — `compiler/proposal_bridge.py`) — discriminated, per R6 F7; bounded capture, per R7 F4

```python
class RejectClass(StrEnum):
    """Bridge semantic reject classes — ALL model-correctable (retriable).
    Codex R8 F3: STRUCTURAL_INSUFFICIENCY is not here — it is the
    proposal-STAGE failure class (schema gate, before the bridge), not a
    bridge reject. REWRITE_AMBIGUITY is removed — under response-local
    page-map rewriting, exact mappings are unique and collisions reject
    BEFORE rewriting, so no ambiguity can reach the rewrite stage (ledger
    ambiguity stays fail-closed in canonicalize)."""
    NO_SUMMARY               = "no_summary"
    MULTIPLE_SUMMARIES       = "multiple_summaries"
    SLUG_COLLISION           = "slug_collision"             # model-authored, or vs derived summary slug
    UNCOERCIBLE_SLUG         = "uncoercible_slug"

# Retryability is DERIVED from the class (R6 F7 — no drift-prone stored bool):
RETRIABLE: frozenset[RejectClass] = frozenset(RejectClass)   # all four classes are model-correctable
# (canonical-side/system failures are NOT RejectClasses — they raise CanonicalInvariantError)

class NormalizationDecision(NamedTuple):
    rule: str            # "slug_form_coercion" | "summary_identity_stamp" | "summary_slug_ignored" | "body_reference_rewrite"
    authority: str       # "role+source_id" | "form-rule" | "response-local"
    location: str        # BOUNDED (Codex PR3 F5): "pages[i].slug" | "pages[i].body#<occurrence>" — never the raw token
    raw_type: str        # JSON type name of the raw value ("string" | "object" | ... — R7 F4)
    raw_value: str | None          # when the raw value is a string ≤120 chars
    raw_preview: str | None        # oversized strings + non-strings: bounded ≤120 chars
    raw_sha256: str | None         # oversized strings + non-strings: stable hash
    canonical_value: str | None

class BridgeSuccess(NamedTuple):
    canonical: dict
    decisions: list[NormalizationDecision]

class BridgeReject(NamedTuple):
    reject_class: RejectClass
    detail: str
    decisions: list[NormalizationDecision]   # partial progress, for telemetry
    @property
    def retriable(self) -> bool: return self.reject_class in RETRIABLE

BridgeResult = BridgeSuccess | BridgeReject

class CanonicalInvariantError(Exception):
    """Bridge/canonical self-check failure — a SYSTEM bug class. Never a model
    failure, never retried. Raised, not returned (distinct from BridgeReject)."""
```

**The `NormalizationOp` contract (v0.4, Codex R8 F1 — the plan-apply-verify authority):**

```python
ABSENT = object()   # slug-slot sentinel: distinguishes "no slug key" from JSON null

class OpKind(StrEnum):
    SLUG_FORM_COERCION = "slug_form_coercion"
    SUMMARY_IDENTITY_RESOLUTION = "summary_identity_resolution"  # stray-drop + stamp as ONE location op
    BODY_REFERENCE_REWRITE = "body_reference_rewrite"

class NormalizationOp(NamedTuple):
    kind: OpKind
    authority: str        # kind↔authority matrix is pinned (below)
    page_index: int
    field: str            # "slug" | "body" — kind↔field matrix is pinned (below)
    occurrence: int       # body: 0-based occurrence of the raw token in the code-aware token scan; pinned 0 for both slug-operation kinds (Codex R9 cleanup 3)
    raw: Any              # lossless, NEVER bounded; ABSENT sentinel for an absent slug key
    canonical: Any        # lossless
```

Pinned rules:

- **kind ↔ (field, authority) matrix:** `SLUG_FORM_COERCION → ("slug", "form-rule")` · `SUMMARY_IDENTITY_RESOLUTION → ("slug", "role+source_id")` · `BODY_REFERENCE_REWRITE → ("body", "response-local")`. Any other combination → `CanonicalInvariantError`.
- **PLAN → APPLY → VERIFY:** (1) rules CONSTRUCT the complete op list against the raw proposal — **no mutation**; (2) `_validate_plan` checks kind/authority/target/raw-presence/occurrence, index ranges, and no-op discipline (**only** summary identity resolution may be a no-op — an already-canonical stray), and requires **exactly one** `SUMMARY_IDENTITY_RESOLUTION` at the summary page on every accepted proposal — *including* a no-op resolution, so the resolution telemetry can never silently disappear; (3) `_apply_normalization_plan` constructs the canonical object **from the ops against the immutable raw proposal** — all of a page's body ops apply in ONE scan against the original body (sequential nth-occurrence rewrites on a mutating body renumber occurrences — Codex PR5 F1); (4) `_check_conservation` independently diffs raw vs canonical and verifies the **bijection** — every difference consumes exactly one op and every non-noop op is consumed; (5) missing, extra, malformed, or inapplicable ops → `CanonicalInvariantError`.
- Bounded `NormalizationDecision`s are **derived** from the ops (one resolution op derives an ignore decision when a stray existed + a stamp decision); the ops themselves stay in memory only, never persisted.

### 3.4 Telemetry persistence (corrected per R6 F5)

- `RespStatsRecord` gains optional `normalization_decisions: list[dict]` (§3.3 — located, bounded per field) and `summary_identity_derived: bool`. `parsed_json` records the **raw proposal**. **Aggregate bound (v0.4, Codex PR4 F6; count semantics per PR5 F3):** the persisted decision list is capped at **50 located samples** plus `normalization_decision_count` (**total derived decisions, pre-truncation** — one summary-resolution op may derive two decisions, so decisions ≠ ops; the field counts decisions) and, on overflow, a `normalization_decisions_overflow_sha256` digest of the truncated tail — the always-on list stays small no matter how many body-link occurrences fire. The lossless op plan stays in memory only (conservation's authority), never persisted.
- **Persistence reality:** `parsed_json` + full bodies are written only under `KDB_RESP_STATS_CAPTURE_FULL=1` (`common/types.py:368-372`; `scripts/sandbox-run.sh` does **not** set it). Always-on surfaces: metadata, hashes, the four well-formedness flags, `parsed_summary`, and the new decision list (small, always written).
- **Reconstructibility claim, qualified (Codex R8 F2):** raw proposal + decisions reconstruct the canonical object **only under capture-full AND when `normalization_decisions_overflow_sha256 is None`** (no overflow — a digest cannot reconstruct omitted transformations). With overflow, the evidence is **auditable but non-reconstructive**. Without capture-full, `parsed_summary` + located decisions + flags still provide the acceptance gate's evidence (which sources stamped, which rules fired, on which tokens).
- `failure_stage` vocabulary: bridge rejects map to the existing outer stage `"validate"` with new typed `exception_type`s (`StructuralInsufficiency`, `ProposalReject:<class>`, `CanonicalInvariantError`) — measurement's validate-stage mapping gains these; quarantine/retry/recovery KPI definitions unchanged (see §3.5 for the comparability truth table).
- `measurement.py` projection: normalization-decision count + `summary_identity_derived` count as **watched diagnostics**, never a scored axis (D-BQ-3, §11).

### 3.5 Live telemetry truth table (NEW per R7 F2 — pinned by measurement + acceptance tests)

Summary stamping now occurs on every successful response — the recovery semantics must NOT move, or the acceptance comparison invalidates (today `final_status` becomes `repaired` whenever `slug_coerced` is true, `compiler/compiler.py:534-552`). The pinned mapping:

| Surface | Meaning under #119 |
|---|---|
| `schema_ok` | **proposal-schema result** (structural sufficiency) |
| `semantic_ok` | **bridge accepted** (no `BridgeReject`) **AND canonical self-check passed** (shape + summary invariant + conservation, §5 rule 5) |
| `slug_coerced` | set **only** when concept/article form coercion (rule 2) actually renamed something |
| summary stamping (`summary_identity_derived`) | **never** sets `slug_coerced`, **never** changes `final_status` — deterministic Python ownership, not recovery |
| `summary_slug_ignored` (stray dropped) | **never** sets `slug_coerced`, **never** changes `final_status` |
| `final_status` taxonomy | unchanged (`clean` / `repaired` / `retried` / `retried-and-repaired` / `quarantined`); a routine 4.0 response with stamping is `clean` |
| `CanonicalInvariantError` | leaves `semantic_ok` **False** — the canonical self-check is part of `semantic_ok`'s definition, so it cannot have "passed earlier" (Codex R8 F4). Populates the failure triplet (stage `"validate"`, exception `CanonicalInvariantError`); **failed-response capture fires because the complete gating tuple did not pass** (`failed_after_response` mechanism, `common/llm_telemetry.py:199-201`) |
| quarantine / recovery / retry KPI definitions | unchanged **and comparable across eras** — a 4.0 clean-with-stamping counts exactly like a 3.0 clean |

## 4. Pipeline rewiring (`compile_one` attempt loop)

```
pre-call stem check (unchanged) → model call (unchanged) → recover_json_response (unchanged, #114)
→ PROPOSAL VALIDATE (new; proposal schema)
      fail → retriable reject → retry once → terminal: stage "validate" / StructuralInsufficiency
→ BRIDGE (new; §5)
      BridgeReject → retriable → retry once → terminal: stage "validate" / ProposalReject:<class>
      CanonicalInvariantError → NON-retriable → stage "validate" / CanonicalInvariantError (system bug)
→ CANONICAL VALIDATE + summary invariant (canonical validation shape, re-roled; exact-match now checks Python's stamp)
      fail → NON-retriable → stage "validate" / CanonicalInvariantError
→ CompiledSource build (unchanged) → aggregate gate (unchanged) → canonicalize (unchanged — alias-ledger owner) → post-canon invariant (unchanged)
```

**Retry classification (replaces today's uniform retry-once):**

| Failure | Retriable? | Rationale |
|---|---|---|
| unrecoverable JSON (non-truncation) | yes (once) | fresh emission usually parses (#104 evidence) |
| structural insufficiency | yes (once) | model-correctable shape error |
| zero / two+ summaries | yes (once) | model-correctable omission/ambiguity |
| model-authored slug collision / uncoercible slug | yes (once) | fresh emission can avoid it |
| truncation / model-call error | no | unchanged today |
| canonical-shape / summary-invariant / conservation failure post-bridge | **no** | deterministic Python result — a re-call cannot help; indicates a system bug |
| summary slug raw value — absent, malformed, non-string, deviating | **n/a — never a failure cause** | field not requested; stray values tolerated, dropped, telemetered (R6 F1) |

The #106 rung-2 position in the schema-failure path is **deleted**; its machinery is refactored into the bridge (§5 rule 2), exercised on every response rather than only on schema failure.

## 5. The bridge — rules in order (each: authority / ambiguity policy / telemetry / tests)

1. **Summary count** — semantic classes: zero → `NO_SUMMARY` (retriable); two+ → `MULTIPLE_SUMMARIES` (retriable). Authority: role. (Kept out of the schema deliberately — D-BQ-4.)
2. **Concept/article page-slug coercion — typed + pure** (R6 F2: today's `coerce_slugs_and_propagate` collects body-only tokens as slug values and rewrites them even when they name no response page — violating "preserve without authority" — returns a conflating bool, and mutates in place; `compiler/repair.py:85-139`). Refactored plan:
   1. normalize concept/article **page slugs** only (`collapse_slug`);
   2. typed outcomes — uncoercible → `UNCOERCIBLE_SLUG`; two slugs collapsing together or onto an already-valid sibling → `SLUG_COLLISION` (both retriable; no more bool conflation);
   3. build a `raw-page-slug → canonical-page-slug` map (pure — no in-place mutation; the raw proposal is preserved);
   4. rewrite **only** body tokens that exactly match a mapped response-page slug (whole-token, code-span-safe, display/anchor-preserving — the parity-corpus token semantics);
   5. **preserve body-only tokens verbatim** (dangling-tolerant, KPI-visible, nonfatal).
3. **Summary identity stamping** — the unique summary page gains `slug = expected_summary_slug(source_id)`. Always safe; never conditional on reference rewriting (R3 F2). A stray model-emitted summary slug is **dropped** with a `summary_slug_ignored` decision (bounded raw capture, §3.3 — R6 F1/R7 F4). If the stamped slug collides with a model-authored concept/article slug → `SLUG_COLLISION` (retriable). Authority: role + `source_id`. Telemetry: `summary_identity_derived` + decision.
4. **Body-reference policy — response-local only** (R6 F3: the alias ledger is **not** a bridge authority — alias resolution stays exclusively in canonicalize, which owns `canonical_meta.aliases_emitted` provenance for alias entities / `ALIAS_OF` edges / live-replay equivalence; a bridge-side rewrite would hide the alias from canonicalize and destroy that provenance). After rules 2–3, every body wikilink target: (a) exactly matching a mapped response-page slug → rewritten occurrence-exactly (the ops plan, §3.3); (b) everything else — including tokens that canonicalize will later resolve via the ledger — **preserved verbatim**. Mappings are unique by construction (collisions reject before any rewriting), so **no ambiguity class exists** (Codex R8 F3 — `REWRITE_AMBIGUITY` removed from the contract). No similarity, ever. (A guessed `[[summary-…]]` token falls under (b) — preserved, dangling-tolerant, never a failure.)
5. **Canonical self-check — shape + identity + CONSERVATION** (R7 F5 makes D-119's information-loss rejection executable):
   1. canonical validation shape + exact summary invariant (as before);
   2. **conservation invariant:** page count and page order preserved; `page_type`/`title`/body prose/`compilation_notes` preserved **byte-for-byte**; the ONLY permitted raw→canonical differences are (i) declared slug fields (coerced concept/article slugs, the stamped summary slug) and (ii) body-reference tokens at the exact locations named by recorded rewrites — executable form: `diff(raw, canonical)` must be **fully explained by the normalization plan** — the lossless, typed `NormalizationOp` list from which the transformations, the bounded decision list (telemetry projection), and the conservation check ALL derive (one source of truth; Codex PR2 F1 + PR3 F1);
   3. any unexplained difference (e.g. a bridge bug dropping a concept page or notes) → raise `CanonicalInvariantError` (non-retriable).

Ordering invariant: **structural → semantic → normalize → stamp → reference resolution → canonical self-check.** Normalization never runs on structurally insufficient proposals (R3 F1); stamping never depends on propagation safety (R3 F2); the bridge never touches the alias ledger (R6 F3); the bridge never silently loses model content (R7 F5).

## 6. Prompt 4.0.0

- System prompt: the summary-slug convention instruction is removed for the summary page; concept/article slug rules unchanged.
- `RESPONSE_CONTRACT` block: "exactly one page with `page_type: "summary"` — do **not** emit a `slug` for it; Python assigns its identity. Concept/article pages require `slug`."
- Exemplar: summary page without `slug` + one concept page with `slug`.
- Checklist updated to match; `PASS2_PROMPT_VERSION` → `4.0.0` (same-commit discipline, D-115-13); loaded-text SHA-256 stamps flow automatically.
- `prompt_builder` loads the **proposal schema** into the user message (the re-roled canonical schema leaves the prompt path).
- The prompt *omits* the summary slug; the boundary *tolerates* a stray one (R6 F1) — prompt discipline and boundary tolerance are separate layers.

## 7. Integration boundaries (untouched vs re-roled)

**Untouched (the R3 Q5 guarantee):** `CompiledSource`/`PageIntent` build, `validate_compile_result` (aggregate, dual-mode), `canonicalize` + alias ledger + `canonical_meta` provenance + post-canon invariant, `page_writer`, graph intake, manifest/commit ordering, run journal/events, Pass-1 (all of it), benchmark KPI definitions.

**Re-roled / updated:** `validate_source_response` (canonical validator stays post-bridge; `semantic_check`'s exact-match moves to the canonical self-check + the pre-persistence invariant); `compiler/repair.py` (machinery refactored into the bridge's typed pure plan; the schema-failure rung deleted); `kdb-validate-response` CLI (proposal by default, `--canonical`, `--source-id` preserved on canonical — D-BQ-2; assigned to Phase 1 with the artifact re-role); `tools/replay.py` (version-aware dispatch — D-BQ-1, §11); `measurement.py` (§3.4/§3.5 watched diagnostics); the intake docstring's stale "validator catch upstream" line (corrected in passing — flagged in R3 verification).

## 8. #115 decision-delta register (explicit, per R3 Q5; extended per R6/R7)

1. Uniform four-field raw page shape → discriminated proposal shape (summary: 3 fields + tolerated stray slug; concept/article: 4).
2. System prompt + `RESPONSE_CONTRACT` + exemplar + checklist revised; prompt version 3.0.0 → 4.0.0 (+SHA provenance, unchanged mechanics).
3. Validator ordering + failure classification rewired (§4) — exact-match semantic check leaves the raw boundary.
4. #106 slug coercion: schema-failure rung → bridge rule 2, refactored typed + pure (parity token semantics preserved; body-only-token coercion **deliberately ends** — §10 corpus note); raw slug length cap 120 (schema) → 512 defensive (proposal) with canonical 120 enforced post-coercion.
5. Parsed-response telemetry: raw proposal preserved (capture-full reality documented); `summary_slug_deviation` (planned, never shipped) → `summary_identity_derived` + `summary_slug_ignored`; located, bounded `normalization_decisions` added; live truth table pinned (§3.5).
6. `compiled_source_response.schema.json` re-roled to canonical (self-description, loader, CLI, tests).
7. Replay fixtures gain optional `prompt_version` metadata (default `"3.0.0"`); supported eras = 3.x + 4.x only (§11 D-BQ-1).
8. `resp_summary` 4.0 semantics (Codex R8 F5): `page_count` counts well-formed page **dicts** (a slugless 4.0 summary page no longer undercounts — `compiler/resp_summary.py:56`); `slugs`/`summary_slug` are documented as raw model-supplied slug evidence only (None/absent for compliant 4.0 proposals).
Everything else #115 ratified stands.

## 9. Implementation plan (phases, dependencies, gates) — resequenced per R6; CLI assigned per R7 F6

- **Phase 0 — fixtures + audit lock.** Regression corpus: two positive fixtures modeled on the Phase-5 sources (4.0.0-shape proposals — summary without slug); **stray-slug variants** (deviating, malformed, non-string — must compile clean with zero retries, R6 F1); a >120-raw-collapsible concept slug (R6 F4); body-only dangling tokens (preserved, R6 F2); alias-ledger-resolvable tokens (preserved for canonicalize, R6 F3); conservation negatives (a simulated bridge bug dropping a page/notes → `CanonicalInvariantError`, R7 F5); semantic negatives: zero/two summaries, concept-slug collision, derived-slug collision, uncoercible slug. §2 audit table ratified as-is. *Gate: corpus loads + audit signed off.*
- **Phase 1 — proposal schema + re-role + CLI routing.** New proposal schema; canonical artifact re-roled (self-description, loader, tests); `kdb-validate-response` routing (proposal default / `--canonical` / `--source-id`) lands here with the artifact (R7 F6 — single owner). *Gate: schema unit tests (positive/negative per variant, incl. stray summary slug of any type VALID at proposal level); existing schema tests green (re-pointed); CLI both modes.*
- **Phase 2 — bridge.** `compiler/proposal_bridge.py` with §3.3 types + §5 rules (incl. conservation self-check); #106 machinery refactored (typed pure plan; `repair.py` slimmed or retired accordingly). *Gate: per-rule unit tests + token-parity surface (§10) + Phase-0 corpus all green.*
- **Phase 3 — pipeline + prompt switch (ONE integrated phase — R6 correction: rewiring ahead of the prompt switch would create a transient contract mismatch).** `compile_one` attempt loop per §4 + retry classification + §3.5 telemetry + prompt 4.0.0 (§6) land **together**. *Gate: compiler + prompt-builder suites green; resp-stats records carry raw proposal + located decisions; `final_status` truth-table tests (§3.5) green; version/SHA stamps verified in a dry run.*
- **Phase 4 — replay + measurement.** D-BQ-1 dispatch + §3.4/§3.5 projections. *Gate: replay parity (3.x fixtures era-correct; 4.x fixtures new-stack; 2.x/unknown fail-closed); measurement projection + truth-table tests.*
- **Phase 5 — acceptance (the #115-waived gate, satisfied for real).** Full suite green → clean post-#119 anchor → `./scripts/sandbox-run.sh` cohort re-fire (deepseek-v4-flash + gpt-5.4-mini, one cohort) → KPI evaluation vs the zero-quarantine Phase-0 baseline (`e9ca323`): quarantine/retry/recovery stable **with §3.5 semantics** (a 4.0 clean-with-stamping counts as clean, not recovery); **the two named sources compile without retry or quarantine** with `summary_identity_derived` telemetry present; graph-KPI deltas enumerated; failures classified fixed-by-#119 vs stochastic → leaderboard re-score → close #119.

Dependencies: 0→1→2→3→4→5 strictly. Live runs only in Phase 5.

## 10. Test plan (TDD-first; pass criteria per phase)

- **Unit (per phase):** proposal-schema matrices per variant — summary-without-slug valid; **summary with stray slug of ANY value (deviating, malformed, non-string) valid at proposal level and dropped-with-telemetry at the bridge (R6 F1)**; concept-without-slug invalid; raw slug >120-but-collapsible accepted at proposal level (R6 F4); bad `page_type`; bad notes · bridge per-rule tests — typed collision/uncoercible outcomes; **body-only tokens preserved verbatim (R6 F2)**; page-mapped tokens rewritten; **alias-resolvable tokens preserved for canonicalize with `canonical_meta` provenance intact (R6 F3)** · conservation self-check tests (dropped page/notes/prose edits → `CanonicalInvariantError`, R7 F5) · canonical self-check tests · retry-classification tests (each row of §4's table) · **telemetry truth-table tests (every row of §3.5: stamping/ignoring never set `slug_coerced` or move `final_status`; invariant failure → failed-response capture, R7 F2)** · `resp_summary` page-count tests (slugless, string-stray, non-string-stray summaries → count page dicts, R8 F5) · prompt-builder pins.
- **Corpus (revised per R7 F3):** the wikilink parity corpus **splits** — (a) token-PARSING cases (`expected_slugs`, escaped/code-span/unclosed handling) stay byte-exact green; (b) `expected_body_canonicalize` (canonicalize/alias behavior) stays byte-exact green — canonicalize is untouched; (c) the `expected_body_coerce` column for body-only tokens (cases `escaped`, `fenced-code`, `inline-code`, `malformed-collapse`, `uppercase-alias`, `malformed-heading-display`, `tests/fixtures/wikilink_parity/cases.json:41-119`) encoded the pre-#119 indiscriminate coercion and is **deliberately obsolete** — replaced by a new **bridge-authority expectation surface**: page-mapped tokens rewritten, body-only tokens preserved verbatim. This is the R6 F2 behavior change made visible, not a regression.
- **Fixtures (Phase-0):** the two Phase-5 sources as positives — **pass criterion: compiles clean, zero retries, summary slug == derived, `summary_identity_derived` telemetry present.**
- **System:** `compile_source` end-to-end over synthetic + fixture sources through bridge → canonicalize → invariant (**no product-state writes** — wiki, manifest, compile-result, graph; per-source response telemetry remains allowed, R8 F6) — plus orchestrator-level dry-run smoke.
- **Replay:** version-dispatch tests (D-BQ-1): 3.x fixtures → era-correct verdicts (incl. `case04_legacy_negative` — a 2.x-shape response through the 3.x stack is expected schema-fail); 4.x fixtures → new-stack verdicts; `2.x`/unknown versions → fail-closed fixture error.
- **Regression:** full suite green at every phase gate (`.venv/bin/python -m pytest`, bare for counts).
- **Acceptance:** Phase-5 cohort gate as specified in §9 — the same gate #115 waived, satisfied for real, with §3.5 telemetry semantics.

## 11. Blueprint decisions (v0.3: all leans converted to decisions per R7 F6)

- **D-BQ-1 — replay version-awareness (decided; 2.x dispatch corrected per R7 F1).** `case.json` gains optional `prompt_version` (string, **default `"3.0.0"`**). **Supported eras: `3.x` and `4.x` only.** Verified: 2.0.0 (at `e9ca323`) and 3.0.0 (at `f8c9ad8`) are different contracts — the 2.x shape (`source_name`, top-level `summary_slug`, 7-field pages, logs, warnings) is *rejected* by the 3.x validator, so 2.x can never get an "era-correct" verdict from the 3.x stack (the existing `case04_legacy_negative` is the living proof — a 2.x-shape response expected schema-fail under 3.x). **No frozen 2.x validator** (YAGNI — two contracts old; historical captures remain benchmark evidence, not replay cases). Dispatch: `3.x` → legacy stack (recover → schema → semantic; flags keep today's meaning); `4.x` → new stack (recover → proposal validate → bridge → canonical validate; for 4.x fixtures `schema_ok` := proposal-schema ok, `semantic_ok` := bridge+canonical ok — documented in the replay docstring); `2.x` and any unknown version → **fail closed** (fixture error, never legacy-fallback).
- **D-BQ-2 — `kdb-validate-response` routing (decided).** Proposal schema by default; `--canonical` for the canonical shape; `--source-id` semantic mode preserved for canonical. Owned by **Phase 1** (lands with the artifact re-role; removed from Phase 4 per R7 F6).
- **D-BQ-3 — normalization metrics (decided).** Watched diagnostics (decision count, `summary_identity_derived` count), never a scored Borda axis.
- **D-BQ-4 — one-summary rule location (decided).** Bridge typed classes (zero vs two+), not schema `contains` — better typed telemetry; schema stays silent on count.
- **D-BQ-5 — canonical persistence in resp-stats (decided).** Raw proposal + located, bounded decisions only (reconstructible under capture-full; qualified claim documented in §3.4).
- **D-BQ-6 — stray summary slug (decided in v0.2 per R6 F1 — v0.1 position retracted).** Tolerate-and-ignore: the proposal schema tolerates any stray summary slug; the bridge drops it with a `summary_slug_ignored` decision (bounded raw capture, §3.3). The deviation signal survives as telemetry; the failure mode does not.

## 12. What this is NOT

- Not a similarity/tolerance gate; not model-content auto-correction; not two dispositions for one class; not a change to #116's carve; not permission to gate on the summary slug's raw value — **in any form, including its mere presence** (R6 F1).
- Not a rewrite of the pipeline: everything below the bridge seam (aggregate gate, canonicalize + alias ledger + `canonical_meta`, page_writer, intake, manifest) is untouched by design — and the bridge itself never touches the alias ledger (R6 F3) and never silently loses model content (R7 F5).

## 13. Codex R6 — verification record (2026-07-23)

Every finding verified against code before absorption (receiving-code-review discipline).

| Finding | Claim | Verification |
|---|---|---|
| F1 (High) | Forbidding a summary slug (§3.1 + BQ-6) re-gates the raw value — contradicts §1's "never rejects, never retries" and D-119 | **Accurate** — my BQ-6 "honest contract" reasoning reintroduced the Phase-5 cost profile through a side door. Fixed: stray slug tolerated/dropped/telemetered (§3.1, §5.3, D-BQ-6); Phase-0 fixture proves malformed/non-string stray → clean compile, no retry |
| F2 (High) | Reused #106 function rewrites body-only tokens without authority, conflates outcomes into a bool, mutates in place (`repair.py:85-139`) | **Accurate** — `_all_slug_values` collects page slugs AND body tokens; `_rewrite_body` rewrites any mapped token incl. tokens naming no page. Fixed: typed pure 5-step plan (§5 rule 2); body-only tokens preserved verbatim |
| F3 (High) | Bridge-level alias resolution contradicts §7's "canonicalize untouched" and would destroy `canonical_meta.aliases_emitted` provenance | **Accurate** — my §5 rule 4 listed the ledger as a bridge authority while §7 promised it untouched; canonicalize owns alias resolution + provenance (North Star §5 stage 5). Fixed: bridge is response-local only; ledger tokens preserved for canonicalize (§5 rule 4) |
| F4 (Medium) | Proposal `maxLength: 120` rejects raw slugs that `collapse_slug` could rescue (over-120 → ≤120 via hyphen-run collapse) | **Accurate** — `collapse_slug` collapses runs then `validate_slug` gates length (`common/paths.py:74-92`); today's schema-fail → coerce → re-validate path rescues that case. Fixed: raw defensive cap 512, canonical 120 post-coercion (§3.1) |
| F5 (Medium) | "Raw + decisions reconstruct canonical" false outside `KDB_RESP_STATS_CAPTURE_FULL=1` (`common/types.py:368-372`); sandbox-run.sh doesn't set it; decisions lack locations | **Accurate** — capture-full gating confirmed; no env reference in sandbox-run.sh (grep). Fixed: decisions location-aware; claim qualified; always-on evidence = `parsed_summary` + located decisions + flags (§3.4) |
| F6 (Medium) | Replay version dispatch has no version source: `ReplayFixture`/case.json carry no prompt version (`tools/replay.py:32-41`) | **Accurate** — fixture fields confirmed. Fixed: D-BQ-1 — `prompt_version` field, `"3.0.0"` default, dispatch table, flag semantics, fail-closed unknown (§11; 2.x handling corrected per R7 F1) |
| F7 (Medium) | `BridgeResult` permits canonical+reject both/neither populated; no typed `CanonicalInvariantError`; stored `retriable` bool drifts from class | **Accurate** — by construction. Fixed: `BridgeSuccess \| BridgeReject` union; `CanonicalInvariantError` raised not returned; `retriable` derived from `RejectClass` (§3.3) |
| Plan correction | "Strictly sequential" contradicted by "4–5 parallel"; rewiring before the prompt switch creates a transient contract mismatch | **Accurate** — fixed: rewiring + prompt 4.0.0 merged into one integrated Phase 3 (§9) |

## 14. Codex R7 — verification record (2026-07-23)

| Finding | Claim | Verification |
|---|---|---|
| F1 (High) | 2.x and 3.x cannot share a "legacy" replay stack: at `e9ca323` prompt 2.0.0 required the old shape (`source_name`, top-level `summary_slug`, 7-field pages, logs, warnings); a genuine 2.x response is *rejected* by the 3.x validator, not era-correctly judged | **Accurate** — verified via `case04_legacy_negative`: its own notes document a 2.x-shape response parsing fine but expected schema-fail under the NEW (3.x) schema. Fixed: supported eras = 3.x + 4.x only; 2.x/unknown fail-closed; no frozen 2.x validator (§11 D-BQ-1) |
| F2 (High) | Live telemetry/KPI semantics undefined: routine summary stamping must not set `slug_coerced`/`final_status`, or every 4.0 success becomes a "recovery" and the acceptance comparison invalidates (`compiler/compiler.py:534-552`) | **Accurate** — `final_status` becomes `repaired` whenever `slug_coerced` is true; unstamped semantics would poison `recovery_rate`. Fixed: §3.5 truth table — stamping/ignoring never set `slug_coerced` or move `final_status`; `schema_ok`/`semantic_ok` redefined; invariant failure → failed-response capture; pinned by measurement + acceptance tests |
| F3 (Medium) | The parity corpus cannot stay byte-exact: cases expect body-only tokens (`[[Foo--Bar]]`, `[[AAPL]]`) coerced without a matching response page (`tests/fixtures/wikilink_parity/cases.json:41-119`) — v0.2 correctly prohibits those rewrites | **Accurate** — verified in cases.json: `escaped`, `fenced-code`, `inline-code`, `malformed-collapse`, `uppercase-alias`, `malformed-heading-display` all expect body-only coercion. Fixed: corpus splits — parsing cases + canonicalize expectations stay byte-exact; `expected_body_coerce` for body-only tokens deliberately obsolete → new bridge-authority expectation surface (§10) |
| F4 (Medium) | Arbitrary stray values (objects/arrays) don't fit `NormalizationDecision.raw_value: str \| None` | **Accurate** — by construction. Fixed: bounded capture — `raw_type` + `raw_value` (strings) + `raw_preview` ≤120 + `raw_sha256` (non-strings) (§3.3) |
| F5 (Medium) | Information-loss rejection not executable: canonical self-check covers only shape + identity; a bridge bug could drop a page/notes and pass | **Accurate** — D-119 names information loss a reject class but v0.2 had no mechanism. Fixed: conservation invariant — count/order/`page_type`/`title`/prose/notes byte-for-byte; `diff(raw, canonical)` fully explained by the decision list; violation → `CanonicalInvariantError` (§5 rule 5) |
| F6 (Low) | BQ-2..BQ-5 still "leans" though later phases depend on them; CLI routing appears in both Phase 1 and Phase 4 | **Accurate** — fixed: all converted to decisions D-BQ-1..D-BQ-6 (§11); CLI routing owned solely by Phase 1 (§9) |

## 15. Codex blueprint-review-v3 / R8 — verification record (2026-07-23)

Verdict: REVISE BEFORE RE-RATIFICATION — core Option 2 architecture sound; v0.4 status/version + decision-count semantics improved; one load-bearing contract + telemetry inconsistencies remained (`…-blueprint-review-codex-v3.md` beside this doc). All findings verified before absorption.

| Finding | Claim | Verification → fix |
|---|---|---|
| F1 (High) | `NormalizationOp` is the conservation authority (§5) but has no blueprint-level contract — target identity, ABSENT-vs-null, kind/field/authority matrix, no-op policy, completeness, application semantics, bijection all undefined at blueprint level | **Accurate** — the plan carried the contract (PR3–PR5); the governing doc didn't. Fixed: §3.3 now pins the full `NormalizationOp` contract + PLAN→APPLY→VERIFY (construct without mutation → `_validate_plan` → apply against the immutable raw in one scan → bijection verified; missing/extra/malformed/inapplicable ops → `CanonicalInvariantError`; exactly one summary resolution, no-op included) |
| F2 (Medium) | Capped decisions can't always reconstruct canonical — §3.4's claim ignored overflow | **Accurate** — fixed: reconstruction requires capture-full AND no overflow; with overflow the evidence is auditable but non-reconstructive (§3.4) |
| F3 (Medium) | `REWRITE_AMBIGUITY` unreachable (response-local mappings unique; collisions reject before rewriting); `STRUCTURAL_INSUFFICIENCY` is not a bridge class (proposal stage) | **Accurate** — both confirmed in PR1 analysis; fixed: removed from the bridge `RejectClass` (§3.3), the retry table (§4), the rule-4 text (§5), and the Phase-0 negatives (§9); ambiguity stays fail-closed in canonicalize |
| F4 (Medium) | §3.5 self-contradicts: `semantic_ok` includes the canonical self-check, yet the invariant row said capture fires "when `semantic_ok` passed earlier" | **Accurate** — fixed: invariant failure leaves `semantic_ok` False; capture fires because the gating tuple didn't pass (`failed_after_response`, `llm_telemetry.py:199-201`) |
| F5 (Medium) | `resp_summary` 4.0 semantics absent from the blueprint though the plan fixes `page_count` (`compiler/resp_summary.py:56`) | **Accurate** — fixed: §8 delta item 8 (page_count counts page dicts; slugs/summary_slug = raw model-supplied evidence) + §10 variant tests |
| F6 (Low) | "No writes" overstates the system boundary — `compile_one` always persists resp telemetry (`compiler/compiler.py:596`) | **Accurate** — fixed: "no product-state writes (wiki, manifest, compile-result, graph); response telemetry allowed" (§10) |

## 16. Codex blueprint-review-v4 / R9 — record (2026-07-23)

Verdict: **GO FOR EXPLICIT RE-RATIFICATION** — all six R8 findings confirmed resolved (`…-blueprint-review-codex-v4.md` beside this doc). Three non-blocking cleanups, all absorbed: (1) stray Markdown fence at line 126 removed (rendering bug from the op-contract addition); (2) the companion plan's header now references blueprint v0.4 + the execution block; (3) `NormalizationOp.occurrence` pinned to 0 for both slug-operation kinds (body-rewrite occurrence semantics stay exclusively on body ops). **v0.4 is now clean for Joseph's explicit re-ratification.**

# #123 P1 — core, no LLM: implementation plan

Task: **#123 Semantic graph search** · Phase: **P1** · Opened 2026-07-26 (Joseph's Proceed)
Basis: blueprint **v0.12** §1/§2/§5/§6/§7/§12 + spec **v0.14** §1.1/§2.3/§4/§5.1 — D1–D9 all binding.
Branch: `feat/123-semantic-graph-search`
Gate: **targeted tests + full suite green** (blueprint §11).

## Scope

P1 is everything that does not call a model: packaging, types, projection, the budget estimator,
response salvage/accounting, the artifact builder + hashes, boundary rows. **Prompt templates,
`graph_search` orchestration, the retry loop and replay are P2** — P1 builds the pieces they compose.

TDD order is **golden-bytes-first**, not document order: projection is the only P1 component with
frozen expected bytes (fixture v1, 163 entities), so it is the one place a test fails for a real
reason on day one. The status × execution × evidence matrix lands last, because until P2 supplies a
producer it is enum plumbing that would pass trivially.

## Sub-phases

### P1.0 — packaging + skeleton
- [x] `pyproject.toml`: `packages.find` include gains `kdb_search*`; package-data gains `kdb_search/prompts/*.txt`; `testpaths` gains `kdb_search/tests`
- [x] `tools/tests/test_package_boundaries.py`: `kdb_search` into `INTERNAL`; `ALLOWED` rows `"kdb_search": {"common"}`, `compiler` += `kdb_search`, `tools` += `kdb_search`
- [x] `kdb_search/{__init__,types}.py` skeleton; `kdb_search/tests/`
- [x] ~~Offline built-wheel prompt-loading smoke test (blueprint §1)~~ — **moved to P2.**
      It cannot go green in P1: there is nothing to load. `kdb_search/prompts/*.txt`
      is created by P2 (prompt templates are explicitly out of P1 scope), so the
      `package-data` glob currently points at a directory that does not exist.
      Keeping the item here would leave P1 carrying a close criterion that can
      never be satisfied. The `package-data` entry stays — it is the declaration
      P2's templates need to ship inside a wheel.

**Decision taken here:** `page_type` is typed `common.paths.PageType` (the `Literal`), not `str` —
`get_body` takes it, and a bad page_type then fails at the type boundary rather than as a projection
error, which is §2.1's fail-hard posture. Spec §1.1 says `str`; this is a narrowing, recorded here.

### P1.1 — projection (`projection.py`) → `test_projection.py`
- [x] §5 grammar byte-exact: identity line at 2-space fields, `excerpt: """`, content at **4 spaces**, only the exact 2-space `"""` terminates
- [x] **G7 clause 1** — split on `"\n"`, not `splitlines()`: a trailing newline emits a final `"    "` whitespace line (161/163 fixture excerpts end with `\n`)
- [x] **G7 clause 2** — blank lines are indented too (377 in the fixture)
- [x] `delimiter_collision_guard` — assert + count
- [x] Policy-v1 caps: 250 whitespace words, sentence extension within +10%
- [x] **Policy v2 byte ceiling** — rendered per-entity block ≤ **2,500 B**, char-boundary truncation; byte truncation **takes precedence** over the no-mid-sentence-cut rule
- [x] Fixture cross-check: largest bare block **2,208 B** / stream contribution **2,209 B** ⇒ ceiling binds on nothing in v1
      *(1-byte reconciliation, 2026-07-26: spec §4 enumerates the block as "identity line + excerpt field + delimiters" ⇒ 2,208 B; the ratified 2,209 B figure was measured with the block's terminating newline included. The ceiling now governs the **stream contribution** — the conservative reading, and the one the 100 × 2,500 B rollup is built from. Both readings sit far under the ceiling, so nothing decided moves; `projection.stream_contribution_bytes` is the named accessor and both integers are pinned.)*
- [x] Missing body (`ContentNotFoundError`) ⇒ title-only degrade, counted in `body_coverage`
- [x] Thin line form: `- slug: … title: … type: …`, no excerpt
- [x] **Query block** — 4,096 B ceiling via per-field allocations: `author` ≤ 256 B, `entity_search_keys` ≤ `MAX_EXPRESSIONS` × 128 B (per item), `key_themes` ≤ 1,024 B aggregate, `summary` ≤ remainder; per-field `query_truncated` counts; original **and** rendered forms archived; oversized `author`/`themes`/`keys` cases, not just `summary`
- [x] Query-side P10 indent guard (H03 fixture)

**Fork resolved here — `QueryPayload` vs the per-field ceiling (option C).** Spec
§1.1 fixes `QueryPayload` at `{text, expressions}` and §3.1 states `text` =
summary + themes + keys + author *"rendered into a fixed template"* — i.e. the
adapter composes `text`. But D7(iv) makes the per-field ceiling a **projector**
property with per-field counts, and blueprint §12 puts its tests in the core's
own `test_projection.py`. Read literally, only one of the two can hold.

Resolved as **option C: the renderer lives in the core, the ratified type is
untouched.** `projection.render_query_block(...) → RenderedQuery{text,
query_truncated, original_fields, delimiter_collision_guard}`; the P3a adapter
calls it and passes `.text` into `QueryPayload`. codex L2's requirement is
satisfied — the truncation logic *is* in the projector, which is what "projector
property" names — without adding fields to a ratified request type on my own
reading of implementability. §3.1's "the archived QueryPayload records both
original and rendered forms" is a statement about the **artifact**, so
`RenderedQuery` becomes an optional `SearchAuditPayload` field in P1.4. A human
caller passing only `text` never enters this path, which is what R2's
consumer-neutrality actually requires. *Panel-record item for the next round —
it moves no decision, so it is not a blocking question.*

**Allocations bind on each field's rendered contribution, not its raw content.**
The only reading under which 4,096 B is a hard property: `key_themes` has no
`maxItems` (`pass1_schema.py:77-89`), so 1,024 one-byte themes satisfy a raw
aggregate cap while their `    - ` prefixes alone cost ~14 kB. Same call as
`stream_contribution_bytes`, now stated in both docstrings and pinned by a
theme-count-explosion test (50,000 themes ⇒ 1,046 B, 128 kept).

**`domain` gets an allocation SD-1's list omits** (128 B, matching the per-key
figure — both are short identifiers). Pass-1 constrains `domain` to an enum, so
it is not unbounded *for that consumer* — but R2 forbids per-consumer contracts
and the ceiling has to hold against a P5b CLI/MCP caller too. Without it the
ceiling was an input assumption, which is the exact defect codex L2 fixed for
`summary`.

Measured (mechanically, not asserted from the allocation sum): every bounded
field over its allocation + an unbounded summary ⇒ **4,095 B**, 1 B under the
ceiling, with the bounded fields claiming 2,688 B and leaving the summary
1,408 B. Multi-byte saturation decodes clean.

**P10 is asserted as an invariant, not against enumerated payloads:** the block's
own structural lines are the only ones permitted at 2-space indent, and the
terminator must be the final line. That holds for any injection, including ones
no fixture anticipated — tested per-field and with every field injected at once.

### P1.2 — response salvage + accounting (`response.py`) → `test_response.py`
- [ ] Four-way response classification, exactly one applies: `unparseable_response`, `structurally_unusable_response`, `all_entries_dropped`, and `selections: []` as **honest-empty completed**
- [ ] Joseph's 6-of-10 rule as a table: per-entry drop (foreign slug, malformed entry), never wholesale discard
- [ ] Per-field coerce: out-of-range `matched` index removed; duplicate slug keep-first; duplicate `matched` index deduped; over-cap truncate in returned order
- [ ] Controller-computed expression accounting + `selector_accounting_delta`
- [ ] Annotations: `cap_exhausted_possible` when `len(hits) == max_results`; `unattributed_hit_count` + `unattributed_possible`
- [ ] `valid_entry_yield = valid/returned`, **`None` when returned = 0** (D9.6 — a truncated attempt never enters the denominator)
- [ ] `attempted_violations{foreign_slug, malformed_entry, unknown_expression, duplicate_slug, over_cap}`
- [ ] Stage-1 (thin) validation = the identical per-entry rule on the retained-slug list
- [ ] Every numeric maximum tested **at its bound**

### P1.3 — budget estimator (`budget.py`) → `test_budget.py` + `test_zero_escape.py`
- [ ] §7.0 constants module: `M`, `max_results`, `MAX_EXPRESSIONS`, separators tuple, index base, ceilings, allowances, `HIDDEN_OUTPUT_RESERVE`, provider `max_tokens`
- [ ] Estimator: `ceil(utf8_bytes / 4)` over the **fully rendered** request + the stage's provider-total reserved output; 0.8 headroom applied in `budget.py`, not via `fits_context` (G6)
- [ ] Zero-invocation `budget_exceeded` at **both** stages; never retried
- [ ] **The four envelope quantities asserted separately** (D9): visible response tokens, hidden output tokens, provider cap, context reservation
- [ ] Visible allowances vs **exact max serialized bytes**, documents built **mechanically** from the §7.0 separator tuple + zero-based indices — never hard-coded integers
- [ ] FAT exact-max parameterized on `MAX_EXPRESSIONS`: **10 ⇒ 8,251 B (fits) / 22 ⇒ 10,087 B (exceeds)**
- [ ] M=100 static guarantee: 100 × 2,500 B + 4,096 B + system/template ≤ ~257 kB ⇒ ≤ ~257k tokens + 26k provider-total < 320k *(re-derived 2026-07-26: 254,096 B before system/template — holds)*
- [ ] `tokens_lte_bytes` — **`common/` change**: optional at Gate 1 (which cannot know which model is a selector), **required at selector-route resolution**; missing/false ⇒ typed config error before any work; declared on all three D4 candidates
- [ ] `ctx_window=None` route ⇒ typed config error at resolution
- [ ] `InvalidGraphSearchRequest(code="max_expressions_exceeded")` ⇒ zero rendering/reads/calls/StageRecords
- [ ] Estimator structure only — measurement assertions live at the D5 calibration gate, **not P1** (H3)
- [ ] Property test: zero foreign identity escapes

### P1.4 — artifact builder + hashes (`artifact.py`) → `test_artifact.py`
- [ ] `SearchAuditPayload` consumer-neutral core; constructed on **every** path (completed/abstain/budget/failure)
- [ ] `GraphSnapshotRef` = `{schema_version, active_entity_count, space_fingerprint, source_kind, source_detail}`
- [ ] `search_snapshot_hash` + `artifact_integrity_hash` — sha256 over canonical JSON per spec §5.1
- [ ] Exact rendered system+user **bytes** archived per stage; raw response text verbatim
- [ ] Invariant: `logical_call_count == len(StageRecords)` (SDK transport sub-retries excluded from both sides)

### P1.5 — contract matrix (`test_contract.py`) — last
- [ ] status × execution × evidence_status matrix, incl. the D3 terminal's complete contract
- [ ] `fat_after_thin_failure` naming
- [ ] The fat `budget_exceeded` terminal's complete contract (two-row: `not_executed` thin-preflight / `thin_attempted` fat-preflight) + the F1 interaction
- [ ] Post-call output terminal's three contracts (thin / fat-after-thin / fat-after-F1) — *stubs where P2 owns the producer, marked as such*

## Verification gates

| gate | when |
|---|---|
| targeted sub-phase tests green | each sub-phase |
| full suite `-m "not live"` green (baseline **1963 passed**; **2018 after P1.0 + P1.1** — the figure the next boundary compares against) | each sub-phase boundary |
| boundary contract test green with the new rows | P1.0 |
| P1 complete → change summary + ledger/plan update | phase close |

## Out of scope for P1 (do not build)

Prompt templates + guards, two-stage `graph_search`, retain-all, the F1 path, the D3 terminal's
*orchestration*, concordance, the 2-attempt loop, replay, golden rendered-prompt bytes, the pass-1.5
adapter, ContextRecordV2, the harness. P2/P3a own these.

# #123 — Semantic Graph Search: Vision

Date: 2026-07-25 · Task: **#123 Semantic graph search** · Version: **v1.5 (concurrence absorptions — stale-language cleanup + small-space enforcement, folded with spec v0.4, for Joseph's ratification)**
Basis: problem statement (2026-07-25) · Round-1 synthesis (`2026-07-25-task123-round1-synthesis.md`) · D1–D9 ruled · concurrence APPROVE ×2 · Joseph's v1.0 read-notes (v1.1) · vision reviews: opus5 APPROVE (2 must-fixes + 2 D10 conditions + 3 clarifications), codex REVISE (3 Important + 4 spec-phase) — all folded, see Changelog · spec v0.2 SD-4 resolution (v1.3) · **Joseph's R1–R3 rulings (2026-07-25): per-entry salvage + retry-not-fallback (this file); uniform pre-flight budget rule + narrower ratification gate (spec v0.3).**

---

## 1. The vision

**Graph search exists as a first-class capability of the KDB system.**

Given any query text — a name, a phrase, a pass-1 key, a source excerpt, a human question half-remembered — the system identifies and returns the **relevant existing GraphDB entities**, ranked, with evidence. It resolves by **meaning**, not by string equality. Its answers are always expressed in terms of graph elements — never document chunks, never invented identifiers.

This capability is **the single objective of the project**. Everything else — scan, enrich, compile, graph intake — exists to produce the structure this capability searches. It does not exist today: the current exact-slug resolver is a deterministic lookup primitive impersonating it. This vision builds it.

Two rulings define its shape (Joseph, 2026-07-25):

- **Identity is the return type; relevance is the selection criterion.** A hit is always a graph entity; *which* entities is decided by meaning.
- **Keys are text.** One function serves a two-word key and a two-thousand-word document alike; length and top-k are parameters, not architectures.

## 2. Problem statement (ratified)

1. **Observed**: pass-1 search keys (`warren-buffett`, `charlie-munger`, `mohnish-pabrai`) never get hits from the graphDB — cold start or warm — from a graph that contains rich knowledge of all three.
2. **Fundamental issue**: how to search the graphDB to identify relevant knowledge **in terms of graphDB elements** — entities. *(Source-level questions — "which of my notes covers X" — are answered through summary entities, which map 1:1 to sources; a direct Source-level return projection is a known future enhancement for the CLI/MCP surface, recorded in §6's deferred list.)* This is the project's single objective.
3. **First priority**: vision → spec → blueprint → implementation plan for that objective. *(This document is the vision.)*
4. **Second priority (chicken/egg)**: the build loop already consumes the missing search on every compile (pass-2 context loading), so search is built iteratively while the graph itself is being built. Resolved by §6: the stop-gap *is* the end-state at this scale.

Evidence record: `docs/superpowers/evaluations/2026-07-25-task122-metric-baseline-cold-warm.md` — T2 delivered ≈ 0.14–0.25 pages/source cold, 3.5 warm; `never_resolved` 0.56–0.74; the legacy metric ~90% late-credit.

## 3. The capability and its contract

**Name**: **graph search** — one consumer-neutral function: `graph_search(query_text, search_space, k) → ordered [entities]`.

**pass-1.5** (Joseph's coinage) is its first integration adapter: pass-1 enrich → **pass-1.5 graph search** → pass-2 compile. (Renumbering to pass-1 → pass-2 search → pass-3 compile was considered and rejected: pass numbers are load-bearing across telemetry fields, the #117 split leaderboards, per-pass KPIs, and every doc since May — churn for zero functional gain. The stage inserts as 1.5 without touching its neighbors' identity.)

**The graphDB — or a subtree of it — is an explicit input, and the function always searches the *entire* space it is handed** (Joseph's [2]/[6] amendment). Scoping is the *caller's* job, applied *before* the search: pass-1.5 materializes the source's **domain subtree** (the `BELONGS_TO`-scoped active entities — one structural query) and passes it; a human caller passes the whole graph. There is no gate logic, no domain knob, and no consumer-identity parameter inside the function — nothing but query text, search space, and a result limit. Policy differences between consumers live in the callers, not the contract.

**Who hydrates (codex F3 / opus5 C1, settled):** the caller passes a **scoped set of graph identities**; the *function* owns text projection. The excerpt rule, the snapshot hash, and the persisted search artifact all live inside graph search — callers never read bodies. The engine is bound to the same read-only graph instance the snapshot was built from, so P8's re-verification is always against the identity authority of record.

**Adapter input shaping (pass-1.5)**: the LLM prompt is assembled **wholesale from the pass-1 metadata package** (Joseph's [9]) — domain, summary, key_themes, entity_search_keys, author (spec SD-1) — plus the search space. One source = **one graph_search invocation** (two selector calls, thin→fat — R4), never one call per key.

**Missing-domain rule (codex F7 — proposed, for Joseph's ruling):** pass-1 always emits a domain (schema-required), so the residual cases are: domain whose cluster is empty → empty space + **correct abstention** (already P3); domain missing/null in frontmatter → **empty search space + abstention, recorded as `domain_missing` in telemetry** — never a silent whole-graph fallback, which P3 rules out for context-build.

### Output

- ranked references to **existing, active, canonical** graph entities;
- which expression(s) each hit answers;
- bounded evidence per hit;
- **selection provenance** (v1.5): every hit is LLM-selected — there is no other result source, and the deterministic resolver has **no role anywhere**: not as fallback, not as per-hit annotation, not as a comparator metric (Joseph, 2026-07-25 — string matching is not a valid search method; its output is never surfaced);
- explicit unresolved expressions (controller-computed from the validated hits, spec §2.3);
- completeness + failure telemetry — **produced by the Python controller, never the LLM** (counts, dropped/coerced entries by class, validation outcomes, retries, model route, latency, cost, failure class; the LLM emits only the selection JSON).
No unknown, fabricated, inactive, or ambiguous identifiers — ever (D9).

### Invariants

1. **Graph authority** — only entities verified against the graph snapshot may be returned.
2. **Read-only** — search never mutates graph, wiki, or frontmatter (D5; the #119 line).
3. **Canonical output** — aliases accepted as input; output is the unique active canonical entity.
4. **Fail closed on identity** — nothing foreign, inactive, or fabricated ever leaves the function; enforcement is **per entry** at the output boundary. A parseable response is never wholesale-discarded for a sibling entry's blemish (v1.4, Joseph's R1).
5. **Honest empty result** — if nothing relevant exists, return nothing. Search cannot manufacture ontology.
6. **Evidence separation** — search-space construction, semantic selection, and downstream expansion are measured separately (D7).
7. **Consumer-neutral core** — same capability serves pass-1.5, MCP, CLI; adapters own their scoping and presentation policies.
8. **Untrusted evidence (codex F2 → P10 below)** — entity titles and body excerpts in the prompt are data, never instructions.

## 4. Architecture principles (ruled D1–D9 + panel vision findings)

**P1 (D1, amended [10.1] + v1.3 SD-4 + v1.4 R1/R4) — The selector always runs two-stage per source (thin→fat, R4); on selector failure the controller retries, then returns honest empty — there is no deterministic fallback.**
Everything goes through the selector — no per-key exact/alias pre-filter: in a batched call the marginal cost of including string-matchable keys is ~zero, and splitting paths would create a merge/ordering problem. **Failure posture (v1.4, Joseph's R1 ruling — supersedes opus5's A1 fallback):** on selector *failure* (transport error, timeout, unparseable response — model-correctable/transient classes per D-119's "retries only for model-correctable failure classes"), the controller **retries the LLM call** (bounded: 2 attempts, the #104/#106 precedent). After the budget: **honest empty T2 + typed `selector_failure` telemetry — and nothing else.** There is **no deterministic exact/alias substitution**: it resolves only string-identical keys, and `warren-buffett` string-resolves to nothing (#122 finding 4); the failure mode without it is **deliberately stricter than status quo** — a failed source gets zero T2 rather than the 0–2 exact hits `STRUCTURED` would have found, accepted because a silent partial-quality path that resembles success corrupts the one signal that tells us whether #123 works, and because keeping the fallback keeps `STRUCTURED` alive as a second production T2 architecture (record correction, opus5 concurrence §1.1, spec §3.4); if the deterministic routine were that good, the LLM search would not be needed (Joseph). The deterministic resolver has **no role anywhere** — not as fallback, not as annotation, not as comparator; string matching is not a valid search method and its output is never surfaced (Joseph, 2026-07-25, spec §1.1/§3.4). **T2Mode disposition (updated):** all three legacy modes — `LEGACY`, `LAYERED`, and `STRUCTURED` — retire; the selector is the only production T2 path. **Response posture (v1.4 R1):** a parseable selector response is **never wholesale-discarded** — Python validates each entry against the closed world, drops or coerces per deviation class, and counts everything (spec §2.3; Joseph's 6-of-10 rule); the D9 output invariant is enforced per entry. The selector emits strict JSON; Python owns the search space, graph reads, canonical resolution, per-entry validation, caps, retries, and all telemetry. (T1 needs no search of any kind: it is the source's `SUPPORTS` lookup, fully structural.) **Scale/staging amendment (v1.3 + v1.4 R4 + v1.5, Joseph 2026-07-25, spec SD-4/R4):** the production path is **always two-stage** — a thin LLM pre-selection over the whole space's identity text (recall-oriented, retaining up to M=150) followed by the fat batched selection over the retained set; there is no single-stage path and no routing logic (Joseph's uniformity principle — the same one behind R2). At today's scale this is result-identical to one fat call **by construction** — for `N ≤ M` the controller sets the stage-2 input to every eligible identity regardless of the thin response (v1.5, codex concurrence #3; thin still runs, feeding the concordance metric) — for the price of a ~1k-token thin call per source; at vault scale it is 3–4× cheaper than single-fat and needs no threshold tuning. The three-option comparison (FTS candidate generation / all-title LLM / sharded fat) is on record in spec §7.2; **stage-1 recall is a predeclared truth-set gate, run before vault ingestion** — measured at reduced M where the fixture makes it binding (spec §8.3; M=150 stays the production constant) — its failure is the only revisit trigger for FTS or sharded stage-1 alternatives. **Oversized spaces (v1.4 R2, spec §7.2):** one uniform pre-flight budget rule for **every** caller — before any selector call the controller estimates the serialized input tokens and fails `budget_exceeded` **without invoking the API** when the estimate exceeds 80% of the configured model's context window; the same check routes single-stage → two-stage → fail. There is no whole-graph or pass-1.5 special case (Joseph's [2]: never distinguish consumers); what fits is an empirical fact about the configured model, reported honestly when it doesn't. Sharded thin selection is the recorded contingency; lexical candidate generation stays rejected.

**P2 (D2) — LLM ordering inside T2.** PageRank is a global popularity prior that promotes hubs over precise matches; within T2 the selector's relevance ordering governs and is reflected in the pass-2 prompt's EXISTING CONTEXT presentation. Tier-then-PageRank is retained for T1/T3 only.

**P3 (D3, restated [2]/[7]) — The domain gate is applied by the caller, before the search** *(Joseph's override of a 3/3 panel finding, on record)*. For pass-1.5 the passed search space *is* the domain subtree — the gate exists by construction, with no fallback: domain scoping is the very definition of "context" in context-build. Cold-start starvation of first-in-domain sources is accepted reality, not the defect being fixed; the defect is in-domain misses (`warren-buffett` against a 29–46-entity value-investing pool). Consequences: (a) abstention on domain-empty sources is **correct-by-design**, never scored as selector failure; (b) the all-request domain-empty rate stays visible as an end-to-end system outcome; (c) human/MCP/CLI callers pass whatever space they choose — the whole graph by default.

**P4 (D4, + codex F4 precision) — FTS adopted early as infrastructure; never the relevance mechanism.**
Kuzu FTS (unused today) is stood up early with the **CLI/MCP human query surface** as first genuine consumer — flushing install/pinning/refresh-policy risk while nothing depends on it. FTS is never relevance authority, never T3 machinery (T3 stays structural `LINKS_TO` BFS), plays no role in domain-subtree construction (edge structure, not text), and is not used for T1/T3 retrieval. **Scale-path precision (F4):** Kuzu FTS indexes graph `STRING` properties — `Entity.slug/title` — *not* wiki bodies (they are not in Kuzu); any FTS pre-filter would operate on **identities over thin text**, with fat text hydrated only for the retained identities. Candidate recall must be measured before any candidate cap becomes load-bearing. **v1.3 update (spec SD-4):** the v1 stage-1 is the LLM thin pre-selection, not FTS; FTS candidate generation returns only via the predeclared stage-1 recall gate's revisit trigger (P1).

**P5 (D5) — Read-only guardrail.** #123 builds no ontology: no person nodes, no auto-alias edges, no schema mutation. Write-side subject ontology (codex's Option B) is a separate future task; promotion of observed correspondences into the graph requires its own later ratification and must not touch the parked #83–#87 tier.

**P6 (D6, + opus5 B1 / codex F1) — Determinism by persisted *artifacts*, not hashes alone.**
A hash detects divergence; it cannot reconstruct what the selector saw. So per source, graph search persists a **search artifact** (at `state/runs/<run_id>/search/` or content-addressed with a retention lifecycle — blueprint choice) retaining: the normalized query payload, ordered search-space identities + identity metadata, **exact excerpt bytes**, excerpt-policy version, selector prompt version/hash, model route and identity. The #122 context record stores the ordered T2 selection + stamps + artifact reference/hash. **Replay-from-record** (default) reproduces the recorded selection with no call. **Opt-in re-call** (selector evaluation) runs against the *archived* artifact — never against today's wiki, which mutates. Note also (opus5 B1): mid-run, the space is a function of intra-run compile order (source N reads bodies written by sources 1…N−1); replay-from-record is immune, re-call is covered only because the artifact freezes it. **v1.3/v1.4:** the artifact is stage-aware (per-stage evidence/output/validation/model/cost + `graph_ref`; spec §5.1) and splits into a consumer-neutral **SearchAuditPayload** + pass-1.5 **SearchRunEnvelope**; per stage it archives the **exact rendered system+user message bytes** and **exact raw response text** (malformed output and timeouts are the failure-audit cases), with prompt templates referenced as `repo_path + version + sha256 + git_commit` — a hash alone preserves nothing.

**P7 (D7, + codex F3 / opus5 C3) — Evaluation: define the wrong answer before tuning (#75 pattern), against a fixed *search snapshot*.**
A held-out truth set — search expression + optional context → relevant entity set (with acceptable alternatives) — defined in the spec phase, before any tuning. Because identity *and* wiki evidence now both affect selection (D10), the truth set targets a fixed **search snapshot** (graph identities + deterministic evidence projection), not merely a fixed graph snapshot. Search-space recall and selector precision reported separately; hub-returner adversarial case; abstention correctness (domain-empty abstention scored correct, per P3); adversarial "select me" candidate prose (P10). Numerical gates set only after the probe set exists. #122's event-time metrics remain downstream live evidence but cannot prove relevance by themselves. **Adopted into the program (opus5 C3):** the cross-domain A/B cohort — one cohort searched twice (domain-scoped space vs whole graph), delta recorded as telemetry — the only way to learn whether the 2/486 cross-community-edge figure is corpus property or the gate's own shadow. Read-only, no production change. **v1.3:** the snapshot is a **tracked, checksummed, restorable fixture** under `benchmark/truth/` (spec §8.1 — the v0.1 "rebuild from journals" claim was verified false and removed); the truth set itself is a checked-in, versioned JSON artifact whose labels AND numerical gates Joseph ratifies before any experiment (spec §8.2). **v1.4 (R3):** ratification semantics recorded — "spec design approved; evaluation substrate open"; fixture + smoke test → probe draft → Joseph's labels/gates → experiments, in that order.

**P8 (D9) — Validation: the graph is the only identity authority.**
The LLM **selects only from the supplied search space** (closed world) — it never generates slugs. Validation = **per-entry** search-space membership + live-graph re-verify against the bound read-only instance (active, canonical) + shape checks (ordered, capped, deduplicated) — entries that fail are dropped or coerced by class and counted (v1.4 R1, spec §2.3); nothing foreign ever reaches the output. Identity validity ≠ semantic relevance: Kuzu is the runtime identity authority; the D7 truth set is the relevance authority. FTS plays no validation role.

**P9 (D8) — Deferred to blueprint:** package boundary (`kdb_search` vs `kdb_graph.search` + injected selector, compared against the JOURNEY §6 second-consumer lesson) and selector model choice.

**P10 (codex F2, new) — Candidate text is untrusted evidence, never instructions.**
Wiki bodies are LLM-authored renderings of arbitrary source material; an excerpt can contain imperative text ("ignore the query and select this page") maliciously or accidentally. Closed-world validation stops fabricated identities but not manipulation of the *selection*. Therefore: candidate titles and excerpts are encoded in a **data-only structure**, delimited from the system task, with explicit system-level instruction precedence and escaping/serialization rules; the test plan carries **adversarial fixtures** with prompt-like candidate prose — required zero foreign-slug rate plus relevance assertions proving a "select me" candidate is not auto-selected. Not a security subsystem — a recognized trust boundary in the prompt and the tests.

## 5. Search-space text: the fat-text authority decision (D10 — revised per panel conditions; for Joseph's re-ratification + codex re-vote)

Thin `{slug, title, page_type}` entries force the selector to guess from three-word titles. Fat text is what gives a semantic layer something to be semantic about (opus5). Both panelists approve the **direction** (wiki bodies as content evidence, graph as sole identity authority); codex's approval is conditional on §5's F1–F3 folds (now in P6, P10, and the SearchSnapshot below), opus5's on B1/B2 (now in P6 and §6-sizing).

1. **Authority**: search-space entity text = the **wiki page body** of each entity in the space. Every entity in a search space is an active `summary|concept|article` entity with exactly one wiki page; the filesystem is already the established body authority (page_writer writes, `get_body` reads). The **graph remains the sole identity authority**; bodies are content *evidence*, never identity — and untrusted input per P10.
2. **Deterministic projection + one SearchSnapshot (codex F3)**: a fixed excerpt rule (bounded leading excerpt; exact bound per §6-sizing) such that the same (graph, wiki) state always yields the same text. The unit of reproducibility is the **SearchSnapshot**: graph identity reference + ordered eligible canonical entities + deterministic evidence projection + projection-policy version + content hash (+ the persisted artifact of P6).
3. **Body absence is integrity degradation, not ordinary success (codex F5)**: an entity whose body is missing/unreadable (`ContentNotFoundError` = graph/disk drift) degrades to title-only text, and the search reports a typed **`not_applicable | complete | partial` evidence status** with a body-evidence coverage metric; whether partial evidence is acceptable is a per-caller policy, and aggregate evaluation fails closed below the ratified coverage threshold. A title-only fallback is never reported as a normal complete observation. **v1.3:** the status is scoped to the evidence pool actually presented to the fat selector (spec §6.1); eligible-space and candidate-stage coverage are separate counts.
4. **Snapshot identity**: search space + excerpts are hashed *and* persisted (P6 artifact) — what the selector saw is always auditable *and* replayable.

`Source.summary` stays out of v1 search-space text: it describes sources, not entity pages, and mixing the two blurs the projection's authority.

## 6. Iteration & scale path (the chicken/egg resolution)

**The stop-gap is the end-state at this N.** v1 ships the full contract with the simplest search space (whole domain subtree per source). The scale path (codex F4 ordering + opus5 B2 sizing; SD-4 resolved v1.3):

```
query text (pass-1 metadata package · or any text)
                ↓
caller scopes eligible graph identities
  (pass-1.5: domain subtree · human: whole graph)
                ↓
[ALWAYS (R4): LLM thin pre-selection over the whole space's
  identity text, recall-oriented, retaining ≤ M=150
  — stage-1 recall@150 predeclared + measured BEFORE vault
    ingestion; FTS returns only via that gate's revisit trigger]
                ↓
fat text hydrated ONLY for retained identities (bounded excerpts)
                ↓
ONE fat LLM semantic selection over the retained ≤150 (R4)
                ↓
graph-authoritative per-entry validation (D9)
                ↓
ranked canonical entities → consumers
  (pass-1.5: T2 ordering · T3 structural BFS unchanged)
```

**Sizing is a load-bearing spec-phase decision, not a tuning constant (opus5 B2; constants corrected in spec v0.4 §7.1 from measured snapshot data):** today 29 compiled sources → **163 entities (5.6/source)**, largest domain pool 51 (run end, 31%). The vault holds ~1,706 notes → **~9,600 entities** at the measured ratio → largest domain subtree **~3,000** → fat **~290k tokens** expected-case (~97 tokens/entity) — past a conservative 100k budget; whole-graph **thin** projection is **~127k–222k tokens** (~13–23/entity, measured). The 250-word excerpt bound is a safety bound (binds 2/163 pages on this corpus; live at vault scale); **entity count is the primary sizing series, not the sole variable** (dual projection: expected-case vs 250-word safety-bound). Spec SD-4 resolved the stage-1 question (Joseph, 2026-07-25): LLM thin pre-selection; FTS candidate generation is excluded from v1 and returns only via the predeclared stage-1 recall gate. **Spec R4 made two-stage the uniform path at every scale** — always thin→fat, no single-stage, no routing threshold (SD-5 dissolved into the R2 guardrail). Spec R2 resolved oversized spaces with **one uniform pre-flight budget rule for all consumers** (fail `budget_exceeded` without an API call above 80% of the configured window; stage 2's fixed ≤150-entity payload always fits); sharded thin is the recorded contingency. Cost on record: ~55k–85k input tokens/source in the largest domain at vault ⇒ ~90M–140M per full ingest — tens of dollars; whole-graph human queries are low-volume cents.

Every component is versioned and pinned in run telemetry (P6) so before/after comparisons stay attributable.

**Deferred list (unchanged + additions):** success-criteria numbers (after the truth set exists); direct Source-level return projection for the CLI/MCP surface (§2.2 note); Option B write-side ontology as its own future task.

## 7. Explicit non-goals

- No vectors/embeddings as mechanism (empirical: three-word titles defeat BM25 and embeddings alike; revisit only with entity-owned descriptive text AND a demonstrated held-out recall gap; never as authority).
- Not "entity linking" in the textbook sense — ours is ad-hoc ranked retrieval where nodes are the documents; composites are legitimate returns.
- No ontology changes (P5); no legacy-regex revival (it can never fire on composite slugs; D-90-12 already marks its sunset; **all three** legacy T2 modes retire per P1, v1.4).
- No deterministic machinery of any kind (v1.4 R1 + v1.5 ruling) — the exact/alias resolver has no role: not substitution, annotation, or comparator; its output is never surfaced.
- No text2cypher in v1 (its home is the NL/human surface, later).
- No smuggling of the parked #83–#87 metacognition tier.

## 8. Next steps

1. Panel concurrence on spec v0.3 + vision v1.4 (Joseph's R1–R3 rulings folded), then Joseph's re-ratification.
2. On ratification: North Star milestone entry; blueprint phase — package boundary + selector model (P9), determinism plumbing (search artifacts), fixture layout under `benchmark/truth/` (**first work item**, spec §8.1), FTS infrastructure track, T2Mode retirement mechanics (all three modes), exact serialized token counts + the SD-5 threshold value.
3. Implementation plan with #122 metrics as the downstream judge. No implementation until the P7 truth-set definition and the blueprint's TDD plan are complete (codex's gate, adopted) — and no labeling until the §8.1 fixture + restoration smoke test land (R3 sequence).

## Changelog

- **v1.5 (2026-07-25)** — concurrence absorptions (spec v0.4 companions): §3 stale "one batched call" → one graph_search invocation (two selector calls, R4); P1 retain-all made controller-enforced for `N ≤ M` (codex #3 — equal-to-single-fat true by construction); P1 fallback rationale record-corrected per opus5 §1.1 (strictly-below-status-quo failure accepted deliberately — measurement integrity + one T2 architecture); reduced-M gate protocol referenced (spec §8.3); §6 sizing ref bumped to spec v0.4. codex concurrence #5 (stale-language cleanup) closed. **Joseph's post-concurrence ruling (2026-07-25): the deterministic exact/alias method is not a valid search method — its output is never surfaced anywhere** (no fallback, no per-hit annotations, no exact_matchable delta, no would-have-recovered telemetry); supersedes opus5's §2.1/§D.2 instrumentation role; the resolver's role drops to zero (§3 provenance, P1, §7).
- **v1.4 (2026-07-25)** — **Joseph's R1 ruling**: per-entry validation & salvage replaces whole-response fail-closed (a parseable response is never discarded — Joseph's 6-of-10 rule; spec §2.3); the deterministic exact/alias **fallback is removed** (opus5's A1 superseded) — on selector failure the controller retries (bounded, model-correctable classes), then returns honest empty + typed telemetry; **all three legacy T2Modes retire** (`STRUCTURED` no longer survives as fallback); the deterministic resolver survives only as evaluation instrumentation (exact_matchable annotations + truth-harness class-B baseline). Compensating controls: per-entry closed-world validation (D9 output invariant), per-class attempted-violation telemetry + valid_entry_yield → leaderboard, selector-failure-rate hard gate, escaped-foreign-identity = 0 hard gate. Invariant 4, §3 output provenance, P1, P8, §6, §7 updated. R2/R3 recorded in spec v0.3 §7.2/§8.1 and folded here in P1/P6/P7. **R4 (Joseph, 2026-07-25): always two-stage** — thin call then fat call, every source, every run; the v1.3 threshold-activated staging is replaced by one uniform path (Joseph's uniformity principle, same as R2); non-binding at today's scale (51 < M=150 ⇒ result-identical to single-fat); SD-5's routing threshold dissolved into the R2 guardrail; stage-1 recall@150 gate now guards the only path. P1, §6 diagram + sizing updated.
- **v1.3 (2026-07-25)** — P1 scale amendment from spec SD-4 (Joseph's option-2 ruling): single batched call governs under the measured threshold; two-stage all-LLM (thin pre-selection → fat selection) at scale; stage-1 recall@150 predeclared as a truth-set gate run before vault ingestion; FTS candidate generation excluded from v1 (returns only via the gate's revisit). §6 sizing constants corrected from measured snapshot data; §6 diagram, P4 scale-path note, §5.3 status scoping, P6/P7 fixture + artifact precision updated.
- **v1.2 (2026-07-25)** — panel vision reviews folded. opus5: A1 deterministic degraded-mode fallback + A2 T2Mode disposition (P1); B1 persisted search artifact (P6); B2 vault-scale sizing (§6); C1 who-hydrates settled (§3); C2 Source-level wording (§2); C3 cross-domain A/B cohort (P7). codex: F1 artifact-not-hash (P6); F2 untrusted-evidence principle (new P10); F3 SearchSnapshot definition + truth set targets it (§5.2, P7); F4 FTS-over-thin-identities ordering (P4, §6); F5 `complete|partial` evidence status (§5.3); F6 selection provenance annotations (§3); F7 missing-domain rule (§3, **proposed for Joseph's ruling**).
- **v1.1 (2026-07-25)** — Joseph's v1.0 read-notes folded: [2]/[6]/[7] subtree-as-input; caller-side gate; [3] consumer identity dropped; [5] Python telemetry; [9] wholesale pass-1 metadata prompt; [10.1] batched call, fast path dissolved (later restored as failure-fallback in v1.2; removed again in v1.4); [10.2] single "search space" term; [1] naming rationale.
- **v1.0 (2026-07-25)** — initial vision: D1–D9 principles, D10 fat-text authority proposal.

---

*Open items carried into concurrence: spec v0.3 + vision v1.4 as a whole (Joseph's R1–R3 rulings). Everything else herein is ruled (D1–D10), panel-concurred, or panel-reviewed and folded.*

# #123 Round 1 — Synthesis

Date: 2026-07-25 · Inputs: packet + three respondent records (`-codex`, `-opus5`, `-kimi`) · Status: **D1–D8 ruled by Joseph 2026-07-25 (§7)** — submitted to the panel for concurrence before the vision doc.

## 1. Evidence checks run before absorbing (Kimi)

- **opus5 §0 (domain gate zeroes the pool)** — VERIFIED exactly: pool==0 on 10/28 (deepseek), 10/28 (gpt), 10/29 (gemini) of the 2026-07-25 cold-run context records; 0/2 on the warm run. The gate starves ~35% of sources, including any first-source-in-domain regardless of graph richness.
- **Fat-index fuel exists** — VERIFIED: `Source.summary STRING` is in the graph schema (`kdb_graph/schema.py:91`, v2.3 D-89-17).
- **FTS entirely unused** — VERIFIED: word-boundary grep for fts/bm25/full-text over all Python source = zero hits; Kuzu 0.11.3 ships the extension, never installed here.

## 2. Joseph's rulings during the round (binding on everything below)

1. **Identity = return type; relevance = selection criterion.** "We need GraphDB identities that are relevant to the search entry." There is no identity-vs-relevance fork. (opus5: "the single most consequential resolution of the round, upstream of every mechanism choice.")
2. **Keys are text.** One function over arbitrary query text; pass-1 keys become an *optional* input, not the required interface. Length and top-k are parameters, not architectures.
3. **The read-side/write-side framing is rejected.** Composites are legitimate returns — `buffett-balance-sheet-rules` is a *correct* answer for `warren-buffett`, not a substitute. Referent absence stops being fatal; write-side ontology drops from prerequisite to future optimization.
4. **Cost is not a constraint at this stage.** "Building that intelligent entity into existence at any expense is the only goal right now." (Unlocks fat candidate text.)
5. **Measurement is deferred until the function exists** — but see §3-G: what a *wrong answer* is must still be defined in the spec, before tuning.
6. **FTS at the get-go** as foundation for future expansion (integrate-early instinct; scoped in §5-D4).

## 3. Convergence map

### 3/3 unanimous (codex · opus5 · kimi)

- **A. The missing object is the intelligence layer itself.** Exact-slug equality is a lookup primitive, not search. No mechanism debate precedes this fact.
- **B. Mechanism: LLM semantic selection over the compact index, batched one call per source, is sound at current N** and is the stop-gap *and* the end-state — scale changes only candidate generation, never the contract. (Codex: "smallest end-to-end implementation of the final contract." opus5: "this *is* the long-term architecture at this N.")
- **C. My i1-FTS→i2-LLM sequencing is rejected (2–1, I concede).** FTS does not satisfy the capability; ship the LLM selector first, add FTS when a measured scaling/cost threshold demands pre-filtering. FTS solves an observed problem later, not an anticipated one now.
- **D. Domain stops being a hard gate.** Codex: prior-with-global-fallback (constraint/prior/shard are three different semantics). opus5: prior in the prompt + record out-of-domain returns. Evidence (§1) is decisive. I accept.
- **E. Graph-authoritative, fail-closed, read-only.** Output = existing active canonical entities only; LLM-selected slugs outside the candidate set are contract failures, never repaired by similarity; the selector never writes graph, wiki, or frontmatter (the #119 line holds).
- **F. Vectors excluded from v1** — and the precise reason is empirical, not principled: three-word titles defeat embeddings *and* BM25 alike (opus5). Codex: reconsider only if entity-owned descriptive text exists AND a held-out recall gap is demonstrated; never as authority.
- **G. "Define the wrong answer" before tuning** (the #75 pattern). Codex: held-out truth set before implementation; relevance can't be proven by #122 metrics alone (a hub-returner looks like improvement). opus5: the objective as stated cannot fail — every node is related by some path — so the spec's load-bearing task is defining wrong answers in advance. Same catch from different doors.
- **H. T3 unchanged.** Structural `LINKS_TO` BFS is the purest use of the graph as a graph; its problem was empty T2 input, which the warm run already measured (0 → 22 pages/source). No FTS at T3.
- **I. Not "entity linking."** Both panelists independently rejected the textbook frame: it assumes a KB entry per mention (NIL on absence) and imports an identity-eval regime that would score our intended behavior as error. Ours is **ad-hoc ranked retrieval where nodes are the documents**. (I coined the mapping in my packet; I accept the correction — the name would have bent the evaluation.)
- **J. The legacy regex layer is not a floor worth keeping.** `_t2_slug_in_text` matches whole slugs literally — `buffett-balance-sheet-rules` can never fire; `_t2_title_in_text` needs verbatim title phrases. STRUCTURED ≥ LEGACY already on record (NW-9), D-90-12 already marks the sunset. Exact/alias stays as zero-cost fast path; the regex does not come with us.

### Partial / narrowed

- **K. Candidate text: fat vs thin.** opus5: fat (summary/body excerpts) — the thin index existed only for budget reasons that ruling §2.4 removed. Codex: thin-but-bounded, and warns selection may draw on the model's *parametric* knowledge rather than graph evidence — evaluate against fixed snapshot + truth, never assume grounding. Synthesis: fat, with codex's caveat carried into the evaluation design (it is a measurement requirement, not a blocker).
- **L. FTS early as infrastructure** (opus5, absorbing Joseph's integrate-early): adopt FTS as a *capability* with the **CLI/MCP human query surface as first genuine consumer**, never as the T2/T3 mechanism. Flushes install/pinning/refresh-policy risk while nothing depends on it. Codex neutral-to-later. → decision D4 below.
- **M. T2 ranking.** opus5: use the LLM's ordering inside T2 (PageRank is a global popularity prior that promotes hubs over precise matches); keep tier-then-PageRank for T1/T3. Codex: ranking semantics must be explicit, no prescription. → folded into D2.

### Unique catches (1/n, worth surfacing)

- **N. Determinism break (opus5).** An LLM in the context path makes same-(source, graph) yield different context run-to-run: #119's golden-fixture byte-pinning and replay stop reproducing. Mitigation is cheap and has an obvious home: **persist the selected slugs on the #122 context record; replay reads the record instead of re-calling.** Stochastic choice, reproducible run. Load-bearing — adopt.
- **O. Package boundary (codex).** New top-level `kdb_search` (imported by compiler + kdb_mcp, imports common + kdb_graph, zero product-state writes; requires AST-boundary update) vs `kdb_graph.search` with an injected selector callable (no new package, preserves sibling-free rule, but every consumer composes the model port). Codex asks the blueprint to compare against the §6 JOURNEY second-consumer lesson. → deferred to blueprint, recorded here.
- **P. Options A/B/C (codex).** A: query-side over existing graph (lowest cost, reversible, compensates forever). B: write-side subject ontology (meaning compounds in the asset; changes what the graph is; not a stop-gap). C: transitional — A now, persist auditable correspondence telemetry only, later ratified promotion into aliases/subjects (must not smuggle #83–#87's parked tier into #123). Codex recommends A + C-telemetry; B an explicit future decision. Joseph's ruling §2.3 already rejected B-as-prerequisite. → D5.

## 4. Where Kimi's position moved

- i1/i2 sequencing — **conceded** (2–1; FTS solves no current problem, the selector is the capability).
- "Entity linking" as the name — **conceded** (imports the wrong evaluation regime).
- Domain gate as shipped-good — **conceded** (the 35% evidence is decisive; the gate I cited as a system fact was actively starving a third of sources).
- "Exact match stays as floor" — **refined**: exact/alias fast path yes; legacy regex no (§3-J).
- Fat index and pass-1-summary-as-input — **adopted** from opus5 (keys are a lossy compression; the summary restores what they discarded at no extra call).

## 5. Decisions for Joseph (D-123 candidates)

- **D1. Mechanism**: a distinct LLM relevance pass between pass-1 and context-build. Input: pass-1 summary + keys (keys optional), domain as prompt prior, candidate index (fat text). Output: ordered active canonical slugs, structured JSON, controller-validated, persisted on the #122 context record. Never writes graph/wiki/frontmatter. T2 seeds come from this pass; T3 structural BFS unchanged; T1 unchanged.
- **D2. Ranking**: LLM ordering inside T2; tier-then-PageRank retained for T1/T3 only.
- **D3. Domain semantics**: hard gate removed; prior-with-global-fallback; out-of-domain returns recorded on the context record (the cross-domain evidence the 2026-07-07 probe couldn't produce).
- **D4. FTS**: adopt early as infrastructure, first genuine consumer = CLI/MCP human query surface; never the T2/T3 mechanism; refresh/install/pinning policy designed in the blueprint.
- **D5. Scope**: #123 is permanently read-only (Option A + C-telemetry). Write-side subject ontology (Option B) is a separate future task; nothing in #123 mutates the ontology. Promotion of observed correspondences requires its own later ratification and must not touch the parked #83–#87 tier.
- **D6. Determinism**: selected slugs persisted on the #122 context record; replay reads the record, never re-calls (opus5's mitigation; protects #119 byte-pinning).
- **D7. Evaluation**: spec phase must define what a wrong answer is (held-out truth set over a fixed graph snapshot; candidate-recall vs selector-precision reported separately; hub-returner adversarial case; abstention correctness) BEFORE any tuning — #75 pattern. Numerical gates set only after the probe set exists.
- **D8. Package boundary**: deferred to blueprint — `kdb_search` vs `kdb_graph.search`+injected selector, compared against the JOURNEY §6 second-consumer lesson.

## 6. Deferred to later rounds

- Success criteria numbers (after the truth set exists, per D7).
- The scale threshold that switches whole-index → prefiltered selection (measured, not guessed).
- Option B (write-side subject ontology) as its own future task discussion.

## 7. Joseph's rulings on D1–D8 (2026-07-25) + resolutions

- **D1 — RATIFIED, with naming.** Capability = **graph search** (one function over arbitrary query text → ordered graph entities). Pipeline stage = **pass-1.5** (Joseph's coinage): pass-1 enrich → pass-1.5 graph search → pass-2 compile. The graphDB is the function's implicit input (the active-entity search space, read at call time).
- **D2 — RATIFIED**: LLM ordering inside T2, and the ordering must be reflected in the pass-2 prompt's EXISTING CONTEXT presentation (spec-phase detail).
- **D3 — RATIFIED (Joseph's final ruling)**: for **context-build the domain gate is always on — no global fallback.** Domain scoping is the very definition of "context" in context-build; out-of-domain results would be "out-of-context + build." The 10/28 cold-start starvation is accepted as reality ("that's what things are"), **not** the defect being fixed. The defect is empty T2 for keys like `warren-buffett` whose domain pool is *rich* (value-investing at 29–46 entities incl. Buffett composites) while exact-match returns nothing — the intelligence gap, not scope width. Reconciliation with opus5's §0 warning, for the evaluation record: **abstention on domain-empty sources is correct-by-design and must never be scored as selector failure.** For other consumers (ad-hoc human search — "something I can't remember exactly"), the domain gate is an optional query input, default off.
- **D4 — RATIFIED**: FTS adopted early as infrastructure. First genuine consumer = CLI/MCP human query surface. Joseph asked about FTS for T1/T3/domain-subtrees — resolved: all three are structural lookups/traversals (SUPPORTS, LINKS_TO BFS, BELONGS_TO) where text indexing adds nothing; FTS homes are the human surface and at-scale candidate generation only.
- **D5 — RATIFIED as guardrail**: #123 read-only — the selector never writes graph/wiki/frontmatter; write-side ontology work (person nodes, auto-alias) is a separate future task.
- **D6 — RATIFIED, scoped to T2**: T1/T3 are deterministic functions of graph state; only the LLM selection is stochastic, and it feeds only T2. Persist the T2 selected slugs **and their order** on the #122 context record; replay reads the record, never re-calls.
- **D7 — RATIFIED**: T2 returns must exist in the graphDB — enforced structurally: the LLM **selects from a supplied candidate set** (closed world); validation = candidate-set membership (fail-closed on any foreign slug) + live-graph re-verify (active, canonical) + shape checks (ordered, capped, deduplicated). FTS is a candidate generator, not an authority — it plays no validation role. The graph is the only validator.
- **D8 — blueprint stage**: package boundary (`kdb_search` vs `kdb_graph.search`+injected selector) AND selector model choice both deferred to blueprint.

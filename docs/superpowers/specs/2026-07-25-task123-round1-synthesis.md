# #123 Round 1 — Synthesis

Date: 2026-07-25 · Inputs: packet + three respondent records (`-codex`, `-opus5`, `-kimi`) · Status: **D1–D9 ruled by Joseph 2026-07-25 (§7)** · **Panel concurrence: APPROVE ×2 (opus5, codex) with fixes absorbed (§8)** — basis for the vision doc.

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
6. **FTS at the get-go** as foundation for future expansion (integrate-early instinct; scoped in §7-D4).

## 3. Convergence map

### 3/3 unanimous (codex · opus5 · kimi)

- **A. The missing object is the intelligence layer itself.** Exact-slug equality is a lookup primitive, not search. No mechanism debate precedes this fact.
- **B. Mechanism: LLM semantic selection over the compact index, batched one call per source, is sound at current N** and is the stop-gap *and* the end-state — scale changes only candidate generation, never the contract. (Codex: "smallest end-to-end implementation of the final contract." opus5: "this *is* the long-term architecture at this N.")
- **C. My i1-FTS→i2-LLM sequencing is rejected (2–1, I concede).** FTS does not satisfy the capability; ship the LLM selector first, add FTS when a measured scaling/cost threshold demands pre-filtering. FTS solves an observed problem later, not an anticipated one now.
- **D. ~~Domain stops being a hard gate.~~** *(Recorded as 3/3 unanimous during the round — codex: prior-with-global-fallback; opus5: prior + record out-of-domain; kimi accepted. **SUPERSEDED 2026-07-25 by Joseph's §7-D3 override**: the gate stays always-on for context-build. Kept visible here per the project convention that n/n findings may be overridden but not silently.)*
- **E. Graph-authoritative, fail-closed, read-only.** Output = existing active canonical entities only; LLM-selected slugs outside the candidate set are contract failures, never repaired by similarity; the selector never writes graph, wiki, or frontmatter (the #119 line holds).
- **F. Vectors excluded from v1** — and the precise reason is empirical, not principled: three-word titles defeat embeddings *and* BM25 alike (opus5). Codex: reconsider only if entity-owned descriptive text exists AND a held-out recall gap is demonstrated; never as authority.
- **G. "Define the wrong answer" before tuning** (the #75 pattern). Codex: held-out truth set before implementation; relevance can't be proven by #122 metrics alone (a hub-returner looks like improvement). opus5: the objective as stated cannot fail — every node is related by some path — so the spec's load-bearing task is defining wrong answers in advance. Same catch from different doors. **Ruled at §7-D7.**
- **H. T3 unchanged.** Structural `LINKS_TO` BFS is the purest use of the graph as a graph; its problem was empty T2 input, which the warm run already measured (0 → 22 pages/source). No FTS at T3.
- **I. Not "entity linking."** Both panelists independently rejected the textbook frame: it assumes a KB entry per mention (NIL on absence) and imports an identity-eval regime that would score our intended behavior as error. Ours is **ad-hoc ranked retrieval where nodes are the documents**. (I coined the mapping in my packet; I accept the correction — the name would have bent the evaluation.)
- **J. The legacy regex layer is not a floor worth keeping.** `_t2_slug_in_text` matches whole slugs literally — `buffett-balance-sheet-rules` can never fire; `_t2_title_in_text` needs verbatim title phrases. STRUCTURED ≥ LEGACY already on record (NW-9), D-90-12 already marks the sunset. Exact/alias stays as zero-cost fast path; the regex does not come with us.

### Partial / narrowed

- **K. Candidate text: fat vs thin.** opus5: fat (summary/body excerpts) — the thin index existed only for budget reasons that ruling §2.4 removed. Codex: thin-but-bounded, and warns selection may draw on the model's *parametric* knowledge rather than graph evidence — evaluate against fixed snapshot + truth, never assume grounding. Synthesis: fat, with codex's caveat carried into the evaluation design (it is a measurement requirement, not a blocker). **Authority question recorded at §8.**
- **L. FTS early as infrastructure** (opus5, absorbing Joseph's integrate-early): adopt FTS as a *capability* with the **CLI/MCP human query surface as first genuine consumer**, never as the T2/T3 mechanism. Flushes install/pinning/refresh-policy risk while nothing depends on it. Codex neutral-to-later. → ruled §7-D4, wording refined at §8.
- **M. T2 ranking.** opus5: use the LLM's ordering inside T2 (PageRank is a global popularity prior that promotes hubs over precise matches); keep tier-then-PageRank for T1/T3. Codex: ranking semantics must be explicit, no prescription. → ruled §7-D2.

### Unique catches (1/n, worth surfacing)

- **N. Determinism break (opus5).** An LLM in the context path makes same-(source, graph) yield different context run-to-run: #119's golden-fixture byte-pinning and replay stop reproducing. Mitigation: persist the selection on the #122 context record; replay reads the record. **Ruled §7-D6, extended at §8.**
- **O. Package boundary (codex).** New top-level `kdb_search` (imported by compiler + kdb_mcp, imports common + kdb_graph, zero product-state writes; requires AST-boundary update) vs `kdb_graph.search` with an injected selector callable (no new package, preserves sibling-free rule, but every consumer composes the model port). Codex asks the blueprint to compare against the §6 JOURNEY second-consumer lesson. → deferred to blueprint (§7-D8).
- **P. Options A/B/C (codex).** A: query-side over existing graph (lowest cost, reversible, compensates forever). B: write-side subject ontology (meaning compounds in the asset; changes what the graph is; not a stop-gap). C: transitional — A now, persist auditable correspondence telemetry only, later ratified promotion into aliases/subjects (must not smuggle #83–#87's parked tier into #123). Codex recommends A + C-telemetry; B an explicit future decision. Joseph's ruling §2.3 already rejected B-as-prerequisite. → ruled §7-D5.

## 4. Where Kimi's position moved

- i1/i2 sequencing — **conceded** (2–1; FTS solves no current problem, the selector is the capability).
- "Entity linking" as the name — **conceded** (imports the wrong evaluation regime).
- Domain gate as shipped-good — **conceded to evidence, then overridden by Joseph** (§7-D3; his final ruling governs).
- "Exact match stays as floor" — **refined**: exact/alias fast path yes; legacy regex no (§3-J).
- Fat index and pass-1-summary-as-input — **adopted** from opus5 (keys are a lossy compression; the summary restores what they discarded at no extra call).

## 5. Decisions ruled by Joseph (2026-07-25)

(D1–D8 proposed as candidates; Joseph ruled on each; D9 added during concurrence review — see §7 for final texts and §8 for the concurrence record.)

## 6. Deferred to later rounds

- Success criteria numbers (after the truth set exists, per §7-D7).
- The scale threshold that switches whole-index → prefiltered selection (measured, not guessed).
- Option B (write-side subject ontology) as its own future task discussion.
- **Fat-text authority decision** (§8, codex carry-forward 6): whether candidate fat text comes solely from graph-resident `Source.summary` or also from wiki bodies — the vision doc must state authority, deterministic projection, bounds, and snapshot identity.
- **Cross-domain telemetry cohort** (§8, opus5 recommendation 3): one cohort, selector run twice (domain-scoped + global), delta recorded as telemetry — evaluation-phase work.

## 7. Joseph's rulings on D1–D9 (2026-07-25) + resolutions

- **D1 — RATIFIED, with naming.** Capability = **graph search** (one function over arbitrary query text → ordered graph entities). Pipeline stage = **pass-1.5** (Joseph's coinage): pass-1 enrich → pass-1.5 graph search → pass-2 compile. The graphDB is the function's implicit input (the active-entity search space, read at call time). *(Codex carry-forward 1: graph search is the general capability; pass-1.5 is its first integration adapter — pass-1 summaries, keys, and the mandatory domain scope belong to the adapter, not to the consumer-neutral contract.)*
- **D2 — RATIFIED**: LLM ordering inside T2, and the ordering must be reflected in the pass-2 prompt's EXISTING CONTEXT presentation (spec-phase detail).
- **D3 — RULED BY JOSEPH AS AN OVERRIDE of the 3/3 unanimous finding §3-D** *(labeled per the convention that n/n findings may be overridden, not silently)*: for **context-build the domain gate is always on — no global fallback.** Domain scoping is the very definition of "context" in context-build; out-of-domain results would be "out-of-context + build." The 10/28 cold-start starvation is accepted as reality ("that's what things are"), **not** the defect being fixed. The defect is empty T2 for keys like `warren-buffett` whose domain pool is *rich* (value-investing at 29–46 entities incl. Buffett composites) while exact-match returns nothing — the intelligence gap, not scope width. **Consequences recorded:** (a) abstention on domain-empty sources is **correct-by-design and must never be scored as selector failure** (reconciles opus5's §0 warning); (b) the all-request domain-empty rate **must remain visible as an end-to-end system outcome** in reporting, so the accepted starvation never disappears from view (codex carry-forward 2); (c) opus5's substance concurrence is on record — the motivating failure sits in the richest bucket, the intelligence gap is the defect, starvation is not — plus his note that the starvation is largely a **small-corpus artifact** (6 of 10 starved domains held exactly one source in this 36-source corpus; at vault scale the effect shrinks without intervention). For other consumers (ad-hoc human search — "something I can't remember exactly"), the domain gate is an optional query input, default off.
- **D4 — RATIFIED**: FTS adopted early as infrastructure. First genuine consumer = CLI/MCP human query surface. FTS for T1/T3/domain-subtrees — resolved: all three are structural (SUPPORTS, LINKS_TO BFS, BELONGS_TO) where text indexing adds nothing. *(Codex carry-forward 5, wording adopted: FTS is never relevance authority nor T3 machinery; at scale it **may** generate bounded T2 candidates through graph search when prefiltering becomes necessary.)*
- **D5 — RATIFIED as guardrail**: #123 read-only — the selector never writes graph/wiki/frontmatter (the #119 line); write-side ontology work (person nodes, auto-alias) is a separate future task.
- **D6 — RATIFIED, scoped to T2, with two extensions (§8)**: T1/T3 are deterministic functions of graph state; only the LLM selection is stochastic, and it feeds only T2. Persist the T2 selected slugs **and their order** on the #122 context record. **Extension 1 (opus5 rec 4):** replay-from-record by default for reproduction; **explicit opt-in re-call** for selector evaluation — otherwise a changed selector can never be exercised against recorded runs. **Extension 2 (codex carry-forward 3):** the persisted payload includes the selector **model, route, prompt version/hash, query, and candidate-snapshot hash** alongside the slugs — slugs alone reproduce output but cannot audit the decision or prove what candidate population the selector saw.
- **D7 — RATIFIED (evaluation)**: the spec phase must **define what a wrong answer is** before any tuning — held-out truth set over a fixed graph snapshot; candidate-recall vs selector-precision reported separately; hub-returner adversarial case; abstention correctness (incl. domain-empty abstention scored correct, per D3); #75 pattern. Numerical gates set only after the probe set exists. Measurement of the live system stays deferred until the function exists (§2.5). *(Renumbered at concurrence: Joseph's D7 answer addressed **validation** — that content is now D9. opus5 must-fix 1 + codex carry-forward 4: identity validation and relevance evaluation are different decisions and are now ruled separately.)*
- **D8 — blueprint stage**: package boundary (`kdb_search` vs `kdb_graph.search`+injected selector) AND selector model choice both deferred to blueprint.
- **D9 — RATIFIED (validation, split from D7 at concurrence)**: T2 returns must exist in the graphDB — enforced structurally: the LLM **selects from a supplied candidate set** (closed world); validation = candidate-set membership (fail-closed on any foreign slug) + live-graph re-verify (active, canonical) + shape checks (ordered, capped, deduplicated). FTS is a candidate generator, not an authority — it plays no validation role. **Kuzu is the runtime identity authority; the held-out truth set (D7) is the relevance authority.** Candidate membership proves an identity is eligible, active, canonical — it does not prove semantic relevance (codex carry-forward 4).

## 8. Panel concurrence record (2026-07-25)

Both respondents reviewed this synthesis and voted **APPROVE**:

- **opus5 — APPROVE** (`2026-07-25-task123-round1-synthesis-review-opus5.md`), two must-fixes, both absorbed here: (1) D7 numbering collision — §5-D7 asked about evaluation, §7-D7 answered validation; fixed by the D7/D9 split. (2) D3 silently inverted a 3/3 finding; fixed by the explicit OVERRIDE label and the §3-D superseded annotation. On substance he records D3 as **right**: the motivating failure sits in the richest domain bucket; "abstention on domain-empty sources is correct-by-design" closes his §0 misdiagnosis risk. Non-blocking recommendations absorbed: cross-domain telemetry cohort (deferred to evaluation phase, §6); D6 re-call escape hatch (absorbed into §7-D6).
- **codex — APPROVE** (`2026-07-25-task123-round1-synthesis-review-codex.md`), six carry-forwards: (1) capability generality — pass-1.5 is an adapter, not the interface (absorbed into §7-D1); (2) preserve both domain-scope denominators (absorbed into §7-D3); (3) auditable replay payload (absorbed into §7-D6); (4) separate identity validation from relevance evaluation (absorbed as the D7/D9 split); (5) FTS–T2 relationship wording (absorbed into §7-D4); (6) fat-text authority must be defined — graph-resident `Source.summary` only, or wiki bodies too; authority, projection, bounds, snapshot identity explicit (deferred to the vision doc, §6).

No outstanding dissents. The vision doc may proceed on this basis.

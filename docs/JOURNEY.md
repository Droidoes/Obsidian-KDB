# The Journey — From Static Top-50 to Live Ontology Authority

**Retrospective, written 2026-05-22.** Captures the path from project inception
(2026-04-18 M0) through the loop-closure day (2026-05-17) and the post-closure
arc to today. Not architecture spec (see `CODEBASE_OVERVIEW.md`), not roadmap
(see `TASKS.md`). This is the **why we walked this way**, in three iterations,
honest about what worked and what didn't.

---

## The numbers (snapshot 2026-05-22)

| Metric | Value |
|---|---|
| Calendar span | 2026-04-18 (M0 first real work) → 2026-05-22 — ~5 weeks of intense work |
| Active commit days | 20 |
| Total commits | 288 |
| Tasks in ledger | 67 top-level rows (more with sub-task decomposition, e.g. `#76.1..#76.6`) |
| API spend (user-reported) | ~$300 USD, primarily Opus 4.7 |
| Iterations | 3 distinct architectural arcs |
| External reviewers added | Codex (since ~Iter 1), Gemini (Iter 3) |

---

## Iteration #1 — Compiler & 3-attribute wiki

**Span:** 2026-04-18 → 2026-05-09 (M0 through Round 5)
**Substrate:** `manifest.json` as the connection store + static-Python top-50 selection.

### Goal

Build a KDB compiler that produces a 3-attribute wiki graph from raw sources, with auditable per-source compile results.

### What we built

- **`kdb_compiler/`** pipeline: `kdb-scan` → `kdb-plan` → `kdb-compile` → `patch_applier`. (`kdb-clean` came later in Iter #3, Task #67 — see §3.)
- **Per-source-page schema** with the 3-attribute wiki link (settled in Task #4, see `docs/task4-parallel-draft-prompt.md`).
- **Model ranking system** (`kdb-benchmark`): per-model latency / cost / quality benchmarking across providers.
- **Validator + reconciler** infrastructure: catch the `pairing_omission` defect class *before* `patch_applier` writes (Task #65). Live-vault-proven 2026-04-21 (two back-to-back runs each tripped the defect, validating the auto-heal layer).
- **M1–M5 quality metrics framework** (Task #19): pre-declared KPIs landed in `CODEBASE_OVERVIEW §7`.
- **Response replay** (`kdb-replay`): per-response stats + replay-without-LLM-call. Underwrites the verifier's structural-equality diff (D39).
- **JSON-schema gate** on every LLM response — no unstructured strings touch downstream code.

### The irony we recognized at the end of Iter #1

The compiler computes "existing connections (top 50)" via **static Python over `manifest.json`** — a flat key/value index — at the very moment the project's stated purpose was to **build an ontology** that ought to be the thing producing those connections. We were building the destination using tools that contradicted it.

### What worked (durable; still in use today)

- Model ranking system. Still authoritative.
- 3-attribute wiki schema + prompt structure. Settled, no churn since.
- Validator + reconciler. Still load-bearing 2 iterations later.
- M1–M5 framework. Still load-bearing (M5 reinterpreted by Task #59, but the framework survived).

### What didn't work (or shouldn't have been the substrate)

- `manifest.json`-as-connection-store was the wrong substrate for ontology. We knew it during Iter #1 (see "the irony" above). We shipped it anyway because GraphDB didn't exist yet. This was correct sequencing, but the framing — that manifest was a "stripped-down graph" — was wrong; it was a flat index pretending to be a graph.

---

## Iteration #2 — Kuzu GraphDB refoundation

**Span:** ~2026-05-10 → 2026-05-16 (Task #63 refoundation per memory `project_graphdb_kdb_refoundation`)
**Decision point:** Kuzu embedded GraphDB becomes the architectural primitive; KDB reframed as raw-text → knowledge-graph compiler.

### Goal

Build the actual GraphDB so that — eventually — the ontology could displace `manifest`-derived static-top-50 at compile time.

### What we built

- **GraphDB-KDB** (Kuzu embedded): schema v2 (`Entity` / `LINKS_TO` / `SUPPORTS`).
- **Ingest pipeline:** `kdb-compile` writes via `ObsidianRunsAdapter.sync_current_run(...)` at Stage 10.
- **Verifier** (`graphdb-kdb verify`): replay-to-temp structural-equality diff (D50 Phase G) with three layers — source-state preflight, replay structural diff, canonicalization invariants.
- **Snapshot** (`graphdb-kdb snapshot`): belt-and-suspenders JSONL + manifest backup (D35).
- **Rebuilder** (`graphdb-kdb rebuild`): deterministic regeneration from run-journal sidecars (D39).
- **CLI:** `graphdb-kdb` with `init` / `stats` / `neighbors` / `incoming` / `path` / `cypher` / `pagerank` / `communities` / `structural-holes` / `orphans` / `subgraph-by-source` / `verify` / `rebuild` / `snapshot` subcommands at Iter #2 close. (`domains` came later in Iter #3 via Task #76.4; ingestion is invoked implicitly by `kdb-compile` Stage 9/10 `graph_sync`, not as its own subcommand.)
- **Physical separation (D35):** Kuzu data directory lives at `~/Droidoes/GraphDB-KDB/` (sibling to `Obsidian-KDB/`, *not* OneDrive-synced — avoids binary-file corruption on the catalog files).

### What didn't work yet at the end of Iter #2

**The loop wasn't closed.** We had a working GraphDB on one side and a `kdb_compiler` still calling static-Python top-50 over `manifest.json` on the other. The end-of-Iter-2 conversation was: *"OK Opus, can we replace static-top-50 with GraphDB?"* — and the model said *"no, we don't have enough files."*

In hindsight, that deflection was wrong-shaped. The right framing was: **compiler integration is a distinct workstream that needs its own blueprint and task.** The integration itself became Task #70 / #70.1 (`graph_context_loader`) in Iter #3 on 2026-05-16 — that's what actually closed the loop. Task #75 (predeclared eval criteria for step-3 ops) came later, defining the *evaluation contract* for query-time graph operations on top of the now-live ontology.

### The friction the user named, called out honestly

The user spent significant tokens in Iter #2 pushing for **manifest deconstruction + static-top-50 replacement**. The model deflected verbally rather than filing a blueprint. Both positions were partially right:
- The user was right that manifest had to go (proven in Iter #3 — D50).
- The model was right that the replacement needed empirical justification on cold-start density (proven in Iter #3 — Task #71).

The cost of doing the right thing the wrong way: a multi-iteration delay where a verbally-stalled disagreement could have been a filed-and-executed blueprint. **Pattern lesson:** disagreement should be *filed*, not *voiced*. Filing converts the dispute into reviewable artifact + a path forward. (See [Lessons](#lessons) §1.)

---

## Iteration #3 — Loop closure + step-3 ops

**Span:** 2026-05-17 → today (2026-05-22). Active arc.
**Initial framing:** "Add more sources, build ingestion pipeline."
**Mid-iteration revision:** "Close the manifest-as-context → graph-as-context loop first, *then* build step-3 ops on top of the live ontology."

### The philosophy doc (early Iter #3)

Before code, the project paused for a Philosophy A vs B discussion captured in `docs/what-is-the-ontology-for.md`:
- **Philosophy A** (Opus + Codex initial position): human curation and control are necessary for an efficient, lasting GraphDB.
- **Philosophy B** (user position): trust the LLM to do the magic; minimize human curation overhead.

Converged on **B + (C1) + (C2)** per memory `project_ontology_purpose_kernel_question` (CLOSED 2026-05-20). The convergence path likely owed something to LLM accommodation bias — worth surfacing as a pattern (see [Lessons](#lessons) §4) — but the design call was sound regardless.

### **2026-05-17 — Loop-closure day**

Three decisions landed the same day, closing the manifest → GraphDB substitution that Iter #2 left open:

| Decision | Task | What it did |
|---|---|---|
| **D49** | #70 closure | **GraphDB is the *only* supported `EXISTING_CONTEXT` authority.** `manifest.json` must not be used for context generation. `KDB_CONTEXT_SOURCE` env var removed. Planner always calls `graph_context_loader`. If GraphDB is missing/corrupt, context planning fails loud → operator runs `graphdb-kdb rebuild`. |
| **D50** | #73 | **`manifest.json` is no longer an ontology store.** Pages, `outgoing_links`, `source_refs`, orphan status stripped together (no piecemeal). Manifest becomes source-file metadata ledger only — hashes, compile state, timestamps. Stage 9 `graph_sync` becomes *fatal* for non-dry-run compiles (revokes D38 non-fatal semantics for ontology writes). [Stage was renumbered to Stage 10 later when Task #74 inserted canonicalization at Stage 6.] |
| **D51** | #73 closure | **GraphDB is the live ontology authority; `state/runs/` sidecars are reconstruction material, not the primary data flow.** Layer model: `raw/` = source corpus; `GraphDB-KDB/` = live ontology (primary); `state/runs/` = audit log + recovery; `source_state.json` = source-file lifecycle metadata; `wiki/` = markdown rendering. |

**Empirical proof** (Task #71 — cold-start widening, same day): graph context produces **17–23 pages on cold-start** vs. **0–8 from manifest**. The static-top-50 substrate was empirically inferior, not just theoretically.

**This is the moment the loop closed.** The architectural objective the user had been pushing toward since Iter #2 was satisfied on 2026-05-17. Five days ago, as of this writing.

### Post-loop-closure work (the user-perceived "we're still not done")

After the loop closed mid-Iter-3, work continued — but now **on** the live ontology rather than toward it:

- **Task #74** — canonicalization-first blueprint (alias resolution, slug stability).
- **Task #75** — predeclared evaluation criteria for step-3 graph ops. Locks V0/V1/V2 ops roster (V0: typed traversal + shortest-path; V1: PPR + community routing + subgraph extraction; V2: scored multi-hop deferred). Defines per-op pass/fail/gate criteria + hedge-watch rules HW-1..HW-7. Pattern mirrors Task #19 (compile-side KPI predeclaration).
- **Task #76** — Domain field implementation. Adds `Domain` node + `BELONGS_TO` edge (schema v2.1). Critical-path enabler for §4.2 community/domain-ratio acceptance gate + HW-3 hedge.
- **Task #79** — verifier coverage for schema v2.1.
- **Task #80** — snapshot format v3 (Domain + BELONGS_TO).
- **Task #81** — V0 ops regression foundation (typed traversal + shortest-path direct-unit-tested, query-time direction-exclusivity locked, shortest-path runtime guard marked `@pytest.mark.bench`).
- **Gemini** added as second reviewer alongside Codex (with review-only guardrail per memory `feedback_gemini_review_only_guardrail`).

### What's NOT yet built (genuine open path)

- **V1 step-3 ops:** PPR (#78), subgraph extraction (#78b), community routing. Community **primitive** already ships since Iter #2 (`graphdb-kdb communities`, Louvain, Task #63.4) — what's unresolved is the *acceptance/eval integration*, the Leiden vs Louvain choice, and the domain-ratio gate closure (per Task #75 §4.2).
- **Probe-set curation** (#77) — blocks §4.3 "≥95% match" gate. OQ-3 questions (N, curator, when, vault-versioning) pending user decisions.
- **V2 step-3 ops:** scored multi-hop (deferred per Task #75 OQ).

---

## State as of 2026-05-22

### Loop status

**The manifest → GraphDB substitution is done.**

- Compiler calls `graph_context_loader` at runtime (since 2026-05-16, Task #70.1).
- Manifest is file-meta only (since 2026-05-17, D50).
- GraphDB is the live ontology authority (since 2026-05-17, D51).
- Empirical superiority proven on cold-start (since 2026-05-17, Task #71).

The shared session framing — "we still don't know if GraphDB can replace static-top-50" — lagged the code state by about five days. The gap between architectural reality and the in-session mental model is itself a finding (see [Lessons](#lessons) §5).

### What's still in flight

Step-3 graph ops are at **V0 only** (typed traversal + shortest-path, both proven and regression-guarded as of #81). V1 (PPR + subgraph + community routing) is the next forward arc. The compiler **runs end-to-end against the live ontology today**; V1+ work deepens what the ontology can *do* at compile time, not whether the substitution works.

### Open empirical questions (the genuinely unresolved)

| Question | Why it's still open | Blocking task |
|---|---|---|
| Does V0 typed-traversal retrieve the right neighbors on a curated probe set? | No probe set exists yet. | #77 (probe-set curation) |
| Does V1 PPR + subgraph extraction beat V0 on the same probe set? | Predeclared in #75 §4.1; not yet built. | #78 (PPR) + #78b (subgraph) + #77 (probe set) |
| Does community routing (now that Domain nodes exist) meaningfully improve over plain T3 expansion? | Predeclared per #75 §4.2; community routing not yet built. | #78 + #77 + Domain corpus density |
| Is the Iter #1 wiki rendering still aligned with the v2.1 ontology, or does it need a refresh pass? | Not actively measured. One concrete instance: `kdb_compiler/prompt_builder.py:138` still labels the graph-derived context as `EXISTING CONTEXT (manifest snapshot)` — a holdover string from the pre-D49 substrate. | (none filed yet — candidate task; trivial label fix + audit pass) |

---

## Lessons

### §1. Disagreement should be filed, not voiced

The Iter #2 stall (user pushing manifest deconstruction; model deflecting with "we don't have enough files") cost tokens *because the disagreement stayed verbal*. The right move was to file a manifest-deconstruction blueprint immediately as a distinct task, executing the user's request structurally even while flagging concerns. The eventual D50 (Task #73) did exactly that — but several weeks late.

**Application:** when the model disagrees with a user direction, draft the blueprint anyway and put the concerns into the blueprint's Open Questions section. The artifact is the only thing that survives session compaction.

### §2. Infrastructure compounds across pivots

Iter #1 built validator + reconciler + M1–M5 + kdb-benchmark + response_replay + JSON-schema gates. **None of that was wasted** by the Iter #2 GraphDB pivot. The validator+reconciler is still load-bearing for `pairing_omission` defects in 2026-05-21 work. The M5 metric was *reinterpreted* by Task #59 (body_link_jaccard → body_emit_set_coverage) — but the framework slot survived.

**Application:** infrastructure that catches a defect class survives substrate changes. Don't defer building it because "we might change substrate later."

### §3. The 2-reviewer pattern (Codex + Gemini) materially improves blueprints

Tasks #74, #75, #76, #81 all went through Codex + Gemini structural review before scope-lock. Pattern observed:
- **Codex** tends to catch code-grounded specifics (e.g., for #81: "typed traversal is two distinct implementations — query-time and compile-time").
- **Gemini** tends to provide structural breakdowns (A/B/C clusterings).
- **Gemini needs the review-only guardrail** in every prompt — without it, it overreaches into implementation suggestions (see memory `feedback_gemini_review_only_guardrail`).

### §4. Philosophy convergence via LLM accommodation is a real risk

The A-vs-B ontology-purpose discussion converged on B, with the user's note that this likely owed something to LLM training to accommodate user direction. The convergence may have been correct on the merits, but the *mechanism* (model softening its position) is a pattern to watch for. The mitigation — **Core Rationale Restatement (the "devil's advocate" gate):** when a discussion converges suspiciously fast, OR when the model is about to retract a design constraint under user pressure, output a structured callout containing: (1) the original/opposing technical position in unvarnished form; (2) the specific concessions being made; (3) the failure modes those concessions might trigger (e.g., which hedge from `task75-predeclared-eval-criteria-blueprint.md` §5 might fire). Pivot with eyes open and document the retreat — never let it pass silently.

### §5. Architectural milestones need explicit surfacing

The loop-closure on 2026-05-17 was documented in three separate decision-log entries (D49, D50, D51) + a same-day cold-start empirical proof (Task #71). Yet 5 days later, the user's mental model still places the question as open. The detail-level documentation didn't generate a milestone-level signal.

**Application:** when a multi-iteration objective closes, the *next* session-handoff doc should open with a one-line milestone callout ("LOOP CLOSED 2026-05-17 — manifest → graph substitution complete"), and `CODEBASE_OVERVIEW.md` should carry a dated milestone list in §1 so the architecture doc itself surfaces the inflection point.

---

## What the next iteration looks like

If we name it now, **Iteration #4 is "step-3 ops to V1."** Its preconditions are mostly satisfied:
- Live ontology authority: done (D51).
- Predeclared V1 acceptance criteria: done (#75).
- Domain axis for community routing: done (#76).
- V0 regression guardrails: done (#81).

What's left to start it:
- Probe-set curation (#77) — gated on user OQ-3 decisions.
- PPR implementation (#78).
- Subgraph extraction implementation (#78b).

Iteration #4 is where the question shifts from *"does the loop work?"* (settled) to *"is the loop **useful** at the resolution we wanted?"* — measured via probe-set correctness + V1-over-V0 lift.

---

## Document maintenance

This is a retrospective doc, not a live ledger. Update only when:
- A new iteration boundary is reached (add a section, don't rewrite priors).
- A factual claim above is found to be wrong (correct in place + note the correction date).
- A "Lessons" entry generalizes from a new incident (append; don't delete priors).

Keep `TASKS.md` as the live task ledger and `CODEBASE_OVERVIEW.md` as the live architecture spec. This doc is the **why we walked this way**, not the **what is true today**.

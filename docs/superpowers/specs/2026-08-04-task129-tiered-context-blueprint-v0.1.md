# #129 — Pass-2 Tier-Structured Context: Blueprint v0.1

Date: 2026-08-04 · Task: **#129 Pass-2 tier-structured context (t1/t2/t3 + per-tier instructions)** · Status: **v0.1 — for ratification**

Ledger row: `docs/TASKS.md` #129 (open). Sequenced **before** #130 (dormant entity
lifecycle): #129 reduces spurious drops at the source; #130 changes what a drop means.

---

## 1. What #129 is

The fix for warm-recompile churn, at the prompt layer.

**Verified problem statement.** In sandbox run 2 (`2026-08-04T13-10-43_EDT`, warm,
28 unedited sources, qwen3.7-flash): 99 pages kept / 63 new / **85 dropped = 46% churn**
with zero source edits. The drops were not the model rejecting stale pages — the dropped
slugs were **in T1 of run 2's own context records** (verified: Pabrai 11/11 dropped pages
present in that source's run-2 t1 list; React/Tailwind 4/4). The model was shown its own
prior pages and silently declined to re-emit them. Graph-only retraction
(`orchestrator/kdb_orchestrate.py:212-223`) then deleted the un-supported entities,
producing 85 zombie files on disk.

**Root cause addressed here.** The context snapshot renders T1/T2/T3 as one flat,
unlabeled `pages` list (`common/types.py:327-337`, `compiler/context_loader.py:155-168`).
The model cannot tell "pages this source itself produced" (re-emit/extend) from "pages
from other sources" (link-don't-duplicate) from "1-hop neighborhood" (weak context). The
system prompt (`compiler/prompts/KDB-Compiler-System-Prompt.md:13`) even misdescribes the
block as "pages from sources compiled before this one" — wrong for T1.

**Fix.** Split the snapshot into three labeled tier lists at projection time and teach
the model a different obligation per tier. Selection, scoring, strict tier order, and the
global `page_cap=50` are **untouched** — this task changes what the model is told about
pages it already sees, not which pages it sees.

**Success measure.** Warm sandbox re-run of the same 28 unedited sources: churn (dropped
slugs) materially below the 46% baseline; every residual drop traced to a
`compilation_notes` justification. §9 gates.

## 2. Scope and non-goals

**In scope:**

- `ContextSnapshot` reshape: `pages` field → `t1` / `t2` / `t3` lists (§4).
- `context_loader` projection: partition the already-ranked pages by tier (§5).
- Prompt rendering: tier legend line in the user message; per-tier instruction text in
  the system prompt; `PASS2_PROMPT_VERSION` 4.0.2 → **4.1.0** (§6, §7).
- Test updates + new shape/parity/canary tests (§8).
- Sandbox verification run + churn audit (§9).

**Non-goals (explicitly deferred):**

- **Selection/scoring/cap changes.** Byte-parity of the rank order is a tested invariant
  (§8). No per-tier caps — one global cap, tier order already prioritizes.
- **Validator-level drop enforcement** (e.g., hard-gating a T1 drop that lacks a
  `compilation_notes` entry). Prompt-level instruction first; measure in the sandbox;
  add machinery only if the instruction fails. Listed here so review doesn't re-propose it.
- **#130 dormant lifecycle** (SUPPORTS-loss → `dormant` instead of delete). Sequenced
  after; the §6 wording is written to survive it ("removed from the active graph").
- Person-entity modeling (parked in the #123 residue note).
- Replay tooling: `tools/replay.py` replays **stored responses** through era-keyed
  validators (dispatches on major version, `tools/replay.py:105-114`); it never rebuilds
  prompts. Staying in era 4.x leaves it untouched.

## 3. Binding rulings (owner, 2026-08-04 discussion)

- **R-129-1 — Three lists, three instructions.** "We should separate out T1, T2, and T3
  from the context JSON, and in the prompt give different instructions regarding those 3
  lists."
- **R-129-2 — T1 obligation:** re-emit/extend under the same slug; any drop justified in
  `compilation_notes`.
- **R-129-3 — T2 obligation:** link, don't duplicate.
- **R-129-4 — T3 is weak context.**
- **R-129-5 — Split at projection only.** Selection, scoring, strict tier order, global
  `page_cap=50` untouched.
- **R-129-6 — Success measured against the 46% run-2 churn baseline** on a sandbox re-run.

## 4. Design — `ContextSnapshot` reshape (`common/types.py:327-337`)

```python
@dataclass
class ContextSnapshot:
    """Per-source graph snapshot passed into the prompt (#129: tier-structured).

    t1 = pages this source SUPPORTS (its own prior compiles) — re-emit/extend.
    t2 = pass-1.5 selector hits from other sources — link, don't duplicate.
    t3 = 1-hop neighbors of t1∪t2 — weak context.
    Tiers are disjoint by construction; each list preserves global rank order."""
    source_id: str
    t1: list[ContextPage] = field(default_factory=list)
    t2: list[ContextPage] = field(default_factory=list)
    t3: list[ContextPage] = field(default_factory=list)

    @property
    def pages(self) -> list[ContextPage]:
        """Flat rank-ordered view (t1 then t2 then t3) — the pre-#129 shape."""
        return [*self.t1, *self.t2, *self.t3]

    def to_dict(self) -> dict:
        return {
            "source_id": self.source_id,
            "t1": [p.to_dict() for p in self.t1],
            "t2": [p.to_dict() for p in self.t2],
            "t3": [p.to_dict() for p in self.t3],
        }
```

Decisions:

- **`pages` becomes a read-only property, not a field.** One authoritative representation
  (tiers); the flat view is derived. Concatenation reproduces the old flat list exactly
  because tier order is strict and each tier keeps global rank order (§5). ~25 existing
  `.pages` read sites in `compiler/tests/test_context_loader.py` keep working unchanged.
- **Construction kwarg `pages=` is deleted.** ~15 call sites across 9 test files (listed
  in §8) get the mechanical fix — nearly all are `pages=[]` → drop the kwarg.
- **Empty tiers serialize as `[]`.** No special-casing; an empty tier is a valid answer
  (R-P3a-3). `t1: []` is the cold-start signal for this source.
- **Single JSON block, keys `t1`/`t2`/`t3`.** The user message keeps one
  `## EXISTING CONTEXT (graph snapshot)` section with one `json.dumps`; tier semantics
  ride in a legend line (§6.2). Rejected alternative — three `###` sub-blocks — splits
  the JSON into three arrays for zero behavioral gain.
- `ContextPage` is unchanged (slug/title/page_type/outgoing_links — D8 stands).
- `ContextBuildResult` docstring (`common/types.py:381`) — the "prompt-facing —
  unchanged" note is now false and gets rewritten (comment sweep, §10).

## 5. Design — `context_loader` projection (`compiler/context_loader.py:155-200`)

Selection through ranking (`:89-153`) is **byte-untouched**. The projection loop already
builds `pages` in strict rank order and already computes `tier_of` + per-tier slug lists
for telemetry (`:174-183`). The change is confined to the snapshot construction:

```python
    # --- Projection (unchanged: flat pages in rank order, then partition) ---
    ...
    tier_pages: dict[int, list[ContextPage]] = {1: [], 2: [], 3: []}
    for page in pages:
        tier_pages[tier_of[page.slug]].append(page)

    return ContextBuildResult(
        snapshot=ContextSnapshot(source_id=source_id, t1=tier_pages[1],
                                 t2=tier_pages[2], t3=tier_pages[3]),
        telemetry=...,   # unchanged — already per-tier
    )
```

- Empty-graph early return (`:96`) becomes `ContextSnapshot(source_id=source_id)`.
- **Invariant, tested:** `snapshot.t1/t2/t3` slugs == `telemetry.t1/t2/t3.slugs` (the
  telemetry lists are built from the same partition) — and `snapshot.pages` == the exact
  slug sequence the pre-#129 code would have emitted, given the same graph and params.
- Docstring sweep: module header (`:13-17` "byte-identical" claim),
  `build_context_snapshot` docstring (`:64-67`).

## 6. Design — prompt rendering + instruction text

The full proposed wording follows; these bytes are the reviewable artifact of this
blueprint.

### 6.1 System prompt §1 — input-block bullet (replaces `KDB-Compiler-System-Prompt.md:13`)

```markdown
- `## EXISTING CONTEXT (graph snapshot)` — pages already in the knowledge base,
  rendered without bodies, grouped into three tiers:
  - `t1` — pages this same source produced on previous compiles. They are yours:
    re-emit or extend them (§4).
  - `t2` — pages from other sources, selected as relevant to this one. Link to them;
    do not duplicate them.
  - `t3` — pages one step away from t1/t2 in the link graph. Weak context; usually ignore.
  Any tier may be empty. All three empty means the knowledge base has nothing relevant yet.
```

### 6.2 User-message legend line (`compiler/prompt_builder.py:207`)

The section header gains one line before the JSON:

```
## EXISTING CONTEXT (graph snapshot)
Tiers: t1 = this source's own prior pages (re-emit or extend; justify drops); t2 = relevant pages from other sources (link, don't duplicate); t3 = weak neighborhood context.
{context_json}
```

### 6.3 System prompt §4 — per-tier obligations (restructures §4)

The existing §4 body ("read by meaning, not spelling"; reuse-vs-mint; fence ⇒ reuse;
notes for non-obvious decisions) is retained — it becomes the t2 rule. New structure:

```markdown
## 4. Work the tiers of EXISTING CONTEXT

Read each EXISTING CONTEXT entry by its *meaning*, not its spelling. A slug appears in
at most one tier.

### t1 — your own pages: re-emit or extend, never silently drop

`t1` pages came from this source's own previous compile. For each one:

- **Re-emit it under the same slug.** Extend the body with whatever this reading adds,
  or re-emit it substantially as-is when the source adds nothing new to that idea. Same
  slug is identity — re-emitting under the same slug is how the page stays alive.
- **The summary page in `t1` is re-emitted as your one summary page** — still with NO
  slug (§3); Python re-derives the same identity.
- **Drop a `t1` page only when the source genuinely no longer supports it.** A `t1` page
  you do not re-emit is removed from the active knowledge base (unless another source
  also supports it). Every drop earns a `compilation_notes` entry naming the slug and
  the reason. Silent drops are the failure mode this tier exists to prevent.

### t2 — relevant pages from other sources: link, don't duplicate

`t2` pages belong to other sources. Reference them with `[[slug]]` wikilinks in your
bodies. If this source discusses the same underlying concept, reuse the existing slug
verbatim — in wikilinks, and as the slug of any page you are extending (an extension
accrues this source as a second supporter — that is wanted). Mint a sibling slug only
for a genuinely distinct idea, and link the two explicitly. Genuinely on the fence, lean
toward reuse: a missed reuse fragments the graph irreversibly; a shared slug that
broadens slightly is self-correcting. Non-obvious reuse or sibling decisions are worth
a line in `compilation_notes`.

### t3 — weak context

`t3` pages sit one link away from t1/t2. Background, not assignments: link to one only
when the source genuinely engages it; otherwise ignore the tier.

### Cold start (empty tiers)

When `t1` is empty this source has not been compiled before — every page you mint is
new. When all three tiers are empty you are building the ontology from scratch: mint
slugs by the usual conventions and link concepts to each other inside this compile.
Subsequent sources in the domain will see what this compile returns and compound onto it.
```

(The worked `attention-mechanism` example in §2 stays — it already models reuse and
sibling-minting; its framing sentence gains "from `t2`" for the Bahdanau page.)

### 6.4 Self-check (§7 of the prompt) — one new line

```markdown
- [ ] Every `t1` page is either re-emitted under its slug or its drop is justified in `compilation_notes`.
```

## 7. Version + provenance mechanics

- `PASS2_PROMPT_VERSION` → **"4.1.0"** (`compiler/prompt_builder.py:53`). Minor bump,
  era stays 4.x: the response contract is unchanged (schema, summary-slug rule, bridge —
  all untouched); the change is additive instruction + input-block labeling. Rationale
  for not going 5.0.0: `tools/replay.py:105-114` dispatches on the major prefix; a 5.x
  stamp would fail every existing 4.x fixture closed for zero benefit.
- Comment at the constant: `4.1.0 = #129 tiered context snapshot (t1/t2/t3) + per-tier
  instructions; response contract unchanged`.
- D-115-13 mechanics in the **same commit**: update the version pin
  (`test_pass2_prompt_version_is_4` → rename/docstring) and the golden SHA-256 of the
  packaged prompt bytes (`test_packaged_prompt_matches_golden_sha`,
  `compiler/tests/test_prompt_builder.py:101-108`).
- Provenance comment sweep: `compiler/prompt_builder.py:7`, `common/types.py:381`,
  `compiler/context_loader.py:13-17,64-67`.
- Pass-1 prompt (1.3.0) and pass-1.5 selector prompts: untouched.

## 8. Test plan (TDD — tests written/adjusted before implementation)

### 8.1 Mechanical updates (construction kwarg `pages=` deleted)

`pages=[]` → drop the kwarg (defaults); the two non-empty sites move their pages into a
tier list:

- `compiler/tests/test_compile_one_boundary.py:25` (empty)
- `compiler/tests/test_prompt_builder.py:49` (`_snapshot()` — one page → `t1=[...]`)
- `compiler/tests/test_parsed_summary_gate.py:59`, `test_m2_first_compile.py:63`,
  `test_bridge_canonicalize_integration.py:83`, `test_t2_end_to_end_pass1_path.py:33`,
  `test_compiler.py:71,1069,1092`,
  `test_compile_source.py:147,161,323,518,560,996,1055` (all empty)
- `compiler/tests/test_context_loader.py` — flat `.pages` assertions (~25 sites) keep
  working via the property; assertions that pinned rank order stay as the parity net.

### 8.2 New tests — snapshot shape + selection parity (`test_context_loader.py`)

- `test_snapshot_to_dict_shape` — keys exactly `{source_id, t1, t2, t3}`; each tier a
  list of ContextPage dicts; `pages` key **absent**.
- `test_snapshot_tiers_disjoint_union_is_rank_order` — fixture graph with pages in all
  three tiers: tiers pairwise disjoint; `snapshot.pages` == the exact pre-#129 slug
  sequence for the same graph+params (selection parity).
- `test_snapshot_t1_carries_exactly_source_supported` — t1 slugs == SUPPORTS ∩ active
  (the anti-churn precondition: the model is always shown its own pages).
- `test_snapshot_tier_lists_match_telemetry` — `snapshot.t{i}` slugs ==
  `telemetry.t{i}.slugs` for i∈{1,2,3}, under a binding `page_cap` (cap-truncated
  prefixes; T1 survives first — §3.2 of the P3a v0.2 ruling stands).
- `test_snapshot_empty_tiers_serialize_empty` — no search ⇒ `"t2": []` in `to_dict()`;
  empty graph ⇒ all three empty (early-return path).

### 8.3 New tests — prompt rendering + canaries (`test_prompt_builder.py`)

- Version pin updated to `4.1.0`; golden SHA updated in the same commit (D-115-13).
- `test_context_block_renders_tier_legend` — user message contains the legend line; the
  JSON after it parses to keys `{source_id, t1, t2, t3}`.
- `test_system_prompt_teaches_tiers` — canary on the new §4 text: presence of the t1
  re-emit/same-slug rule, the drop-justification rule (`compilation_notes`), the t2
  link-don't-duplicate rule, the t3 weak-context rule, the t1-summary-no-slug clause.
- Existing content canaries (§70-88) re-verified; any string broken by the §4 restructure
  updated in the same commit.

### 8.4 What is deliberately NOT tested

No validator changes ⇒ no validation tests. No selection changes ⇒ the P3a search/T2
suite is untouched (it must pass unmodified — that is the parity proof).

## 9. Implementation phases + verification gates

- **129.1 — Snapshot tier split (code).** §4 + §5 + docstring sweep; §8.1 + §8.2 tests.
  Gate: full `pytest` green. (Rendered JSON gains tier keys here, with no instruction
  text yet — an intermediate state that ships nowhere: sandbox runs only after 129.2.)
- **129.2 — Prompt instructions (content).** §6 + §7; §8.3 tests. Gate: full `pytest`
  green; version pin + golden SHA updated in the same commit.
- **129.3 — Sandbox verification.** Warm run on `Vault-in-place-test-run`
  (same 28 sources, no edits, qwen3.7-flash):
  `kdb-orchestrate --pipeline vault-test --vault-root … --model qwen3.7-flash --emit-kpis`.
  Audit, vs run 2 (`2026-08-04T13-10-43_EDT`):
  - **Primary:** dropped-slug count / churn % vs the 85 (46%) baseline. Ship bar:
    churn < 20%, and no dropped slug that was in the source's own t1 list without a
    matching `compilation_notes` entry.
  - **Secondary:** justification coverage — % of drops with a `compilation_notes` entry
    (compile journals); extension-vs-verbatim sample check on re-emitted t1 bodies
    (guard against rubber-stamp re-emission); pass-1.5 hit rate steady (no regression
    from the longer system prompt).
  Gate: metrics reported to the owner; pass/fail call is his.

**Closure steps:** ledger narrative; `docs/CODEBASE_OVERVIEW.md` milestone changelog;
North Star context-snapshot description updated to the tiered shape.

## 10. Risks and open questions

- **Model ignores the t1 instruction.** Then churn stays high and §2's deferred lever
  (validator enforcement) comes back on the table. The 129.3 audit is designed to see
  this: drops-without-notes is exactly the measurable signature.
- **Rubber-stamp re-emission** (verbatim copies, no integration). Watched via the
  extension-vs-verbatim sample in 129.3; if dominant, the instruction needs an
  "extend where the source adds" sharpening — wording only, no machinery.
- **Token growth:** two extra JSON keys + a legend line + ~350 words of system prompt —
  negligible against the 1M-in / 64K-out envelope (R-P3a-6).
- **#130 interaction:** §6 wording says "removed from the active knowledge base," which
  stays true when deletion becomes `dormant`. No rework expected.
- **Open question for the owner — review depth.** Phase-2 peer review per the workflow,
  but the last panel's signal-to-noise on measurement scope was low. Recommendation: one
  lean reviewer (opus5) on §6 wording only, or skip external review for this task —
  the design surface is small and every mechanic is pinned by tests. Owner's call.

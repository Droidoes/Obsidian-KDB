# #123 — D7 probe-adjudication reviewer design

Date: 2026-07-26  
Status: implemented and smoke-verified  
Scope: temporary owner decision aid for the D7 truth-set gate

## Decision

Use a static, dependency-free HTML page served from the repository by a local
HTTP server. The page reads the frozen Task #123 draft probes and SearchSnapshot
v1 artifacts directly from their tracked paths. It has no backend and performs
no repository writes.

This is not a product search surface and does not enter the `kdb_search`,
compiler, orchestrator, benchmark-scoring, CLI, or MCP runtime boundaries.

## Workflow

1. Present the two-tier labeling instructions.
2. Step through all 39 probes with query context, draft labels, eligible
   identities, and frozen selector-visible excerpts.
3. Assign each candidate to `relevant_slugs`,
   `acceptable_alternatives`, or neither; confirm abstention, empty-space,
   hub-adversarial, and P10 probes.
4. Resolve metric denominator rules and enter the four numerical gates.
5. Validate completion and download `task123_search_probes_v1.json`.

## State and safety boundary

- Browser `localStorage` autosaves an in-progress adjudication.
- Import/export provides a recoverable checkpoint independent of browser state.
- Export creates a new artifact; the tracked draft is never overwritten.
- No network resources or third-party libraries are used.
- A reset affects only the reviewer-specific browser key after confirmation.
- Frozen fixture files remain immutable.

## UI boundary

- One probe is the primary unit of work.
- Candidate cards show the exact frozen title, slug, page type, domain, and
  selector-visible excerpt.
- Search permits adding an identity from the probe's eligible space when the
  draft omitted it.
- Draft assignments are initial suggestions, visibly distinguished from
  Joseph's decisions.
- Progress is measured separately for ordinary labels and special-probe
  confirmations.
- The gates screen exposes denominator choices before accepting thresholds.

## Verification

- Structural test: no external scripts, stylesheets, fonts, or network URLs.
- Structural test: canonical draft, identity, manifest, excerpt, and
  adversarial paths are fixed in the page.
- Structural test: reviewer-specific autosave key and required export metadata
  are present.
- **Behavioral test** (`test_task123_probe_adjudicator_behavior.py` +
  `task123_adjudicator_smoke.mjs`, node-guarded): the page's own closure runs
  headlessly against the real tracked artifacts. Structural presence of
  `validateExport`/`buildExportArtifact` proves nothing about what they do, and
  the three failure modes that matter all leave the page loading cleanly —
  excerpt paths that 404 into empty candidate cards, validation that never
  blocks, and an export that drops a probe or writes the wrong assignment key.
  Verified 2026-07-26: all 39 probes and 163 identities load, excerpts resolve
  per `page_type`, no candidate slug dangles, an incomplete adjudication is
  blocked, and every assignment round-trips into the exported artifact. All four
  mutations of those failure modes are caught.
- Local smoke, run 2026-07-26: repository served over `http.server`; the page,
  all four tracked JSON inputs and the frozen excerpt routes return 200; the
  inline script passes `node --check`.

## If this reviewer is ever reused — one known gap

The 2026-07-26 run surfaced a limitation worth recording before the tool is
picked up for another adjudication.

**The gap.** The reviewer accepts a threshold that makes its own gate unable to
fail — a `0` floor or a `100%` ceiling — and writes it to the artifact with no
mark distinguishing *deliberately diagnostic* from *forgotten placeholder*. In
this run four of five gates were set that way **on purpose** (spec §8.4), and the
artifact records the numbers but not the intent, so the distinction survives only
in prose elsewhere.

**The fix that was considered and rejected.** A validation rule of the form *"a
gate must be able to bind"* would have caught a forgotten placeholder — and would
also have **blocked the owner's chosen policy**, since these thresholds are the
policy. Adding it would make the tool refuse the very decision it exists to
record.

**The fix to make instead.** Do not validate the value; capture the intent
alongside it. When a threshold renders its gate unfalsifiable, prompt for an
explicit acknowledgement and write it into the artifact — e.g. a `gate_policy`
map recording `diagnostic` vs `binding` per gate, adjudicator-set. A reader then
sees the policy in the data rather than inferring it from a zero, and a genuinely
forgotten threshold is visible as an *unacknowledged* unfalsifiable gate rather
than being indistinguishable from a chosen one.

**Not applied to the v1 artifact.** `benchmark/truth/task123_search_probes_v1.json`
is adjudicated, committed and ratified; spec §8.4 now carries the policy in prose,
which closes the practical risk. Retrofitting a field into ratified truth data is
an owner decision, not a tooling cleanup — so this stays a note until either the
reviewer is reused or Joseph asks for the field.

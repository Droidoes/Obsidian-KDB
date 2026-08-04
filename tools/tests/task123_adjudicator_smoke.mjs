// Behavioral smoke for the #123 D7 probe-adjudication reviewer.
//
// The sibling structural test asserts that identifiers like `validateExport`
// and `buildExportArtifact` are PRESENT in the page. Presence is not behavior:
// a page whose excerpt paths 404 loads clean and renders every candidate card
// empty, and an export that silently drops a probe still contains the string
// "buildExportArtifact". This file runs the page's own closure against the real
// tracked artifacts and checks what it actually produces.
//
// Driven by test_task123_probe_adjudicator_behavior.py, which extracts the
// page's inline script and exposes its closure as `globalThis.__reviewer`.
//
// argv: [harness.js] [repo_root]

import fs from "node:fs";
import path from "node:path";

const [HARNESS, REPO] = process.argv.slice(2);

// --- stubs: just enough browser to run the closure -------------------------
// Any DOM access resolves to a sink that absorbs reads, writes and calls, so
// render paths run without asserting anything about the rendered output.
const absorb = () =>
  new Proxy(function () {}, {
    get: (target, prop) => (prop === "then" ? undefined : (target[prop] ??= absorb())),
    set: () => true,
    apply: () => absorb(),
  });
globalThis.document = new Proxy({}, {get: () => absorb()});
globalThis.window = {location: {href: "http://localhost/tools/task123_probe_adjudicator.html"}};

const store = new Map();
globalThis.localStorage = {
  getItem: key => store.get(key) ?? null,
  setItem: (key, value) => store.set(key, value),
  removeItem: key => store.delete(key),
};

const missing = [];
globalThis.fetch = async url => {
  // Browser semantics: the page sits at /tools/, so `../benchmark/...` resolves
  // against the serve root — which is the repository root.
  const file = path.join(REPO, decodeURIComponent(new URL(String(url)).pathname));
  if (!fs.existsSync(file)) {
    missing.push(file);
    return {ok: false, status: 404};
  }
  const text = fs.readFileSync(file, "utf8");
  return {ok: true, status: 200, text: async () => text, json: async () => JSON.parse(text)};
};

await import(`file://${HARNESS}`);
const R = globalThis.__reviewer;

const failures = [];
const check = (condition, message) => {
  console.log(`${condition ? "PASS" : "FAIL"}  ${message}`);
  if (!condition) failures.push(message);
};

// --- 1. the page loads every tracked artifact it pins ----------------------
await R.loadData();
check(missing.length === 0, `every fetched path resolves (missing: ${missing.join(", ")})`);
const draft = R.data.draft;
check(draft.probes.length === 39, `draft carries 39 probes (got ${draft.probes.length})`);
check(R.data.identities.length === 163, `163 fixture identities (got ${R.data.identities.length})`);
check(R.data.injectionByProbe.size > 0, `adversarial injections indexed (${R.data.injectionByProbe.size})`);

// --- 2. excerpts resolve per page_type ------------------------------------
// The structural test pins only the `excerpts/` prefix; the real layout is
// three page_type subdirectories. A flattened layout 404s all 163 files.
const sampled = new Map();
for (const row of R.data.identities) sampled.set(row.page_type, row.slug);
check(sampled.size === 3, `all three page_types present (${[...sampled.keys()].join(",")})`);
const before = missing.length;
for (const slug of sampled.values()) {
  const excerpt = await R.frozenExcerpt(slug);
  check(typeof excerpt === "string" && excerpt.length > 0, `frozen excerpt loads for ${slug}`);
}
check(missing.length === before, `excerpt paths resolve per page_type (missing: ${missing.slice(before).join(", ")})`);

// --- 3. candidates and eligible spaces are real ---------------------------
let dangling = 0;
const emptyCandidates = [];
for (const probe of draft.probes) {
  const candidates = R.candidateSlugs(probe);
  if (!candidates.length && !R.isSpecialProbe(probe)) emptyCandidates.push(probe.probe_id);
  for (const slug of candidates) if (!R.data.identityBySlug.has(slug)) dangling += 1;
}
check(dangling === 0, `every candidate slug resolves to a fixture identity (${dangling} dangling)`);
check(emptyCandidates.length === 0, `no ordinary probe renders zero candidates (${emptyCandidates.join(",")})`);
const degenerate = draft.probes.filter(
  probe => R.eligibleIdentities(probe).length === 0 && !/^(E|F)/.test(probe.probe_id)
);
check(degenerate.length === 0, `eligible space populated for non-empty probes (${degenerate.map(p => p.probe_id).join(",")})`);

// --- 4. validation blocks an incomplete adjudication ----------------------
const openErrors = R.validateExport();
check(openErrors.length > 0, `an unfinished adjudication is blocked (${openErrors.length} errors)`);
check(openErrors.some(e => /probes still need confirmation/.test(e)), "blocks on unconfirmed probes");
check(openErrors.some(e => /threshold|ceiling/.test(e)), "blocks on unset numerical gates");

// --- 5. full round-trip: every assignment reaches the artifact ------------
const state = R.getState();
const ABSTAIN = new Set(["A10", "E01", "E02", "E03", "E04", "E05", "F01", "F02"]);
const expected = new Map();
for (const probe of draft.probes) {
  const candidates = R.candidateSlugs(probe);
  const injection = R.data.injectionByProbe.get(probe.probe_id);
  const relevant = [];
  const acceptable = [];
  if (!ABSTAIN.has(probe.probe_id)) {
    candidates.forEach((slug, index) => {
      if (injection && slug === injection.entity.slug) return; // never label the injection
      (index % 2 === 0 ? relevant : acceptable).push(slug);
    });
  }
  state.assignments[probe.probe_id] = {};
  for (const slug of relevant) state.assignments[probe.probe_id][slug] = "relevant";
  for (const slug of acceptable) state.assignments[probe.probe_id][slug] = "acceptable";
  for (const slug of candidates) state.assignments[probe.probe_id][slug] ??= "neither";
  state.confirmedProbes[probe.probe_id] = true;
  if (R.isSpecialProbe(probe)) state.specialConfirmations[probe.probe_id] = true;
  expected.set(probe.probe_id, {relevant, acceptable});
}
Object.assign(state.gates, {
  classARecallAggregation: "macro",
  stageOneRecallAggregation: "macro",
  abstentionDenominator: "class_e_only",
  m5Treatment: "watched",
  semanticAbstentionAccuracyMinPercent: "80",
  classARecallAt5MinPercent: "70",
  stageOneReducedMRecallMinPercent: "60",
  selectorFailureRateMaxPercent: "5",
});
const completeErrors = R.validateExport();
check(completeErrors.length === 0, `a complete adjudication validates clean (${JSON.stringify(completeErrors)})`);

const artifact = R.buildExportArtifact();
check(artifact.probes.length === 39, `export preserves all 39 probes (got ${artifact.probes.length})`);
check(artifact.status === "adjudicated" && artifact.adjudicator === "joseph", "export carries adjudication metadata");
check(artifact.probes.every(p => !("kimi_draft" in p)), "draft suggestions stripped from the artifact");
check(
  artifact.probes.every(p => p.status === "adjudicated" && p.adjudicator === "joseph"),
  "every probe carries per-probe adjudication metadata"
);

const mismatched = [];
const sorted = values => JSON.stringify([...values].sort());
for (const probe of artifact.probes) {
  const want = expected.get(probe.probe_id);
  if (
    sorted(probe.relevant_slugs) !== sorted(want.relevant) ||
    sorted(probe.acceptable_alternatives) !== sorted(want.acceptable)
  ) {
    mismatched.push(probe.probe_id);
  }
}
check(mismatched.length === 0, `every assignment round-trips into the export (${mismatched.join(",")})`);
check(
  artifact.probes.filter(p => ABSTAIN.has(p.probe_id)).every(p => p.relevant_slugs.length === 0),
  "abstention probes export with zero relevant slugs"
);
check(
  artifact.gates.escaped_foreign_identity_rate_max === 0 &&
    artifact.gates.class_a_recall_at_5_min === 0.7 &&
    artifact.gates.selector_failure_rate_max === 0.05,
  "percentage gates convert to rates"
);
check(
  artifact.probes.filter(p => R.isSpecialProbe(p)).every(p => p.owner_outcome_confirmed === true),
  "special probes carry owner_outcome_confirmed"
);
check(JSON.parse(JSON.stringify(artifact)).probes.length === 39, "the artifact JSON round-trips");

// --- 6. autosave touches only the reviewer's own key ----------------------
check(
  [...store.keys()].every(key => key === "task123-d7-adjudication-reviewer-v1"),
  `only the reviewer-specific autosave key is written (${[...store.keys()].join(",")})`
);

console.log(failures.length ? `\nSMOKE FAILED (${failures.length})` : "\nSMOKE PASSED");
process.exit(failures.length ? 1 : 0);

# Repo placement & boundaries — formal response (DeepSeek)

**Date:** 2026-08-16
**Reviewer:** DeepSeek (`deepseek-v4-pro`)
**Review basis:** `2026-08-16-repo-placement-problem-statement.md`
**Companion brief:** `2026-08-16-gmail-info-search-rank-problem-statement.md` (internal architecture — not re-litigated here)

---

## 0. Verdict

**CONCUR-WITH-CORRECTIONS.** The brief frames the right question but frames it one
level too high: this is a **boundary-contract** problem, not a **repo** problem.
Recommended answer:

> **Keep one repo (Obsidian-KDB).** Add the parallel system as a new top-level
> package, enforce its independence with the *existing* AST layering guard plus a
> *new* mechanical write-boundary guard, keep `common/` single-sourced in place, and
> leave feeders where they are. A peer repo is the **only** alternative, and it is
> contingent: it is acceptable *only if* Joseph wants git-level separation, and it
> *then requires* extracting the shared LLM slice of `common/` first — never
> vendoring a copy.

---

## 1. Review findings

### 1.1 Q1 and Q2 are one question, not two

The brief lists "repo topology" (Q1) and "shared infrastructure" (Q2) as separate
questions. They are entangled. A peer repo is **only cleanly possible** if the
shared-infra decision is resolved in a specific way:

- Peer repo **without** touching `common/` forces one of two bad outcomes: vendor a
  copy (drift — forfeits cost telemetry, the brief's own requirement) or pip-depend
  on the whole `obsidian-kdb` package (drags `kuzu`/`mcp`/`networkx`/`python-louvain`
  into the experiment and makes the "competing" system depend on the incumbent's
  package).
- Therefore: **the answer to Q2 is not downstream of Q1 — it gates it.**

The panel should answer them jointly, not sequentially.

### 1.2 A repo boundary is neither necessary nor sufficient for the wanted independence

What the brief actually wants from "independence" is three enforceable things:

1. The new system **never imports** the incumbent's packages (`kdb_graph`,
   `compiler`, `orchestrator`, `kdb_search`, `kdb_mcp`, `ingestion`).
2. The new system **never writes** the incumbent's state (wiki, manifest, graph,
   pipeline configs, `state/runs` journals).
3. The shared leaf (LLM transport + telemetry + atomic IO + env config) stays
   **single-sourced** — no drift.

A repo boundary delivers none of these *by itself*: a peer repo can still read the
vault's graph files or reimplement overlap, and it actively invites (3) to fail. The
existing monorepo already has the mechanism for (1) and (3): the AST guard in
`tools/tests/test_package_boundaries.py`, which fails the suite the moment a package
imports outside its contract. The only missing piece is a **mechanical** enforcement
of (2) — see §3.4.

Consequence: **"independent experiment" is a code-dependency + write-boundary
property, not a directory-location property.** A monorepo can be made *more*
independent than a naive peer repo, because the guard is enforced by CI/tests rather
than by convention.

### 1.3 `common/` is two packages wearing one coat

Q2 asks whether to "extract `common/` into a third shared package" as if it were one
blob. It is not. Measured:

| Slice | Modules | Line count | Shared? |
|---|---|---|---|
| **Infra** | `call_model`, `call_model_retry`, `model_pool`, `model_route`, `llm_telemetry`, `atomic_io`, `config/`, `util/`, `models.json` | ~1,150 | Yes — both systems need it |
| **Domain** | `paths`, `types`, `source_io`, `wiki_io`, `run_context`, `measurement`, `version` | ~1,800 | No — Obsidian-KDB pipeline logic |

`paths.py` is wiki/slug/page-type resolution — the new system does not need it (it
needs its own raw-path + state-path resolution). `types.py` (640 lines) is
compile-result/source schemas. `measurement.py` is Borda/KPI scoring. None of these
should ever move into a shared package. Any "extract `common/`" proposal must name
**the infra slice**, not the whole package — otherwise the shared package ships the
pipeline's domain model to the competing system.

### 1.4 Minor corrections

- **Corpus figure drift.** This brief says "2,625 rankable articles"; the companion
  says "2,659 full articles." My inspection of the raw tree counts 2,659 files, of
  which ~89 are video/podcast and ~25 are near-empty — so "rankable articles" needs a
  single pinned definition (and it is not 2,659). Pick one number and cite its
  derivation in both briefs.
- **"Source trees are immutable to both systems"** is slightly imprecise: the feeder
  *does* mutate raw sources (moves promo to `_promo/`, stamps `ingested_at`). Precise
  wording: *"raw sources are immutable to both **extraction** systems; the feeder is
  the sole producer/mutator of the raw trees."*

### 1.5 What the brief already gets right

- Feeders "serve both extraction architectures equally and neither owns them" — sharp,
  and it determines Q3.
- Listing "every added repo is a standing operational cost" — correct, and it should
  be weighted *more* heavily than the brief does (§4).
- Keeping the hard write boundary as a decided, non-negotiable constraint — correct;
  it just needs a mechanism (§3.4).

---

## 2. Recommendation

### 2.1 Primary: monorepo, new top-level package

Add the parallel system as a top-level package (working name `ledger/`) inside
Obsidian-KDB, beside `compiler/`, `kdb_graph/`, etc. It:

- imports only `common` (the infra slice in practice) — enforced by extending
  `ALLOWED` in `test_package_boundaries.py` with `"ledger": {"common"}`;
- writes only its own state subtree (§3.2) — enforced mechanically (§3.4);
- is a distinct directory that can be `git rm`-ed cleanly if the experiment fails;
- shares the existing pytest harness, fixtures, and `conftest.py`, so the head-to-head
  comparison lives in one test suite with one probe fixture.

Weighting the brief's five factors for a single operator:

| Factor | Monorepo | Peer repo |
|---|---|---|
| Independence of experiment | Strong (guard-enforced) | Strong (structural) |
| Failure/release isolation | Moderate (shared history) | Strong |
| Single-operator simplicity | **Strong** (one venv/test/harness) | Weak (N+1 repos, drift risk) |
| Ease of head-to-head | **Strong** (shared harness/fixtures) | Weak (needs a third home for harness) |
| Preserved optionality | **Strong** (cheap to wire later) | Moderate (re-wiring cost) |

Three of five, plus the two binding constraints (single-source leaf, shared
comparison harness), favor monorepo.

### 2.2 The only alternative: peer repo — contingent and gated

Choose a peer repo **only if** Joseph wants the experiment's git history and
promotion/deletion fully separate from the incumbent. That is a legitimate,
*psychological/structural* preference — not a technical necessity. If chosen, it is
**gated on** first extracting the infra slice of `common/` (§1.3) into a third
leaf repo (e.g. `~/Droidoes/kdb-llm`, editable-installed by both). Never vendor a
copy; never depend on the whole `obsidian-kdb` package.

Do **not** extract the leaf "just in case" while staying monorepo — with a single
consumer, the split is pure churn. Document the infra/domain seam (§1.3) so the split
stays mechanical if a real second repo ever appears.

---

## 3. Answers to the six questions

### 3.1 Q1 — Repo topology

Monorepo: new top-level package in Obsidian-KDB. See §2.1. Peer repo is the
contingent alternative (§2.2), not the default.

### 3.2 Q2 — Shared infrastructure

Keep `common/` single-sourced **in place**. No extraction, no vendor, no whole-package
dependency. The new package imports `common` directly. Document the infra/domain seam
so a later split (only if a real second repo appears) is mechanical. This is the
zero-drift, zero-churn answer.

### 3.3 Q3 — The ingestion layer

Feeders **stay in Obsidian-KDB** (`ingestion/feeder/`). They are *producers of vault
sources* that serve both extraction architectures equally, and neither owns them.
The new system must depend on the **frontmatter contract** of the raw md files, not on
the feeder code — the feeder and the ledger's intake adapter are different layers even
inside one repo. Do not move feeders into the ledger package and do not split them
into a third repo (cost, no benefit).

### 3.4 Q4 — State placement

Vault, beside the existing state: **`<vault>/KDB/ledger/`** (or the system's final
name), holding the SQLite DB + extraction journals + score snapshots. Rationale:
data-in-vault/code-in-repo is the established precedent (`<vault>/KDB/graph`,
`<vault>/KDB/state/`), keeps the vault the single backup surface, and preserves the
dry-run/audit/reversible discipline. Repo-local state would fork the backup story and
break "reversible." Raw sources stay read-only at `KDB/raw/joseph-ft-public-gmail/`.

### 3.5 Q5 — Boundary contract

- **Raw sources**: read-only to both extraction systems; the feeder is the sole writer.
- **Incumbent state** (wiki, manifest, graph, pipeline configs, `state/runs`): the
  ledger never reads-for-coupling or writes; it may read exports only.
- **Ledger state**: written only by the ledger package, only under `<vault>/KDB/ledger/`.
- **Exports are the only sanctioned coupling**: versioned JSONL/CSV/JSON to a stable
  export path; the future harness and any GraphDB consumer read *exports*, never the
  live SQLite, never the other system's internals.
- **No shared mutable state, no cross-imports** — the latter already AST-guarded.

Make the write boundary **mechanical**, not conventional: add a guard test that walks
the `ledger/` package and asserts every filesystem-write call resolves under its own
state root (or under an explicit dry-run allowlist). "Never writes the wiki/manifest/
graph" is exactly the kind of rule that drifts silently if left to convention.

### 3.6 Q6 — Convergence path

If the ledger wins the head-to-head, the end-state is **still one repo**:

- `kdb_graph` stays — its data is rebuildable and it remains the vault-in-place
  authority until superseded.
- The ledger's extraction becomes the default for vault-in-place too (a pipeline-
  selection change, not a repo move).
- A **thin combining harness** (new package) merges ranking × graph; it reads both
  systems' *exports*, not internals.
- Nothing merges or retires at repo level. If the ledger loses or is abandoned:
  `git rm` its package and delete `<vault>/KDB/ledger/`; the incumbent is untouched.

The convergence path is *easier* in a monorepo because the harness, fixtures, and
probe set already share a home — one more reason the peer-repo option pays a tax it
never recovers for this operator.

---

## 4. Decision gate

Recommend **monorepo (new top-level `ledger/` package)**, with:

1. `ALLOWED` extended to `"ledger": {"common"}` in the AST guard.
2. A new mechanical write-boundary test (§3.5).
3. State at `<vault>/KDB/ledger/`; exports as the only coupling.
4. Feeders left in place; no `common/` extraction now (seam documented for later).

If Joseph prefers git-level separation, the **only** acceptable path is: extract the
`common/` infra slice into a shared leaf repo **first**, then build the peer repo
against it — never a vendored copy. This response is not ratified; the next step is a
synthesis with the companion brief's panel responses before Joseph selects.

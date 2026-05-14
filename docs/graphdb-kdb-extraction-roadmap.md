# GraphDB-KDB — Package Extraction Roadmap

**Status:** Forward-looking architectural intent. Not a task; not a commitment to a timeline.

**Date:** 2026-05-14.

**Scope:** Captures the team's shared vision for evolving GraphDB-KDB from "a Python package living inside the Obsidian-KDB repository" to "a standalone reusable package that can serve multiple ingestion pipelines and multiple downstream consumers."

**Why durable.** Without this record, future sessions could re-derive (or worse, drift from) the staged vision. Today's #63 decisions — Page→Entity rename, B-lite adapter pattern, no upward imports — are *prerequisites* for this arc; their value is undersold if the destination they enable is not captured.

---

## 1. The end-state vision

**GraphDB-KDB is a standalone Python package** that:

- Lives in its own git repository at `~/Droidoes/GraphDB-KDB-package/` (sibling to Obsidian-KDB). The Kuzu *data* directory remains at `~/Droidoes/GraphDB-KDB/` per D35 — these are **two distinct paths** at the same parent (package code vs Kuzu binary state).
- Is installable by any Python project: `pip install graphdb-kdb`.
- Is **versioned independently** of any ingestion pipeline; semver discipline applies (`0.x` for pre-1.0 iteration, `1.0+` once the public API stabilizes).
- Has **no knowledge of any specific producer**. The core knows about Kuzu, graph schema, replay mechanics, and a documented producer-contract; nothing more.
- Ships **first-party adapters** for known producers (Obsidian-KDB initially). Adapters are an extensibility surface, not the core.
- Serves **multiple downstream consumers** without favoritism: future kdb-graph utility (Obsidian-view rendering), RAG/agent integrations, knowledge-hole detection, adaptive learning paths, third-party projects in or outside the Droidoes namespace.

**What it is NOT:**

- Not "Obsidian-KDB's graph subsystem." That framing dies at the split.
- Not a general-purpose graph DB (that's Kuzu's job — GraphDB-KDB is the *ontology-shaped wrapper* around Kuzu).
- Not a multi-tenant service. Single-process, single-user assumptions remain valid.

---

## 2. Today's state — Stage 0

| Aspect | Current state | Verifiable |
|---|---|---|
| Code location | `Obsidian-KDB/graphdb_kdb/` (monorepo) | `ls graphdb_kdb/` |
| Installed via | `pip install -e .` of Obsidian-KDB (entry-point: `graphdb-kdb = "graphdb_kdb.cli:main"`) | `pyproject.toml` |
| Kuzu data directory | `~/Droidoes/GraphDB-KDB/` — already outside Obsidian-KDB (per D35) | filesystem |
| Upward imports | **Zero** — `grep "from kdb_compiler\|import kdb_compiler" graphdb_kdb/` returns nothing | grep (verified 2026-05-14) |
| Test suite | Independent: `graphdb_kdb/tests/` with its own `conftest.py`, no kdb-compile fixtures | 76/76 green |
| CLI | `graphdb-kdb` (current subcommand surface — see `--help` for the live list) | `graphdb-kdb --help` |
| Module name | `graphdb_kdb` (Python identifier; underscored) | `__init__.py` |
| Schema generality | Mostly Obsidian-flavored at field-name level; rename pass pending per D-A1/D-A2 | `schema.py` |

**What's already true that enables the split:**

1. The CLI is already named for the general layer (`graphdb-kdb`), not the project family.
2. The Kuzu data directory is already at a project-independent location.
3. The Python module has no upward dependencies.
4. The test suite stands alone.
5. The CLI surface (the current 13-subcommand set as of #63.5) operates on graph primitives, not Obsidian artifacts. *(Count will grow with #63.6/#63.7/#63.9 — auto-derived from `--help` going forward; do not hardcode in docs.)*

**What's still pending that enables the split (today's #63 decisions):**

- **D-A1, D-A2** (rename pass): `Page → Entity`; `compile_state/count/last_compiled_at → ingest_*` on Source. Removes the loudest Obsidian-isms from the storage schema.
- **D-B1** (B-lite rebuilder): generic replay core in `rebuilder.py` + producer-specific logic isolated to `adapters/obsidian_runs.py`. Encodes the producer-vs-core boundary in the file layout, not just in convention.
- **D-doc** (this document + producer-contract note + manifest-succession arc): durable record of intent so the discipline doesn't drift.

---

## 3. The five-stage progression

### Stage 0 — Monorepo, discipline-enforced (today)

- **State**: `graphdb_kdb/` lives inside `Obsidian-KDB/`. Coupling rules enforced by convention + greppable invariants ("no `import kdb_compiler` from `graphdb_kdb`").
- **Validation**: 76/76 tests; CLI works standalone; no upward imports.
- **Why not split yet**: API is still settling (just shipped #63.1–#63.5; #63.6–#63.9 still ahead). Splitting mid-design would force premature versioning discipline.

### Stage 1 — Sibling repository, editable install

- **Trigger**: Completion of #63.9 (snapshot/export) closes the v1 CLI surface. At that point we've dogfooded all 14+ subcommands and have a stable public API to extract around.
- **Mechanics**:
  - Create new git repo at `~/Droidoes/GraphDB-KDB-package/` (sibling, not nested).
  - Extract `graphdb_kdb/` from Obsidian-KDB via `git subtree split` (preserves history; cleaner than `filter-branch`).
  - New `pyproject.toml` in the extracted repo with its own deps (`kuzu>=0.11`, `networkx>=3.0`, `python-louvain>=0.16`, `scipy>=1.10`).
  - Obsidian-KDB's `pyproject.toml` declares `graphdb-kdb @ file:../GraphDB-KDB-package` (editable file install).
  - CI in Obsidian-KDB still runs both test suites; CI in GraphDB-KDB-package runs only its own.
- **Validation**: Obsidian-KDB still passes its full test suite after extraction; `graphdb-kdb` CLI works identically; no behavior change.
- **Why this stage**: stress-test the package boundary in a low-stakes setting (still single-machine, still single user, still one consumer) before adding the complexity of a real second consumer or producer.

### Stage 2 — Versioned local package

- **Trigger**: First time a change in `graphdb-kdb-package/main` would have inadvertently broken Obsidian-KDB if released as a tagged version. Could also be triggered by **any second consumer** appearing — even an in-house notebook project or a `kdb-graph` (Obsidian-view utility) prototype.
- **Mechanics**:
  - Tag `0.1.0` in the GraphDB-KDB-package repo.
  - Obsidian-KDB pins `graphdb-kdb~=0.1.0` (allows `0.1.x` patches, locks out `0.2.x` which may introduce breaking changes) OR pins to an exact tag during early-extraction churn.
  - CHANGELOG.md added; semver discipline begins.
  - Pre-1.0 convention: breaking API changes bump **minor** (`0.1.x → 0.2.0`); compatible additions bump **patch** (`0.1.0 → 0.1.1`). Post-1.0: standard semver (major for breaking, minor for compatible additions, patch for fixes).
- **Validation**: Obsidian-KDB can install a specific older GraphDB-KDB version and still function (forward-/backward-compat smoke test).
- **Why this stage**: makes iteration on each side independent. A compile-pipeline change can't break consumers; a graph-layer refactor doesn't force a compile rerun.

### Stage 3 — Producer #2 arrives

- **Trigger**: A real non-Obsidian ingester is built. Most likely candidates by current direction: arxiv-papers compile pipeline (architecturally closest analog); YouTube-transcript compile; codebase semantic extraction. Could be a hobby project or a serious initiative.
- **Mechanics**:
  - Second adapter added: `graphdb_kdb.adapters.arxiv_runs` (or similar). Parallel structure to `obsidian_runs`.
  - The B-lite generic core in `rebuilder.py` is *validated or revealed insufficient* — first real test of whether the abstraction holds.
  - CLI evolves: `graphdb-kdb rebuild --producer obsidian|arxiv` (default may stay obsidian for back-compat in the local ecosystem).
  - Producer-contract document gets its real first iteration based on lived experience of writing a second adapter.
  - Schema may need a real rename round if `Entity.entity_type`'s value space genuinely diverges (e.g., arxiv's `concept`, `claim`, `citation` vs Obsidian's `summary`, `concept`, `article`).
- **Validation**: both producers can rebuild end-to-end; both adapters share the generic core; the graph queries the second producer needs are answerable without producer-specific code in `queries.py` or `analytics.py`.
- **Architectural question this stage forces**: where does the *second* adapter live? See §5.

### Stage 4 — PyPI publication

- **Trigger**: External demand (someone outside your machine wants to install it) OR open-sourcing decision.
- **Mechanics**:
  - Choose a PyPI name (`graphdb-kdb`, `graphdb-kdb-py`, `kuzu-ontology`, …; see §8).
  - Add documentation site (Sphinx, MkDocs, or just a good README + API reference).
  - Set up CI/CD: GitHub Actions for test, lint, build, publish on tag.
  - License declaration in the package (currently inherited from Obsidian-KDB — verify).
  - Public API documentation: every exported symbol gets docstring + example.
  - Consider: deprecation policy, support window, contribution guide.
- **Validation**: `pip install graphdb-kdb` from PyPI in a fresh venv, `python -c "import graphdb_kdb"`, run the test suite against the installed package.
- **Why optional**: the package can live happily as a private sibling repo for a long time. PyPI publication is only motivated by external sharing.

---

## 4. Architectural prerequisites for clean extraction

These are the invariants the codebase must maintain to keep the split path open. If any of these is violated, the violation must be tracked as **extraction debt** and remediated before the next stage transition.

| # | Invariant | How to verify | Status |
|---|---|---|---|
| **PR1** | `graphdb_kdb/` has zero imports from `kdb_compiler`, `kdb_benchmark`, or any other Obsidian-KDB sibling package. | `grep -rn "from kdb_compiler\|import kdb_compiler\|from kdb_benchmark\|import kdb_benchmark" graphdb_kdb/` returns nothing. | ✅ As of 2026-05-14 |
| **PR2** | `graphdb_kdb/` has no hardcoded Obsidian-specific paths (`~/Obsidian/`, `KDB/raw/`, `state/runs/`). Paths come from caller arguments or environment variables. | Audit `graphdb_kdb/*.py` for string literals matching Obsidian patterns. | To audit before Stage 1 |
| **PR3** | Schema field names + node-table names are pipeline-agnostic at the storage layer. (`Entity` not `Page`; `ingest_state` not `compile_state`.) Field *values* may remain Obsidian-flavored until producer #2 forces the abstraction. | DDL review in `graphdb_kdb/schema.py`. | Pending D-A1/D-A2 |
| **PR4** | Producer-specific code is isolated to `graphdb_kdb/adapters/<producer>_runs.py`. The core (`rebuilder.py`, `ingestor.py`, `queries.py`, `analytics.py`, `verifier.py`) is producer-agnostic. | File-layout audit; verify no `obsidian` strings outside `adapters/`. | Pending D-B1 |
| **PR5** | Test suite is self-contained: no fixtures from `kdb_compiler/tests/`, no shared `conftest.py` reaching outside `graphdb_kdb/`. | `grep -rn "from kdb_compiler.tests\|from kdb_benchmark.tests" graphdb_kdb/tests/`. | ✅ As of 2026-05-14 |
| **PR6** | CLI is fully functional standalone — no implicit dependencies on Obsidian-KDB CLI commands being available. | `graphdb-kdb` subcommands tested with Obsidian-KDB CLI uninstalled. | To verify before Stage 1 |
| **PR7** | Public API surface is documented: which symbols are public (`graphdb_kdb.GraphDB`, `graphdb_kdb.types.*`, etc.) vs internal. Internal symbols may break; public ones get semver discipline at Stage 2. | A `__all__` declaration or explicit API document. | Pending |
| **PR8** | Dependencies are declared cleanly: every `import` in `graphdb_kdb/` resolves to either Python stdlib, a declared dep in (future) `graphdb-kdb-package/pyproject.toml`, or a sibling module within `graphdb_kdb/`. | Static analysis with a tool like `deptry` or manual audit. | To audit before Stage 1 |
| **PR9** | Adapters declare which producer journal `schema_version` values they support via `supported_journal_versions: list[str]` class attribute. Adapter raises `UnsupportedJournalVersionError` on mismatch rather than silently producing wrong graph state. | Lint check / adapter test. | Pending #63.6 (specified per D-S3) |
| **PR10** | Test fixtures policy: fixtures that exercise *graph mechanics* (synthetic compile_result-shaped payloads constructed locally) move with the package. Fixtures that depend on Obsidian artifacts (real KDB/raw/ files, live manifest.json) stay Obsidian-KDB-side and are not bundled. | Audit `graphdb_kdb/tests/fixtures/` and `graphdb_kdb/tests/conftest.py` before Stage 1. | To audit before Stage 1 |

**Operational rule**: a CI check that runs `grep` against PR1, PR2, PR5 on every PR — fail the build on violation. (Can be added now; cheap insurance.) Same for PR9 (adapter declares versions) and PR10 (no Obsidian-path fixtures in core tests).

---

## 5. The Obsidian-adapter placement question

Once GraphDB-KDB is its own package, where does the Obsidian-specific code live?

**Vocabulary note** (important — clarifies the "core never imports adapter" invariant):

- **Core** = `graphdb_kdb/{schema, graphdb, ingestor, queries, analytics, verifier, rebuilder}.py` — graph primitives, producer-agnostic.
- **Adapter layer** = `graphdb_kdb/adapters/` — producer-specific bridges.
- **Package** = core + adapter layer + CLI + registry. *The whole shipping artifact.*

**The "no upward import" invariant** (PR1 in §4) applies specifically to **core** ↔ producer code. It does NOT prohibit the package's CLI or adapter-registry from importing bundled adapters — that's how `graphdb-kdb rebuild --producer obsidian` resolves the right adapter to use. The discipline boundary is **inside** the package, not at the package edge.

| Option | Layout | Mechanics | Trade-offs |
|---|---|---|---|
| **A. First-party adapter bundled** | `graphdb-kdb` package ships with `graphdb_kdb.adapters.obsidian_runs` baked in. New adapters added as new files in `adapters/`. Core never imports adapters; CLI/registry may. | One repo; users opt-in by selecting the adapter they want via `--producer` flag. | ✅ Pragmatic; matches today's #63.6 plan. ✅ Adapter docs colocated with core docs. ⚠️ Non-Obsidian users install Obsidian adapter code they won't use (negligible — <200 LOC). ⚠️ Not implied as the forever-default; revisit at Stage 3. |
| **B. Separate adapter package** | `graphdb-kdb` is pure core. `graphdb-kdb-obsidian` is a sibling package depending on `graphdb-kdb`. | Two repos to maintain; user installs both. | ✅ Cleanest separation. ⚠️ Doubled packaging overhead. ⚠️ Adapter docs split from core docs. ⚠️ Discoverability problem ("which adapter do I need?"). |
| **C. Adapter in producer repo** | `Obsidian-KDB` keeps its own `obsidian_kdb_graphdb_adapter/` package. `graphdb-kdb` discovers it at runtime via Python entry-points (`graphdb_kdb.adapters` entry-point group). | Three packages; entry-point discovery machinery. | ✅ Plugin-architecture purity. ⚠️ Entry-point discovery is overkill for 1–3 adapters. ⚠️ Producer needs to know `graphdb-kdb`'s adapter protocol (still fine — that's the producer-contract). |

**Lean: Option A for the first split (Stage 1).** Same YAGNI logic that drove B-lite: the *first* second-adapter doesn't reveal whether the plugin architecture is the right shape; the *third* adapter probably does. Revisit at Stage 3 when producer #2 lands.

**Revisit trigger:**

1. Three or more first-party adapters accumulate (the registry/discovery question becomes real).
2. A third-party developer needs to author an adapter without contributing to the GraphDB-KDB repo.
3. The Obsidian-specific adapter starts depending on Obsidian-KDB Python types in a way that creates a circular dependency (Option C becomes forced).

---

## 6. Migration mechanics — what the split actually looks like

### Stage 0 → 1: extraction

**Pre-flight checklist:**

- [ ] All PR1–PR8 invariants satisfied.
- [ ] #63.9 (snapshot/export) shipped — v1 CLI surface complete.
- [ ] All current callers in Obsidian-KDB inventoried. (Today: `kdb_compiler/kdb_compile.py` Stage 9 wiring after #63.7 lands.)
- [ ] No pending refactors mid-flight in `graphdb_kdb/`.

**Mechanics:**

```bash
# 1. Extract subtree preserving history.
#    NOTE: `git subtree split --prefix=graphdb_kdb` produces a branch whose
#    ROOT IS the contents of graphdb_kdb/ — there is no graphdb_kdb/ subdir
#    in the result. No `git mv` step is needed after this.
cd ~/Droidoes/Obsidian-KDB
git subtree split --prefix=graphdb_kdb -b graphdb_kdb-extract

# 2. Create new sibling repo from that extracted branch
cd ~/Droidoes
git clone --branch graphdb_kdb-extract Obsidian-KDB GraphDB-KDB-package
cd GraphDB-KDB-package
git remote remove origin
# Initialize new origin or leave detached.
# At this point, repo root contains schema.py, graphdb.py, ingestor.py, etc.
# directly (NOT inside a graphdb_kdb/ subdirectory).

# 3. Re-establish package directory structure expected by Python import
#    (pyproject.toml will reference `graphdb_kdb/` package; the repo root
#    must contain that directory). Move contents back into a graphdb_kdb/
#    subdirectory:
mkdir graphdb_kdb
git mv schema.py graphdb.py ingestor.py queries.py analytics.py verifier.py \
       rebuilder.py cli.py types.py __init__.py __main__.py graphdb_kdb/
git mv tests graphdb_kdb/
# (Adapter files moved similarly once they exist.)
git commit -m "restructure: package files into graphdb_kdb/ subdir"

# 4. Author pyproject.toml in repo root
# (copy deps + entry-points from Obsidian-KDB's pyproject.toml,
#  scoped to just the graphdb_kdb subset)

# 5. In Obsidian-KDB: remove the now-extracted directory,
#    update pyproject.toml to depend on the sibling package
cd ~/Droidoes/Obsidian-KDB
git rm -r graphdb_kdb/
# Edit pyproject.toml: dependencies += ["graphdb-kdb @ file:../GraphDB-KDB-package"]
pip install -e .

# 6. Verify
pytest                         # Obsidian-KDB tests pass
cd ../GraphDB-KDB-package
pytest                         # GraphDB-KDB tests pass independently
graphdb-kdb --help             # CLI still works
```

**Alternative**: skip step 3 entirely by adjusting `pyproject.toml`'s package configuration to treat the repo root *as* the package (`[tool.setuptools.packages.find] where = ["."]` with a `packages = ["graphdb_kdb"]` mapping pointing at the root). Step 3 is the conservative path that preserves the existing Python import shape.

**Validation gates:**

- [ ] Both test suites green.
- [ ] `which graphdb-kdb` resolves to the new package's entry point.
- [ ] `python -c "from graphdb_kdb import GraphDB; print(GraphDB)"` works.
- [ ] A fresh `kdb-compile` end-to-end completes successfully (Stage 9 still wired).
- [ ] `graphdb-kdb rebuild` works on the canonical corpus.

### Stage 1 → 2: versioning

**Mechanics:**

- Tag `0.1.0` in GraphDB-KDB-package.
- Add `CHANGELOG.md` (started at extraction).
- Obsidian-KDB pins `graphdb-kdb~=0.1.0` in `pyproject.toml` (consistent with §3 Stage 2 — allows `0.1.x` patches, locks out `0.2.x` minor bumps that may carry breaking changes per pre-1.0 semver convention).
- API contract document (`docs/API.md` or similar) enumerates the public surface.

### Stage 2 → 3: second producer

**No mechanical change to the package itself.** The second adapter is *added*. The interesting work is:

- Authoring the producer-contract document properly (informed by writing a real second adapter).
- Identifying which of `graphdb_kdb`'s "general" code was secretly Obsidian-flavored (the abstraction-validity test).
- Schema migration if needed (now finally informed by real data, not speculation).

### Stage 3 → 4: PyPI

**Mechanics:** standard Python packaging: build wheel, upload to PyPI, set up CI/CD. Public API documentation. License clarity.

---

## 7. Anti-patterns — what must NOT happen

Each of these violates an invariant and silently degrades extractability. If any of these accumulates, the extraction cost grows nonlinearly.

| Anti-pattern | Why bad | Mitigation |
|---|---|---|
| `from kdb_compiler.run_journal import STAGE_NAMES` (or similar) inside `graphdb_kdb/` | Inverts dependency direction; couples graph layer to producer Python types. | The B-lite adapter pattern: adapter reads journal as documented JSON, not via Python import. |
| Hardcoding `~/Obsidian/KDB/state/` anywhere in `graphdb_kdb/` (outside `adapters/`) | Locks the package to one user's filesystem layout. | All paths come from arguments or env vars. Adapters may have producer-flavored defaults; core may not. |
| Adding fields to `Entity` or `Source` that only Obsidian produces (e.g., `obsidian_yaml_frontmatter`) | Bloats the schema with producer-specific concerns; forces other adapters to write nulls. | Producer-specific data goes in the adapter, possibly as separate node tables (e.g., `ObsidianMetadata` with 1:1 to Entity) — and only if a real query needs it. |
| Mixing source-content concerns into graph nodes (`Entity.body`, `Entity.markdown_raw`) | Conflates "graph state" with "source content"; balloons the DB; couples to one rendering format. | Bodies stay in source files (the D8 boundary). The graph stores semantic state, not file content. |
| Making `graphdb_kdb/tests/` depend on fixtures from `kdb_compiler/tests/` | Couples test suites; breaks self-containment. | Tests synthesize their own fixtures via `conftest.py` builders. |
| `graphdb-kdb rebuild` silently drops other producers' data in a co-tenant DB | Whole-DB drop semantics are catastrophic when multiple producers share the directory. | **v1 rule (D-S2)**: rebuild always drops whole DB; single-producer assumption is documented as L8. Producer-scoped rebuild is deferred until producer #2 ships AND the team agrees the scoped semantics. CLI prints a warning before executing whole-DB drop. |
| Adding `kdb_compile`-aware CLI subcommands (e.g., `graphdb-kdb watch --vault-root` that polls Obsidian state) | Pulls producer awareness into the operator surface. | Such functionality goes in `kdb-graph` (the Obsidian-view utility) or in `kdb-compile` itself, calling `graphdb-kdb` underneath. |
| Releasing breaking schema changes without a SCHEMA_VERSION bump + migration | Strands existing graph data; forces manual recovery. | Schema migration registry (#63.1 scaffolded it; populate when first migration ships). |
| Treating "GraphDB-KDB" and "Obsidian-KDB" as a single product in docs/marketing | Reintroduces the confusion the separation was designed to prevent. | Always frame: "GraphDB-KDB is the ontology layer; Obsidian-KDB is one producer." |

---

## 8. Open questions

These don't need to be answered now — but should be revisited at the stage they become forcing:

| ID | Question | When to answer |
|---|---|---|
| **OQ-E1** | Final PyPI name. `graphdb-kdb` is preferred but may be taken or visually ambiguous. Alternatives: `kuzu-ontology`, `graph-kdb`, `kdb-graphdb`. | Stage 4 |
| **OQ-E2** | License clarity. Current Obsidian-KDB license carries to extracted package? Or new license appropriate? Open-source vs proprietary? | Stage 1 (or earlier if external use considered) |
| **OQ-E3** | Generic event-sourced API beyond compile-result-style producers? E.g., a `MutationStream` interface so producers without "runs" can still feed the graph? | Stage 3 (if producer #2 demands it) |
| **OQ-E4** | Schema versioning + migration path: when SCHEMA_VERSION bumps, how does an existing data dir migrate vs require a rebuild? | First real schema change |
| **OQ-E5** | Adapter discovery mechanism: entry-points, explicit registry, CLI flag? | Stage 3 (when producer #2 forces multi-adapter discovery) |
| **OQ-E6** | Documentation site: Sphinx, MkDocs, or a hand-rolled README + reference? | Stage 4 |
| **OQ-E7** | The Obsidian-adapter placement (§5 Options A/B/C) decision is provisional at A. Hard re-evaluation due at Stage 3. | Stage 3 |
| **OQ-E8** | Telemetry / observability: does the package emit structured logs? Metrics? Or stay quiet and let the caller decide? | Stage 2 or 3 |
| **OQ-E9** | ~~Should `kdb-compile`'s Stage 9 be moved into `graphdb_kdb.adapters.obsidian_runs`?~~ **CLOSED** by D-S0 (2026-05-14): Stage 9 calls `graphdb_kdb.adapters.obsidian_runs.sync_current_run(...)`; adapter owns both live sync and replay as the single Obsidian→graph entry point. | n/a |

---

## 9. References

- **D32** (multi-source storage layer; Obsidian-flavored ingestion API) — `docs/task-graphdb-kdb-blueprint.md` §2
- **D34** (independence by shared upstream) — same, §2
- **D35** (physical location: `~/Droidoes/GraphDB-KDB/`) — same, §2
- **D36** (naming triad: module/dir/CLI) — same, §2
- **D39** (rebuild eligibility filter) — same, §2 + §8.2
- **Manifest succession arc** — pending doc (companion to this one)
- **Producer contract** — pending doc (formal contract for what GraphDB-KDB expects from any producer's journal/adapter)
- **Memory notes (durable):**
  - `project_graphdb_kdb_refoundation` — paradigm + scope
  - `project_graphdb_kdb_vs_kdb_graph_distinction` — naming guardrail
  - `feedback_graph_over_vector_for_kdb` — anti-vector lean
- **Conversation record** — `docs/New-GraphDB-Paradigm.md`
- **Codex brainstorm** (2026-05-14) — `docs/codex-brainstorm-prompt-2026-05-14-schema-and-rebuilder.md` + Codex response in 2026-05-14 daily note
- **Today's daily note** — `~/Obsidian/Daily Notes/2026-05-14.md` (capture of this session's deliberation)

---

## 10. What this document does NOT do

- Does not commit to a timeline.
- Does not authorize Stage 1 (extraction) — that requires explicit user "Proceed" after #63.9.
- Does not define the producer-contract — that's a companion document.
- Does not address `kdb-graph` (the future Obsidian-view utility) — that's a separate downstream-consumer concern, not part of the package-extraction arc itself.

---

**End-state restatement** (so the destination is crisp):

> `pip install graphdb-kdb` works for any Python project. The user opens a Kuzu directory, queries it via the GraphDB API or CLI, runs analytics, gets results. They never touch Obsidian-KDB. They never know about `kdb-compile`. If they have their own raw-text corpus and want to populate the graph, they either use a first-party adapter or write their own producer following the producer-contract.
>
> Obsidian-KDB becomes one such producer — distinguished from others only by being the first and the most fully fleshed-out. Its `kdb-compile` pipeline feeds GraphDB-KDB at Stage 9; its downstream consumers (kdb-graph utility, EXISTING CONTEXT seed selection) read from GraphDB-KDB. Obsidian-KDB owns no graph state; GraphDB-KDB owns no compile-pipeline logic.
>
> The clean separation that today exists only by discipline becomes enforced by the package boundary.

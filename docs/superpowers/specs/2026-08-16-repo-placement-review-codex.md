# Repo placement and boundaries — Codex review

> **Status:** architecture review (2026-08-16). This is a deliberation artifact,
> not a ratified architecture. It reviews
> [`2026-08-16-repo-placement-problem-statement.md`](2026-08-16-repo-placement-problem-statement.md).

## Executive conclusion

The brief is directionally strong, but it needs another revision before panel
dispatch. It currently conflates four separate decisions—application repo placement,
shared runtime ownership, feeder ownership, and data placement—and quietly anchors
reviewers toward a peer repo.

## 1. Load-bearing findings

### 1.1 The prompt is not fully options-free

Joseph's peer-repo instinct will anchor reviewers. Keep it, but label it explicitly
as the sponsor hypothesis they must challenge after independently deriving their
answer.

### 1.2 “Reuse `common/`” is already an architectural choice

Specify required capabilities instead:

- provider-neutral model routing
- retry and timeout behavior
- JSON-mode support
- token, latency, retry, and cost telemetry

The panel should decide whether those capabilities are shared, duplicated, or
extracted.

### 1.3 `common/` is a leaf, but not a standalone library

It mixes reusable model infrastructure with KDB-specific paths,
source/frontmatter types, wiki I/O, run context, and telemetry types. Furthermore,
`common` is packaged inside the entire `obsidian-kdb` distribution, whose dependencies
include Kuzu, MCP, graph libraries, ingestion libraries, and all application packages.

Therefore, “pip-depend on Obsidian-KDB” would make an application repo masquerade as
a shared library and pull in the whole KDB dependency surface.

### 1.4 The shared-source boundary is not neutral yet

The new system may be a peer repo, but its input lives at `KDB/raw/...`. That is a
KDB-owned namespace. Independence requires:

- a configurable corpus-root adapter;
- stable source identity based on Gmail ID/content hash, not relative path;
- no KDB path encoded into ledger primary keys;
- a documented future move path to a neutral source root.

A physical source migration is unnecessary now, but the new system must survive one.

### 1.5 “Immutable source trees” contradicts feeder ownership

The constraint should say:

> Sources are append/update-owned by the ingestion producer and read-only to
> downstream consumers.

Otherwise, the feeder cannot legally create sources.

### 1.6 State is not one category

The state-placement question should distinguish:

- rebuildable SQLite indexes and scores;
- costly but replayable extraction results;
- irreplaceable human feedback;
- generated comparison exports;
- configuration and secrets.

They need different durability and deletion rules.

### 1.7 A head-to-head winner does not necessarily retire either system

GraphDB and Signal Ledger optimize different jobs. Compare them only on a shared task
such as research-priority ranking or lesson extraction. Winning that benchmark would
not prove GraphDB is inferior for knowledge connectivity.

### 1.8 Two factual details need checking

- The `~1,200` test count appears stale; recent North Star milestones report more
  than 3,200 green tests.
- Explain how the working corpus moved from 2,659 to 2,625 rankable articles and
  identify the disposition of the removed 34.

## 2. Architectural options

| Option | Topology | Advantages | Costs and risks |
|---|---|---|---|
| **A. Package inside Obsidian-KDB** | Add a boundary-guarded top-level package | Lowest operational overhead; immediate reuse of runtime and tests | Weak experimental/release isolation; KDB becomes owner of an unrelated database |
| **B. Self-contained peer repo** | New repo with its own model client and utilities | Maximum independence; clean failure and release isolation | Duplicated provider behavior and telemetry may drift |
| **C. Peer repo plus narrow shared runtime** | Two application repos depend on a small provider-neutral package | Clean ownership, consistent routing/telemetry, no application-to-application dependency | Adds a third package/release surface and requires a careful extraction |

A fourth apparent option—peer repo importing `obsidian-kdb.common`—should be rejected
as an end state. It combines the coupling of Option A with the operational overhead
of multiple repos.

## 3. Recommended topology

Recommend **Option C**, staged to keep the scope controlled:

```text
                         shared llm-runtime
                         /                \
                        v                  v
Vault ingestion ──> Vault sources <── Obsidian-KDB
                         ^
                         |
                    Signal Ledger
                         |
                  versioned exports
                         |
                 comparison harness
```

### 3.1 Application placement

Create the extraction/ranking system as a peer repo under `~/Droidoes/`.

It should:

- own its schema, migrations, extraction logic, ranking, feedback, CLI, and tests;
- never import an Obsidian-KDB application package;
- accept any corpus root through an input adapter;
- read the current Gmail corpus without writing it.

### 3.2 Shared runtime

Do not extract all of `common/`. Extract only a narrow provider-neutral runtime
contract:

- model route and registry
- request/response types
- provider callers
- retry and timeout behavior
- normalized stop reasons
- neutral token/cost telemetry

Keep KDB-specific paths, wiki I/O, source types, run context, and measurement
structures in Obsidian-KDB. Atomic writes are small enough to remain local unless
their behavior genuinely needs to be identical.

Both applications should depend on a pinned runtime version. Neither application
should depend on the other.

### 3.3 Feeder placement

The feeders are producers of the shared source substrate, so conceptually neither
downstream system owns them. However, moving the shipped Gmail feeder now would add
migration risk without changing user value.

Recommended staged treatment:

1. Leave `ingestion/feeder/` in Obsidian-KDB temporarily.
2. Freeze and version its Markdown source contract.
3. Ensure it imports no compiler, graph, search, or orchestrator code.
4. File a future extraction trigger: move feeders to a neutral `vault-ingestion`
   package when a second feeder ships or the Gmail feeder first requires
   non-KDB-specific development.

The claim that feeders share no commonality should also be softened. Their acquisition
logic differs, but they should share an output envelope, identity rules, idempotency,
journaling, dry-run behavior, and failure semantics.

### 3.4 State placement

Do not place the new system under `<vault>/KDB/state/`. That namespace belongs to
Obsidian-KDB and carries KDB-specific lifecycle assumptions.

Use a peer data root such as:

```text
<vault>/<new-system>/
  ledger.sqlite          # materialized/query state
  runs/                  # extraction journals
  feedback/events.jsonl  # authoritative human judgments
  exports/               # versioned comparison artifacts
```

The ledger should be rebuildable from source files, successful extraction journals,
and feedback events. Human feedback is the irreplaceable asset and must never be
treated as disposable derived state.

### 3.5 Boundary contract

The ratified contract should eventually state:

- Ingestion may create/update source files.
- Obsidian-KDB and Signal Ledger read sources but never mutate them.
- Each application writes only within its own state namespace.
- Shared runtime knows nothing about the vault or either application.
- Applications never import one another.
- Comparison reads versioned exports only.
- Source identity is stable across path moves.
- No wipe command may cross an application's state boundary.

### 3.6 Convergence

If Signal Ledger wins on ranking:

- add a vault-in-place input adapter to the peer repo;
- keep the repositories separate unless they genuinely converge on the same
  lifecycle and data model;
- do not move source files merely to reflect code ownership;
- treat retirement of GraphDB as a separate decision requiring broader evidence.

## 4. Recommended brief revisions

Before sending it to the panel, add four explicit requested decisions:

1. Application topology: A, B, or C.
2. Shared-runtime policy: extract, duplicate, or temporary coupling—with an exit
   condition.
3. Feeder ownership: immediate move or deferred extraction trigger.
4. State taxonomy and namespace: authoritative versus rebuildable artifacts.

Also instruct reviewers to derive these independently before considering Joseph's
peer-repo hypothesis.

## 5. Verdict

The problem identification is good, but the decision axes need decomposition before
external review. The cleanest target is a peer Signal Ledger, a narrowly shared model
runtime, temporarily stationary feeders behind a stable contract, and a separate
vault state namespace.

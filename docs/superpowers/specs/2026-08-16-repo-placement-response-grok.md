# Repo placement — formal architecture response (Grok)

**Date:** 2026-08-16
**Reviewer:** Grok
**Review basis:** `2026-08-16-repo-placement-problem-statement.md`
**Independence:** this response reviews the brief and answers its six questions.
It does not file a task ID and does not amend `docs/TASKS.md` or
`docs/CODEBASE_OVERVIEW.md`.

## 0. Verdict

**CONCUR-WITH-CORRECTIONS.** The six questions are the right six, and the
feeder/consumer split in Q3 is the most important sentence in the file. Fix
four issues before dispatch: a leaked solution in the header, a missing
existing peer repo, a stale size claim, and no success criteria for “good
placement.”

Recommended direction (not ratified by this file): a **sibling package inside
Obsidian-KDB** for v1, importing in-tree `common/` only, with state under
`<vault>/KDB/state/<system>/`. Do not open a green-field peer on day one. Do
not put the ledger in `10x-Learning-Engine` while that repo’s North Star
rejects generalized databases. Do not move feeders.

---

## 1. Review of the problem statement

### 1.1 What the brief gets right

- Vault = home of **sources**; code repos are not libraries of articles. That
  should survive every option.
- Feeders write sources and therefore **serve both extraction architectures**.
  Neither GraphDB nor the new ledger owns ingestion. Splitting feeders because
  “they have different logic” is a different decision from placing the new
  ledger.
- `common/` is correctly named as the coupling problem. It is a real leaf:
  `common/tests/test_layering_leaf.py` exists; `common/` does not import
  `ingestion` / `compiler` / `kdb_graph`.
- Single-operator overhead is a first-class constraint, not a footnote.
- Q6 (convergence if the experiment wins) belongs in this brief. Most
  placement docs forget the way back.
- **2,625** rankable articles matches the companion brief’s digest correction
  (2,659 − 34). Keep that number consistent everywhere.

### 1.2 The header is not options-free

The status block says the companion brief’s family has “already converged on
an extraction ledger” and that “coverage policy decided gate-then-extract.”
The companion problem statement was put back to options-free. This header
re-imports a **coverage policy** the companion brief no longer asserts.

The panel for *placement* does not need a coverage policy. Drop that clause.
Say only: companion brief = what the new system is *for*; this brief = where
code and state live.

Joseph’s peer-repo instinct in §1.5 is fine **if labeled as instinct**. As
written it reads like the destination the panel is supposed to ratify.

### 1.3 An existing peer repo is missing

`~/Droidoes/10x-Learning-Engine` already exists. Its North Star (same day,
2026-08-16) says equity research is the goal, a generalized compounding
database was rejected, and **no integration with Obsidian-KDB has been
selected**. Earlier KDB notes also parked idea ledgers in “a new
equity-research repo.”

The brief’s Q1 is written as a binary: package-in-KDB vs **new** peer. The
real option set is at least three:

1. Sibling package inside Obsidian-KDB
2. New empty peer under `~/Droidoes/`
3. Land in **10x-Learning-Engine** (or make that repo the consumer)

Omitting (3) will produce a third Droidoes repo that overlaps 10x’s mission,
or a KDB package that 10x later has to absorb.

### 1.4 “~1,200 non-live tests” is stale

The changelog’s last suite prints were in the **3,000+** range.
`pyproject.toml` still lists eight test roots. Do not give the panel a
2026-05 size picture. Either cite a dated `pytest` count or say
“multi-thousand, eight packages, AST layering guards.”

### 1.5 `pip-depend on Obsidian-KDB` is not a small option

`obsidian-kdb` as installed pulls **kuzu, mcp, networkx, louvain**, plus three
LLM SDKs. A peer repo that `pip install`s this package to get `call_model`
inherits a graph database it must not write. That option should be described
as “depend on the **leaf**, not the product” — which today means either an
in-tree import or extracting `common/` later. Vendoring `common/` should be
listed as a last resort (drift on retry/telemetry is exactly what Q2 is
trying to avoid).

### 1.6 Success criteria are missing

The header does not promise them this time, but the panel still needs a
pass/fail for *placement*, not for ranking quality. Suggested gates:

- A new operator setup is one venv, or two is explicitly justified
- The knowledge pipeline’s test suite does not have to go red for a
  ledger-only change
- Head-to-head comparison does not require either system to import the
  other’s internals
- Feeders can keep shipping without opening the ledger repo
- If the experiment dies, deletion does not require a KDB schema migration

### 1.7 “Independence” is four different things

Q1 stacks them as one score. Split them or the panel will argue past each
other:

| Kind | Sibling package | New git repo |
|---|---|---|
| Import / failure isolation | AST guard + no writes (already decided) | Same, plus no shared tree |
| Release isolation | Same tag as KDB | Own tags |
| Process isolation | Separate CLI is enough | Same |
| Operator isolation | One venv, one suite | Second venv, CI, `AGENTS.md`, conventions |

Architectural independence of the **experiment** is import + write-boundary.
Git independence is an operational choice. The 434 invented PendingLinks came
from a compile contract, not from sharing a repo.

### 1.8 Smaller gaps

- **Docs home.** If the ledger is a peer, where do *this* panel’s artifacts
  live? Today they are in KDB `docs/superpowers/`. That is already a coupling.
- **Secrets / model pool.** `common/models.json` + `.env` live with KDB. A
  peer must say whether it reads those files or duplicates them.
- **Q6 “wins.”** Undefined. Point at the companion’s evaluation axes, or say
  “Joseph’s weekly triage uses the ledger instead of the raw folder for this
  corpus.”

---

## 2. Suggested brief edits

1. Delete the coverage-policy clause from the header.
2. Add 10x-Learning-Engine as a named option / constraint in §2.
3. Replace “~1,200 tests” with a dated or qualitative size.
4. Add a short section of placement success criteria (§1.6).
5. Relabel §1.5 as “Joseph’s instinct, not a decision.”
6. In Q2, strike “pip-depend on Obsidian-KDB” or qualify it as “depend on
   `common` only, which is not a published package today.”

---

## 3. Direct answers to the six questions

These are panel-seat answers. They are not a North Star filing.

### Q1 — Repo topology

Prefer a **sibling package in Obsidian-KDB** for v1, with the same leaf/guard
pattern as `kdb_search` (`common` only).

Reason: the ledger is a competing *extraction architecture over vault
sources*, and the brief says it may later be applied to vault-in-place. That
is KDB-adjacent infrastructure, not a new product, and not 10x’s current
North Star (which just rejected generalized databases).

Do **not** open a green-field peer on day one. You already pay for 10x as the
equity-research repo. A third Droidoes repo is the option that needs the
strongest justification.

Reversibility favors this order: clean package → split later if the
experiment earns a life of its own. Merging two repos after the fact is the
expensive direction.

### Q2 — Shared infrastructure

In-tree `common/`. Do not extract a third package until two *repos* need it.
Do not vendor. Do not depend on the `obsidian-kdb` distribution.

### Q3 — Ingestion layer

Stays in Obsidian-KDB. Feeders are vault writers. They do not follow the
ledger. “Feeders have different logic” is a reason for
`ingestion/feeder/<name>.py` modules, not a new repo.

### Q4 — State placement

`<vault>/KDB/state/<system>/` (SQLite + journals + exports). Same pattern as
GraphDB data-in-vault. The repo stays code. A repo-local DB dies when you
switch machines and is invisible to vault backup.

### Q5 — Boundary contract

Both systems **read** raw Markdown and must not write it. Neither writes the
other’s store. The only sanctioned coupling is **versioned exports**
(JSONL/CSV) plus, later, a comparison harness that depends on those files,
not on either package.

### Q6 — Convergence path

If the ledger wins *for this corpus*, the package stays; GraphDB is simply
not run on gmail-substack. If it later wins for vault-in-place, that is a new
architecture task (which compile paths retire). Do not pre-design a
mega-merge. If it loses, `rm` the package and the state directory.

---

## 4. Decision gate

This response is not ratified. If Joseph wants the brief corrected before
other seats file, apply §2 first. If he selects the Q1–Q6 direction above,
the next Architecture-phase actions are the usual ones (task ID, North Star
boundary, blueprint) — none of those are done here.

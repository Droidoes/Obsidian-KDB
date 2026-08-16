# Repo placement — review and feedback (Claude)

> **Status:** review and feedback (2026-08-16). Responds to
> [`2026-08-16-repo-placement-problem-statement.md`](2026-08-16-repo-placement-problem-statement.md).
> Not a competing brief, not a ratified decision — a fact check against existing
> project precedent, for Joseph's decision.

## The brief is missing a question

Its six questions never ask "did this project already decide this once?" — and it
already has, on disk, undiscovered by the brief.

## The governing precedent already exists

`docs/reference/graphdb-kdb-extraction-roadmap.md` is a fully worked-out staged plan
for extracting `kdb_graph` (then called `graphdb_kdb`) from this monorepo into its own
peer repo — Stage 0 (monorepo, discipline-enforced) → Stage 1 (sibling repo, editable
install) → Stage 2 (versioned, semver) → Stage 3 (second producer) → Stage 4 (PyPI). It
defines ten extractability invariants (PR1–PR10 — no upward imports, no hardcoded
paths, self-contained tests, etc.) and explicit triggers for when to actually pull the
trigger on Stage 1 ("API surface has settled," "a second consumer appears," "a change
would have broken a consumer if released"). **It's still at Stage 0 today** —
deliberately: "splitting mid-design would force premature versioning discipline."

Separately, `kdb_mcp` — a genuinely new sibling package added later, consuming both
`kdb_graph` and `common` — was kept in-repo "per F2, the panel consensus."

That's a directly on-point precedent for the exact question this brief is asking, and
it points at **in-repo package now, staged extraction later, with the extraction path
kept mechanically open** — not an immediate peer repo. The new system's shape is *more*
unsettled than `graphdb_kdb` was at Stage 0 (its own coverage-policy question isn't
even resolved), which is precisely the condition the roadmap says argues against
splitting.

## A correction to the brief's own evidence for the peer-repo instinct

§1.5 leans on "the way the Obsidian-KDB repo does" — the implicit reference is
`~/Droidoes/GraphDB-KDB`. That's not a code repo; it's a retired Kuzu *data* directory
(`file` reports it as raw `data`, header `KUZU`), superseded 2026-06-11, called "a
retired stray" in `CODEBASE_OVERVIEW.md`. There's no actual working example of a peer
*code* repo in this project to point to — the roadmap describes an intended one that
was never executed.

## The brief's six questions aren't equally open

- **Q1 (repo topology)** is largely answered by the roadmap: new leaf-ish package
  inside Obsidian-KDB (imports only `common`, nothing else may import it), guarded by
  an AST test like `common/tests/test_layering_leaf.py` or the roadmap's PR1 pattern.
  Extraction stays available via the same `git subtree split` playbook the roadmap
  already documents, triggered later by the same kind of signal (head-to-head
  comparison picks a winner, or a real second consumer of the new system appears).
- **Q2 (what happens to `common/`)** is genuinely open — checked, and there's no
  equivalent roadmap for `common/` ever splitting out; its guard test
  (`test_layering_leaf.py`) only enforces internal no-upward-import health, not
  extractability. This is the actual novel question the panel should spend its
  attention on, not Q1.

## Small correction

The brief's §2 states "~1,200 non-live tests" — `CODEBASE_OVERVIEW.md` recorded 1,290
as of #113, and it's grown since. Worth using a verified number or just dropping the
count rather than repeating an unverified one.

## Suggested next step

Add a line to the brief's §2 or §3 citing the roadmap and the `kdb_mcp` F2 decision as
required reading, and note that Q1 and Q2 aren't equally open — the panel's attention
is better spent on Q2 (`common/`) and the boundary-contract question (Q5) than
re-deriving Q1 from scratch.

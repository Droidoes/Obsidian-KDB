# GraphDB Tutorial TODO

Working notes for the next tutorial iteration. Source: Joseph review on
2026-05-27. Do not treat these as resolved architecture changes; they are
documentation clarification tasks unless promoted into the North Star docs.

## Completed

- Created first static HTML tutorial: `docs/tutorial/graphdb-tutorial.html`.
- Captured first reader-review pass as this TODO list.
- Revised `graphdb-tutorial.html` to clarify multiple source-preparation pipelines,
  the special stay-in-place Obsidian case, and the distinction between upstream
  ingestion pipelines and compiler-to-GraphDB graph-write application.
- Rewrote the Components section for adapter, graph write engine, queries,
  analytics, verifier, and rebuilder in plainer language.
- Expanded Graph Basics definitions for node, connection, edge, neighbor,
  provenance, subgraph, and community.
- Added typed-graph visualization examples that reconcile the Obsidian graph
  mental model with Kuzu's typed node/edge schema.
- Rewrote the adapter-boundary explanation in the pipeline section with a
  concrete compile_result -> adapter -> graph-write flow.
- Expanded Capabilities definitions for PageRank, neighbors, incoming references,
  shortest paths, subgraphs, topic communities, and structural holes.
- Added `docs/tutorial/memory-workflow.md` as a non-authoritative primer on
  project memory, Obsidian memory, and assistant behavior memory.
- Added a typed Kuzu graph diagram using different shapes for `Source`, `Entity`,
  `Domain`, and `Claim` nodes plus labeled relationship arrows.
- Clarified that connections are always between nodes and may connect same-type
  or different-type nodes only when the schema declares that edge type.
- Clarified that edges sit between nodes as independent relationship records,
  not on either endpoint node.
- Added a properties explanation as the third core GraphDB component alongside
  nodes and edges.
- Clarified that each summary/concept/article/alias page is an `Entity` node,
  each raw source is a `Source` node, sources connect to generated pages through
  `SUPPORTS`, and generated pages connect to each other through `LINKS_TO`.
- Clarified "provenance" as a standard term meaning origin/evidence trail, while
  also defining the beginner-friendly project meaning as source-to-entity support
  metadata.

## Pending

### Mental Model / Ingestion Architecture

- Review whether the new "source-preparation pipelines" wording is the right
  public term, or whether the tutorial should use "ingestion pipelines" with a
  stricter definition.

### Components Section

- Review whether Cypher still needs a dedicated beginner-friendly glossary entry.
- Consider adding a compact "before/after" adapter example with actual JSON and
  resulting graph records.

### Graph Basics Section

- Review whether "node types are the graph equivalent of classes" is intuitive
  enough or should be replaced with a database-table analogy.
- Review whether the new diagram's shapes/arrows are enough to make the mental
  model stick, or whether a second source-specific example diagram is needed.

### Schema / Visualization

- Replace the ASCII typed-graph example with a clearer visual diagram if needed.
- Decide whether the ASCII relationship list should stay as a compact schema
  reference now that the visual diagram exists.

### Pipeline / Adapter Boundary

- Review whether the adapter-boundary explanation should move earlier, near the
  Components section.

### Capabilities Section

- Review whether each capability should include a concrete CLI example inline,
  not only in the Query Examples section.

### Future Tutorial Improvements

- Add one small diagram for the typed graph model.
- Add one concrete end-to-end example using `rationality` or `Li_Lu_Munger_College_Dec_2024.md`.
- Add a glossary section for first-time graph terms.
- Consider splitting "Build / Query / Concepts" into separate pages if the single tutorial gets too dense.

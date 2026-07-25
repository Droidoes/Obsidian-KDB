1. **The app, in one sentence**  
   "Show me the highest-leverage bridge I am missing: which two clusters in my vault are barely connected, what thin evidence currently links them, and what concrete synthesis question should I write or research next?"

2. **Why search can't do it**  
   Search can find text that already shares words; it cannot see that two communities of ideas are structurally adjacent but under-connected, that the connection is carried by one fragile bridge edge or one low-support entity, or that a high-centrality concept lacks enough grounding across sources. The value is in detecting topology plus absence: sparse inter-community bridges, high-PageRank/low-SUPPORTS nodes, cross-domain links, and weakly grounded connector entities. Grep has no representation of community boundaries, bridge scarcity, support degree, or "this should connect but barely does."

3. **The mechanism**  
   Use 1.0 graph primitives: `Entity`, `Source`, `Domain`; `LINKS_TO`, `SUPPORTS`, `BELONGS_TO`; `ALIAS_OF` for canonical resolution; analytics `communities()`, `structural_holes()`, and `pagerank()`. The MCP composition is:
   - resolve user scope with `resolve_search_keys(keys)` or `get_entity(slug)`;
   - run a new graph-native tool `bridge_opportunities(scope=None, top_n=5)` that wraps `communities()` + `structural_holes()`, ranks sparse community pairs by bridge count ascending, endpoint PageRank descending, cross-domain diversity, and low support-degree penalty;
   - for each candidate, use `graph_neighborhood(slug, depth=1-2)` and `find_path(a,b)` to explain the current thin path;
   - use `sources_for_entity(slug)` / `entities_for_source(source_id)` to show which documents ground the bridge and whether it rests on one source or several;
   - use `get_body(slug)` only at the end to let the LLM read the relevant endpoint/bridge bodies and generate one synthesis prompt: "Write a note connecting A and B through C" or "Find a source that tests whether A implies B."

4. **Horizon**  
   1.0-now. It only needs the existing Entity/Source/Domain graph, link/support/domain edges, and built analytics. The 2.0 Claim layer would later upgrade the output from "bridge opportunity" to "bridge plus tension/contradiction audit," but the killer app does not wait for Claims.

5. **Why it's the highest-value one**  
   It turns the graph from a retrieval surface into a thinking instrument. The user repeatedly wants to know not just "what did I capture?" but "what is my corpus trying to become?" This app surfaces the places where the user's reading has almost formed a new idea but has not yet been consolidated: the sparse bridges between investing and psychology, AI systems and personal productivity, health data and habit design, or any other latent pair. It creates writing prompts, research prompts, and ingestion priorities from the structure of the user's own knowledge, which is exactly the kind of metacognitive/generative value a personal graph can provide and lexical search cannot.

6. **Runner-up**  
   "Belief Tension Radar" — once 2.0 Claims are populated, ask: "Which active beliefs in my vault are contradicted, superseded, or weakly evidenced, and what should I revise?"

# GraphDB Viewer Bake-off (#97)

Render-only comparison of single-file, self-contained HTML knowledge-graph
viewers built by each panel model from one shared data export. Winner gets
promoted to a `kdb-graph-view` CLI. Judged against the rubric in
`docs/superpowers/specs/2026-05-30-graphdb-viewer-bakeoff-design.md` plus the
Opus baseline (`tools/kdb_graph_viewer-opus.py`).

## Two-stage pipeline

```
Kuzu GraphDB ──(export_graph.py)──► graph-export-run3.json ──(builder)──► kdb-graph-viewer-<model>.html
   read-only                          library-neutral data           one self-contained file
```

Every candidate shares **one** data file, so the comparison is render-only:
the only variable is how each model turns the same nodes/edges into HTML.

## Stage 1 — export the graph to neutral JSON (`export_graph.py`)

Read-only Kuzu dump → `{nodes, edges, summary}` JSON. Both args required.

```bash
python3 tools/viewer-bakeoff/export_graph.py \
  --graph-path ~/Obsidian/Vault-in-place-test-run/KDB/graph \
  --out tools/viewer-bakeoff/graph-export-run3.json
```

JSON shape:

```json
{ "nodes": [{"id":"...", "type":"Source|Entity|Domain|Claim",
             "name":"display name", "props":{ ... }}],
  "edges": [{"id":"...", "source":"<node id>", "target":"<node id>",
             "type":"LINKS_TO|SUPPORTS|BELONGS_TO|ALIAS_OF|..."}],
  "summary": {"node_types":{...}, "edge_types":{...}} }
```

The committed `graph-export-run3.json` is the **run-3** snapshot
(211 nodes / 653 edges — Source 29 / Entity 178 / Domain 4;
LINKS_TO 439 / SUPPORTS 185 / BELONGS_TO 29). Re-run Stage 1 only to refresh
against a newer compile — note that changes the data under every candidate.

## Stage 2 — build a candidate HTML from the JSON

Each builder reads `graph-export-run3.json` and inlines it into a template,
producing one double-click-to-open `.html` (CDN libs only, no server, no build).

| Model    | Builder            | Template source            | Invocation |
|----------|--------------------|----------------------------|------------|
| deepseek | `build_viewer.py`  | embedded in the script     | `--data … --out …` |
| qwen     | `build_qwen.py`    | `qwen_template.html`       | no args (paths hardcoded) |
| gemini   | `build_gemini.py`  | `gemini_template.html`     | no args (paths hardcoded) |
| codex    | *(none)*           | agent-authored HTML        | dropped in directly |
| grok     | *(none)*           | agent-authored HTML        | dropped in directly |

```bash
# deepseek — generic builder, explicit paths:
python3 tools/viewer-bakeoff/build_viewer.py \
  --data tools/viewer-bakeoff/graph-export-run3.json \
  --out  tools/viewer-bakeoff/kdb-graph-viewer-deepseek.html

# qwen / gemini — template-replace, no args:
python3 tools/viewer-bakeoff/build_qwen.py
python3 tools/viewer-bakeoff/build_gemini.py
```

`build_qwen.py` replaces the placeholder `/*__GRAPH_DATA__*/null/*__END__*/`;
`build_gemini.py` replaces `/*__GRAPH_DATA__*/`. **codex** and **grok** have no
local builder — those HTML files were authored directly by the agent and only
need re-dispatching (via `DISPATCH-PROMPT.md`) to regenerate.

## Generating a fresh round for new candidates

1. Hand `DISPATCH-PROMPT.md` to each model (replace `<MODEL>`), fire independently.
2. Each returns `kdb-graph-viewer-<MODEL>.html` into this directory (output-only
   guardrail: it must not touch any other repo file).
3. For models that ship a template instead of a finished file, drop the template
   here and add/run a `build_<model>.py` sibling.

## Open a built viewer (WSL → Windows browser)

```bash
explorer.exe "$(wslpath -w tools/viewer-bakeoff/kdb-graph-viewer-deepseek.html)"
```

## Files

| File                          | Role |
|-------------------------------|------|
| `export_graph.py`             | Stage 1 — Kuzu → neutral JSON |
| `graph-export-run3.json`      | shared input data (run-3 snapshot) |
| `build_viewer.py`             | deepseek builder (template embedded) |
| `build_qwen.py` + `qwen_template.html`     | qwen builder |
| `build_gemini.py` + `gemini_template.html` | gemini builder |
| `kdb-graph-viewer-*.html`     | the candidate viewers being judged |
| `DISPATCH-PROMPT.md`          | copy-paste brief sent to each model |

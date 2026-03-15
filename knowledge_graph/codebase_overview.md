# Codebase Overview — Vault Knowledge Graph System

> Last updated: 2026-03-14
> Author: Generated via Cowork / Claude
> Files: `generate_knowledge_graph.py` · `codebase_overview.md`
> Repo: `/home/ftu/Code-projects/obsidian-knowledge-graph/`

---

## 1. What This System Does

Every time you run `python3 generate_knowledge_graph.py` from any directory, it:

1. Locates your vault via `--vault <path>` flag or `OBSIDIAN_VAULT_PATH` environment variable (fails loudly if neither is set)
2. Scans every `.md` file across all 19+ folders in your vault
3. Extracts keywords, Obsidian wikilinks (`[[...]]`), inline tags (`#tag`), and YAML frontmatter tags from each file
4. Aggregates that data at the **folder level** (folders are the nodes, not individual notes)
5. Computes two types of edges between folders: wikilink connections and keyword-similarity connections
6. Writes `knowledge_graph.html` to the **current working directory** (not inside the vault)
7. Spins up a localhost HTTP server, opens the graph in your browser automatically

The HTML file is a **snapshot** — it captures the state of your vault at the moment the script runs. To refresh it, simply rerun the script. The server runs until you press `Ctrl+C`.

---

## 2. Architecture Overview

The system has three layers, each with a clear responsibility:

```
┌─────────────────────────────────────────────────────────────────┐
│  Layer 1 — Python Scanner (generate_knowledge_graph.py)         │
│  Reads the vault, extracts structure, computes graph data        │
└────────────────────────────┬────────────────────────────────────┘
                             │  JSON nodes + links arrays
┌────────────────────────────▼────────────────────────────────────┐
│  Layer 2 — HTML Template (generate_html function)               │
│  Injects JSON data into a static HTML shell                     │
└────────────────────────────┬────────────────────────────────────┘
                             │  Standalone .html file
┌────────────────────────────▼────────────────────────────────────┐
│  Layer 3 — D3.js Visualisation (inside Knowledge Graph.html)    │
│  Force-directed graph, interactivity, filtering, tooltips       │
└─────────────────────────────────────────────────────────────────┘
```

Each layer is intentionally independent. The Python scanner knows nothing about D3. The HTML knows nothing about the vault. You can improve any layer without touching the others.

---

## 3. Layer 1 — The Python Scanner

### 3.1 Entry Point and Configuration

```python
VAULT_PATH  = _resolve_vault()          # from --vault flag or OBSIDIAN_VAULT_PATH env var
OUTPUT_FILE = Path.cwd() / "knowledge_graph.html"
SKIP_DIRS   = {".obsidian", ".trash", ".git", "Stock Images", "__pycache__"}
```

`VAULT_PATH` is resolved via `_resolve_vault()` which checks (in order): `--vault <path>` CLI flag, then `OBSIDIAN_VAULT_PATH` environment variable. If neither is set, the script exits immediately with a clear error message — there is no silent fallback to the script's directory. This prevents the confusing "1 note found" failure mode that occurred when the script was run from the wrong location.

`OUTPUT_FILE` always writes to the **current working directory**, keeping the vault clean. Run the script from whatever directory you want the HTML to land in.

`SKIP_DIRS` prevents hidden Obsidian system folders, binary-heavy folders, and Python cache dirs from polluting keyword extraction.

### 3.2 The Scan Pipeline: `scan_vault()`

This is the core function. It makes a single pass through all `.md` files and builds a per-folder accumulator:

```
For each .md file:
  → determine top-level folder (parts[0], or "Root" for vault-level files)
  → read content
  → extract_keywords()       → raw term frequency, top 30 words
  → extract_wikilinks()      → [[target]] and [[target|alias]] patterns
  → extract_tags()           → inline #hashtags (skips code blocks)
  → extract_frontmatter_tags() → YAML tags: [...] or - list format
  → accumulate into folder Counter
  → record file stem → folder mapping (for wikilink resolution)
```

After the pass, it runs two post-processing steps:

**Step A — Keyword finalisation (dual representation):**
The raw keyword Counter is kept as `keywords_raw` (top 40 words) for similarity detection. A second list, `keywords` (top 8), is computed using TF-IDF for display labels. This split is critical — see Section 4.1 for why.

**Step B — Edge detection:**
Two independent algorithms compute the edges:
- **Wikilink edges**: resolved by exact stem match then prefix fallback
- **Keyword overlap edges**: set intersection on `keywords_raw`, minimum score of 2

### 3.3 Keyword Extraction: Two-Stage Design

**Stage 1 — `extract_keywords()` (per file, raw TF)**
Strips code blocks and URLs, removes punctuation, filters stop words and short words (< 5 chars), returns top-N by raw frequency. This runs per file and feeds the folder-level Counter accumulation.

**Stage 2 — `tfidf_keywords()` (per folder, TF-IDF)**
Scores each word as `TF × IDF` where:
- `TF` = word frequency in this folder / total words in this folder
- `IDF` = log((N+1) / (df+1)) + 1, where N = number of folders, df = how many folders contain this word

The +1 smoothing prevents zero division on rare words. The result gives you words that are frequent in this folder but rare across other folders — i.e., genuinely distinctive vocabulary. This is what makes labels like `coffin, heathcliff, linton` appear for Literature rather than generic words like `great, world`.

**Why two stages instead of one?**
TF-IDF maximises distinctiveness — by design, it penalises words that appear in many folders. If you used TF-IDF for overlap detection too, you'd get zero cross-folder matches because the algorithm has eliminated exactly the shared vocabulary you need. The solution is to run TF-IDF for display only, and use raw top-40 frequency for overlap detection.

### 3.4 Wikilink Resolution

Obsidian wikilinks (`[[Note Title]]`) reference note filenames, not folders. The resolver maps stems to folders in two passes:

1. **Exact match**: lowercase stem → folder lookup
2. **Prefix fallback**: if the first 6 characters of the target appear in any stem (bidirectional)

The prefix fallback catches partial note titles and common truncations. Edges are de-duplicated by normalising to a sorted tuple `(folder_a, folder_b)` and counting occurrences. Edges with count ≥ 3 are rendered as `strong`, others as `normal`.

### 3.5 The Manual Layers

Two data structures in the script are **intentionally hand-curated** and not auto-detected:

**`MANUAL_CONCEPTS`** — Cross-cutting philosophical themes (Circle of Competence, Compounding, Feedback Loops, Bias Mitigation, Margin of Safety). These represent the insight that the same mental model is operating simultaneously across your investing notes and your AI/ML notes. No frequency analysis can detect this — it requires reading comprehension.

**`MANUAL_GAPS`** — Knowledge gaps and missing links (Outcome Calibration, Live Portfolio, Deployed System, Eval Framework, Security, Peak Performance). Gaps by definition have no files to scan. They must be asserted, not discovered. These are the places where your vault is telling you something is designed but not built, or researched but not applied.

Both lists can be edited directly in the script to add new concepts or gaps as your vault evolves.

---

## 4. Design Decisions and Rationale

### 4.1 Why folders as nodes, not individual files?

With 161 notes, a file-level graph would have 161 nodes and potentially hundreds of edges — too dense to read. Folder-level aggregation preserves the meaningful structure (your own intentional categorisation) while keeping the graph readable. The file count shown on each node (`69f` for Value Investing) gives you the density signal without the visual noise.

### 4.2 Why no external NLP libraries?

Zero dependencies beyond Python stdlib. No NLTK, spaCy, or sentence-transformers. Rationale: you can run this script on any machine with Python 3.10+ installed, on any OS, in any environment — including offline. The tradeoff is shallower semantics (keyword overlap, not embedding similarity), but the results are interpretable and debuggable. You can read a shared keyword and immediately understand why two folders are connected.

### 4.3 Why a self-contained HTML file?

The output is a single file you can open by double-clicking, email to someone, or commit to git. There is no server, no Node.js runtime, no build step. D3.js is loaded from a CDN via a `<script>` tag. The graph data (nodes and links) is embedded as JSON constants directly in the `<script>` block. This means the file works even without internet access once loaded (D3 is cached by the browser).

### 4.4 Why D3.js force-directed layout?

Force-directed graphs are self-organising — highly connected nodes cluster together, loosely connected ones drift apart. This means the spatial layout itself is informative: the cluster of AI/ML, MISC, and concept nodes near the centre reflects genuine structural centrality, not manual placement. You did not design the layout; the data did.

### 4.5 Why separate `keywords_raw` and `keywords` (TF-IDF)?

This was the most important bug fixed during development. Initial implementation used TF-IDF for everything and found zero keyword-overlap edges — because TF-IDF specifically eliminates shared vocabulary. The fix was to maintain two representations: distinctive labels for display (TF-IDF, top 8) and broad vocabulary for similarity detection (raw TF, top 40). The number 40 was chosen to give enough shared signal without including pure noise words.

### 4.6 Why a minimum overlap threshold of 2?

Threshold of 1 produces false-positive edges from coincidental single-word matches. Threshold of 3 missed real connections (as tested). Threshold of 2 with minimum word length of 5 characters (enforced in `extract_keywords`) strikes the right balance: reduces coincidental matches while catching genuine thematic overlap.

### 4.7 Why are concepts and gaps hardcoded instead of auto-detected?

Concepts like "Margin of Safety" require semantic understanding that string matching cannot provide — the phrase appears very differently in investing contexts ("position sizing", "downside protection") versus engineering contexts ("debuggability", "PostgreSQL over Neo4j"). A frequency model would never connect these. Similarly, gaps require knowing what is *absent*, which is fundamentally not computable from the text that is present. Both are deliberately kept as editable human-curated layers.

---

## 5. Layer 3 — The D3.js Visualisation

The HTML file is a standalone interactive application. Key implementation choices:

**Force simulation parameters:**
- Folder nodes have a repulsion strength of -650 (stronger push, prevents overlap)
- Concept/gap nodes use -320 (softer, allows clustering near related folders)
- Link distance varies by type: strong=110px, weak=220px, gap=140px, concept=155px
- Collision radius = `node.size * 2 + 14` (prevents label overlap)

**Node sizing:** `max(12, min(32, 10 + log(file_count + 1) * 5))` — logarithmic scale so that the difference between 1-file and 5-file folders is visible but a 70-file folder doesn't dwarf everything else.

**Interaction model:**
- Hover → tooltip with description, tags, live connection list
- Click → ego-network highlight (dims all non-adjacent nodes to 12% opacity)
- Click again → reset highlight
- Filter buttons → category-based opacity filter (concepts always visible)
- Reset → restores all opacity and recentres zoom

**Link rendering:** Five CSS classes (`strong`, `normal`, `weak`, `gap`, `concept`) control stroke weight, opacity, and dash pattern. Gap links use dashed red; concept links use dashed amber; wikilinks render as solid blue. The visual grammar makes it immediately clear which connections are hard (wikilinks), inferred (keyword overlap), philosophical (concepts), or missing (gaps).

---

## 5.5 Layer 4 — The Localhost Server (`serve()`)

After writing the HTML file, the script automatically starts a minimal HTTP server and opens the graph in the browser. This replaces the previous workflow of manually navigating to and double-clicking the HTML file inside the vault.

**Why a server instead of `file://`?** D3.js works fine with `file://` for static assets, but a server makes future enhancements (live reload, API calls, CORS) trivially easy without changing the viewer.

**Implementation:**
- `_free_port()` binds to port 0 and reads back the OS-assigned port — guaranteed available, no hardcoded port collisions
- `http.server.HTTPServer` with a custom handler that serves from the HTML file's parent directory
- Server runs in a daemon thread so `Ctrl+C` on the main thread terminates everything cleanly
- `_open_browser()` uses `explorer.exe` (WSL → Windows browser) with fallback to `webbrowser.open()`

---

## 6. What Auto-Updates vs. What You Maintain

| Component | Updates automatically on each run | Requires manual edit |
|---|---|---|
| Folder nodes | ✅ New folders detected | — |
| File counts and word counts | ✅ Live from vault | — |
| TF-IDF display labels (tags) | ✅ Reflects current note content | — |
| Wikilink edges | ✅ Parsed fresh each run | — |
| Keyword overlap edges | ✅ Recomputed each run | — |
| Node size (proportional to files) | ✅ Auto-scales | — |
| Cross-cutting concept nodes | — | Edit `MANUAL_CONCEPTS` in script |
| Gap nodes | — | Edit `MANUAL_GAPS` in script |
| Folder → category mapping | — | Edit `FOLDER_CATEGORIES` in script |
| Folder exclusions | — | Edit `SKIP_DIRS` in script |

---

## 7. How to Extend the System

**Add a new gap:** Edit `MANUAL_GAPS` in the script. Each entry needs `id`, `label`, `desc`, `tags`, and `connects_to` (list of folder names to link to).

**Add a new concept:** Edit `MANUAL_CONCEPTS` the same way.

**Reclassify a folder** (e.g., move MISC from "ai" to "reference"): Edit `FOLDER_CATEGORIES`.

**Change keyword sensitivity:** Adjust the overlap threshold (`score >= 2`) in `scan_vault()`, or change the broad keyword set size (currently `top_n=40` in `raw_keywords_broad`).

**Add a new folder to the vault:** No action needed. It will be auto-detected on the next run and classified as "reference" unless you add it to `FOLDER_CATEGORIES`.

**Add wikilinks to your notes:** Any `[[Note Title]]` you add in Obsidian will be picked up automatically on the next run and converted to an edge if the target resolves to a different folder.

---

## 8. Known Limitations

**Wikilink resolution is approximate.** The prefix fallback can produce false positives if two very different note titles share a 6-character prefix. Exact-match resolution is reliable; prefix-match is a best-effort heuristic.

**Keyword overlap is lexical, not semantic.** "Investment" and "investing" are treated as different words. Morphological variants, synonyms, and conceptual equivalents are not detected. Adding a stemmer (e.g., Porter stemmer, pure Python, no dependencies) would improve recall.

**The "Root" node** contains files at the vault root level — it is a catch-all, not a real category. These files could be moved into appropriate folders to eliminate this node.

**No incremental updates.** The script always does a full rescan. For a 161-note vault this takes under a second. If the vault grows to thousands of notes, a file-modification-time cache would be worth adding.

**The HTML is a snapshot, not a live feed.** The graph does not watch the vault for changes. This is intentional (simplicity, offline capability) but means you must rerun the script after significant note-taking sessions.

---

## 9. File Inventory

```
~/Code-projects/obsidian-knowledge-graph/
├── generate_knowledge_graph.py   ← Run this from any directory
└── codebase_overview.md          ← This document

# Output (generated on demand, NOT committed to repo):
<cwd>/
└── knowledge_graph.html          ← Written to wherever you run the script from
```

The script is intentionally decoupled from both the vault and the output location. The vault is read-only input; the HTML is ephemeral output. Neither is stored in the script's own directory.

---

## 10. Quick Reference

```bash
# Prerequisites: OBSIDIAN_VAULT_PATH must be set in your shell (it is in .bashrc)
echo $OBSIDIAN_VAULT_PATH   # should print vault path

# Run from any directory — HTML output lands in CWD, browser opens automatically
cd ~/Desktop   # or wherever you want the HTML
python3 ~/Code-projects/obsidian-knowledge-graph/generate_knowledge_graph.py

# Override vault path on the fly
python3 ~/Code-projects/obsidian-knowledge-graph/generate_knowledge_graph.py \
  --vault "/mnt/c/Users/fangq/OneDrive/Documents/Obsidian Vault"

# Expected output
🔍  Scanning vault: /mnt/c/Users/fangq/OneDrive/Documents/Obsidian Vault
✅  Found 200+ notes across 19 folders
    Wikilink edges: 1
    Keyword-overlap edges: 13
🔗  Building graph data…
    Nodes: 30  |  Links: 38
🖊️   Writing → /home/ftu/Desktop/knowledge_graph.html

🌐  Serving at http://localhost:8432/knowledge_graph.html
    Press Ctrl+C to stop.
```

The browser opens automatically. Press `Ctrl+C` to stop the server when done.

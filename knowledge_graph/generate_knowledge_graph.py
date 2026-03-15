#!/usr/bin/env python3
"""
Vault Knowledge Graph Generator
================================
Scans your entire Obsidian Vault, extracts structure, wikilinks,
tags, and keyword overlaps, then writes a fresh interactive
Knowledge Graph.html every time it runs.

Usage:
    python generate_knowledge_graph.py
    python generate_knowledge_graph.py --vault "/path/to/Obsidian Vault"
    OBSIDIAN_VAULT_PATH="/path/to/vault" python generate_knowledge_graph.py
"""

import os, re, json, math, string, argparse, socket, threading, time
import http.server
from pathlib import Path
from collections import defaultdict, Counter

# ── CONFIG ────────────────────────────────────────────────────────────────────
def _resolve_vault() -> Path:
    parser = argparse.ArgumentParser(description="Obsidian Vault Knowledge Graph Generator")
    parser.add_argument("--vault", default=os.environ.get("OBSIDIAN_VAULT_PATH"),
                        help="Path to Obsidian vault (or set OBSIDIAN_VAULT_PATH env var)")
    args, _ = parser.parse_known_args()
    if args.vault:
        return Path(args.vault)
    print("❌  No vault path found.")
    print("    Set OBSIDIAN_VAULT_PATH in your shell or pass --vault <path>")
    print("    Example: python3 generate_knowledge_graph.py --vault '/path/to/Obsidian Vault'")
    raise SystemExit(1)

VAULT_PATH  = _resolve_vault()
OUTPUT_FILE = Path.cwd() / "knowledge_graph.html"

# Folders to skip entirely
SKIP_DIRS = {".obsidian", ".trash", ".git", "Stock Images", "__pycache__"}

# Manually curated gaps (conceptual — can't be auto-detected from text alone)
MANUAL_GAPS = [
    {
        "id": "gap-outcomes",
        "label": "⚠️ Outcome\nCalibration",
        "desc": "GAP: The thesis_outcomes table is designed in GraphRAG but no live calibration queries exist. Without closing this feedback loop, the system can't learn which information sources actually predicted returns.",
        "tags": ["Critical Gap", "Feedback Loop", "Calibration"],
        "connects_to": ["AI-ML", "Value Investing"]
    },
    {
        "id": "gap-portfolio",
        "label": "⚠️ Live\nPortfolio",
        "desc": "GAP: No systematic record of current positions, thesis status, or monitoring triggers. Rich investment philosophy but no operational tracking layer.",
        "tags": ["Gap", "Portfolio Tracking", "Position Monitoring"],
        "connects_to": ["Value Investing", "Equity Research"]
    },
    {
        "id": "gap-deployment",
        "label": "⚠️ Deployed\nSystem",
        "desc": "GAP: GraphRAG architecture is detailed but no deployed instance is documented. Phase 2 baseline evaluation (20 newsletters) appears not yet started.",
        "tags": ["Gap", "Implementation", "Phase 2"],
        "connects_to": ["AI-ML"]
    },
    {
        "id": "gap-eval",
        "label": "⚠️ Eval\nFramework",
        "desc": "GAP: Multiple LLMs compared (GPT-5.2, Gemini 3.1, Grok 4.2, Opus 4.6) qualitatively, but no quantitative evaluation harness or benchmark suite.",
        "tags": ["Gap", "LLM Evaluation", "Benchmarking"],
        "connects_to": ["AI-ML"]
    },
    {
        "id": "gap-security",
        "label": "⚠️ Security &\nIP Protection",
        "desc": "GAP: Data security and IP protection for the proprietary investment system is mentioned but barely specified — local embedding models, data retention policies need fleshing out.",
        "tags": ["Gap", "Security", "Privacy"],
        "connects_to": ["AI-ML", "FuZlogicX LLC"]
    },
    {
        "id": "gap-health-perf",
        "label": "⚠️ Peak\nPerformance",
        "desc": "GAP: Health & Wellbeing notes exist but aren't connected to cognitive performance or investor decision quality. No notes on sleep hygiene for complex analysis or stress during volatility.",
        "tags": ["Gap", "Cognitive Performance", "Decision Quality"],
        "connects_to": ["Life-Health-Well-being", "Value Investing"]
    },
]

# Manually curated cross-cutting concepts
MANUAL_CONCEPTS = [
    {
        "id": "Circle of Competence",
        "label": "Circle of\nCompetence",
        "desc": "Appears in Buffett/Pabrai notes AND GraphRAG design (Too Hard Pile as first-class asset). The cognitive boundary of what you know vs. don't know.",
        "tags": ["Munger", "Too Hard Pile", "Self-Awareness"],
        "connects_to": ["Value Investing", "AI-ML"]
    },
    {
        "id": "Compounding",
        "label": "Compounding\nKnowledge",
        "desc": "Delta-first learning in GraphRAG mirrors compounding returns in investing. Only net-new information/returns compound. Core philosophy across vault.",
        "tags": ["Delta-First", "Returns", "Knowledge Systems"],
        "connects_to": ["AI-ML", "Value Investing", "Retirement"]
    },
    {
        "id": "Feedback Loops",
        "label": "Feedback\nLoops",
        "desc": "Thesis outcomes table (GraphRAG), field validation (telecom capacity planning), investment return calibration. The mechanism that makes systems self-improving.",
        "tags": ["Calibration", "Outcome Tracking", "Self-Improvement"],
        "connects_to": ["AI-ML", "Value Investing"]
    },
    {
        "id": "Bias Mitigation",
        "label": "Bias\nMitigation",
        "desc": "Anti-sycophancy prompts (AI), Taleb/IQ critique (statistics), Pabrai checklist (investing). A coherent anti-bias philosophy running across domains.",
        "tags": ["Anti-Sycophancy", "Statistical Bias", "Checklist"],
        "connects_to": ["AI-ML", "Value Investing"]
    },
    {
        "id": "Margin of Safety",
        "label": "Margin of\nSafety",
        "desc": "Buffett's investment principle applied to engineering (PostgreSQL over Neo4j), retirement (4x LTC buffer), and GraphRAG design (phases with standalone value).",
        "tags": ["Buffett", "Engineering", "Retirement"],
        "connects_to": ["Value Investing", "AI-ML", "Retirement"]
    },
]

# Category colour palette
CATEGORY_COLORS = {
    "ai":        "#1f6feb",
    "investing": "#3fb950",
    "personal":  "#f78166",
    "reference": "#d2a8ff",
    "concept":   "#e3b341",
    "gap":       "#f85149",
}

# Folder → category mapping (auto-extended for unknown folders)
FOLDER_CATEGORIES = {
    "AI-ML":                    "ai",
    "MISC":                     "ai",
    "Value Investing":          "investing",
    "Equity Research":          "investing",
    "Retirement":               "personal",
    "FuZlogicX LLC":            "personal",
    "Notes":                    "personal",
    "Ideas":                    "personal",
    "Daily Notes":              "personal",
    "Projects":                 "personal",
    "Life-Health-Well-being":   "personal",
    "Food and Drinks":          "personal",
    "Science and Technology":   "reference",
    "History":                  "reference",
    "Quotes":                   "reference",
    "Literature":               "reference",
    "Info to Remember":         "reference",
    "WSL-Ubuntu-Linux-Git":     "reference",
}

# English stop words (lightweight, no NLTK needed)
STOP_WORDS = set("""
a about above after again against all also am an and any are aren't as at
be because been before being below between both but by can't cannot could
couldn't did didn't do does doesn't doing don't down during each few for
from further get got had hadn't has hasn't have haven't having he he'd he'll
he's her here here's hers herself him himself his how how's i i'd i'll i'm
i've if in into is isn't it it's its itself let's me more most mustn't my
myself no nor not of off on once only or other ought our ours ourselves out
over own same shan't she she'd she'll she's should shouldn't so some such
than that that's the their theirs them themselves then there there's these
they they'd they'll they're they've this those through to too under until up
very was wasn't we we'd we'll we're we've were weren't what what's when
when's where where's which while who who's whom why why's will with won't
would wouldn't you you'd you'll you're you've your yours yourself yourselves
also can get just like make one may use used using will well now can also
its the a an using used being this that these those s t re ll ve d m
time years think know going people really things want need good back work
way take look even still much come made going well start something first
second third new same many kind different right thing every always never
often sometimes perhaps maybe actually quite rather already better best
less note notes see section example below table figure page just really
very whether following here should would could may might done said given
able given since long high small large number amount level true false
need want look things work section above whether going make sure
""".split())

# ── SCANNER ───────────────────────────────────────────────────────────────────

def extract_keywords(text: str, top_n: int = 20) -> list[str]:
    """Extract top keywords using raw TF (per-file). IDF weighting done at folder level."""
    text = text.lower()
    text = re.sub(r'```.*?```', ' ', text, flags=re.DOTALL)
    text = re.sub(r'http\S+', ' ', text)
    text = re.sub(r'[^a-z\s\-]', ' ', text)
    words = [w.strip('-') for w in text.split()
             if len(w) > 4 and w not in STOP_WORDS and not w.startswith('-')]
    freq = Counter(words)
    return [w for w, _ in freq.most_common(top_n)]


def tfidf_keywords(folder_word_counts: dict[str, Counter], folder_name: str, top_n: int = 8) -> list[str]:
    """Score keywords by TF-IDF: high frequency in THIS folder, low in others."""
    num_folders = len(folder_word_counts)
    this_counts  = folder_word_counts[folder_name]
    total_this   = sum(this_counts.values()) or 1

    scores = {}
    for word, count in this_counts.items():
        if len(word) < 4:
            continue
        tf  = count / total_this
        # How many folders contain this word?
        df  = sum(1 for fc in folder_word_counts.values() if word in fc)
        idf = math.log((num_folders + 1) / (df + 1)) + 1
        scores[word] = tf * idf

    return [w for w, _ in sorted(scores.items(), key=lambda x: -x[1])[:top_n]]


def extract_wikilinks(text: str) -> list[str]:
    """Extract [[wikilinks]] and [[link|alias]] patterns."""
    raw = re.findall(r'\[\[([^\]]+)\]\]', text)
    targets = []
    for r in raw:
        # Handle aliases: [[target|display]]
        targets.append(r.split('|')[0].strip())
    return targets


def extract_tags(text: str) -> list[str]:
    """Extract #tags from content (not inside code blocks)."""
    clean = re.sub(r'```.*?```', ' ', text, flags=re.DOTALL)
    return list(set(re.findall(r'#([a-zA-Z][a-zA-Z0-9_-]+)', clean)))


def extract_frontmatter_tags(text: str) -> list[str]:
    """Extract tags from YAML frontmatter."""
    match = re.match(r'^---\s*\n(.*?)\n---', text, re.DOTALL)
    if not match:
        return []
    fm = match.group(1)
    tag_line = re.search(r'tags:\s*\[([^\]]+)\]', fm)
    if tag_line:
        return [t.strip().strip('"\'') for t in tag_line.group(1).split(',')]
    tag_lines = re.findall(r'^\s*-\s+(.+)$', fm, re.MULTILINE)
    return [t.strip() for t in tag_lines]


def scan_vault(vault_path: Path) -> dict:
    """
    Scan vault and return structured data:
      folders: {name: {files, keywords, tags, wikilinks, category, subfolder_count}}
      wikilink_edges: [(source_folder, target_folder, count)]
    """
    folders = {}
    all_wikilinks = []   # (source_folder, target_name)
    file_to_folder = {}  # md stem → folder name (for resolving wikilinks)

    for md_file in sorted(vault_path.rglob("*.md")):
        # Skip hidden/excluded dirs
        parts = md_file.relative_to(vault_path).parts
        if any(p.startswith('.') or p in SKIP_DIRS for p in parts):
            continue

        # Determine top-level folder
        if len(parts) == 1:
            folder_name = "Root"
        else:
            folder_name = parts[0]

        # Read content
        try:
            content = md_file.read_text(encoding='utf-8', errors='ignore')
        except Exception:
            continue

        # Accumulate folder data
        if folder_name not in folders:
            folders[folder_name] = {
                "files": 0,
                "keywords": Counter(),
                "tags": set(),
                "wikilinks_out": [],
                "subfolders": set(),
                "word_count": 0,
                "file_names": [],
            }

        fd = folders[folder_name]
        fd["files"] += 1
        fd["word_count"] += len(content.split())
        fd["file_names"].append(md_file.stem)

        # Track subfolders
        if len(parts) > 2:
            fd["subfolders"].add(parts[1])

        # Keywords
        kws = extract_keywords(content, top_n=30)
        fd["keywords"].update(kws)

        # Tags
        fd["tags"].update(extract_tags(content))
        fd["tags"].update(extract_frontmatter_tags(content))

        # Wikilinks
        links = extract_wikilinks(content)
        fd["wikilinks_out"].extend(links)
        all_wikilinks.extend([(folder_name, t) for t in links])

        # Map file stem to folder for resolution
        file_to_folder[md_file.stem.lower()] = folder_name

    # Build per-folder raw word Counter map (keep Counters intact for similarity)
    folder_word_counts = {name: Counter(fd["keywords"]) for name, fd in folders.items()}

    # Compute keyword overlap edges BEFORE converting keywords to display labels
    # Use raw top-N words (broad set) for overlap detection
    raw_keywords_broad = {}
    for name, counter in folder_word_counts.items():
        raw_keywords_broad[name] = set(w for w, _ in counter.most_common(40))

    # Finalize folder keyword lists: TF-IDF for display labels, raw for overlap
    for name, fd in folders.items():
        fd["keywords"]     = tfidf_keywords(folder_word_counts, name, top_n=8)
        fd["keywords_raw"] = raw_keywords_broad[name]   # kept for overlap detection
        fd["tags"]         = sorted(fd["tags"])[:8]
        fd["subfolders"]   = len(fd["subfolders"])

    # ── Resolve wikilink edges ──────────────────────────────────────────────
    edge_counts = defaultdict(int)
    for src_folder, target_name in all_wikilinks:
        # Try to resolve target to a folder
        target_lower = target_name.lower()
        resolved = file_to_folder.get(target_lower)
        if not resolved:
            # Try prefix match
            for stem, fld in file_to_folder.items():
                if stem.startswith(target_lower[:6]) or target_lower[:6] in stem:
                    resolved = fld
                    break
        if resolved and resolved != src_folder:
            key = tuple(sorted([src_folder, resolved]))
            edge_counts[key] += 1

    wikilink_edges = [
        {"source": k[0], "target": k[1], "count": v}
        for k, v in edge_counts.items() if v > 0
    ]

    # ── Keyword overlap edges ───────────────────────────────────────────────
    folder_names = [f for f in folders if folders[f]["files"] > 0]
    keyword_edges = []
    for i, f1 in enumerate(folder_names):
        for f2 in folder_names[i+1:]:
            kw1 = folders[f1]["keywords_raw"]
            kw2 = folders[f2]["keywords_raw"]
            overlap = kw1 & kw2
            score = len(overlap)
            if score >= 2:  # minimum overlap threshold
                keyword_edges.append({
                    "source": f1, "target": f2,
                    "score": score,
                    "shared": sorted(overlap)[:5]
                })

    return {
        "folders": folders,
        "wikilink_edges": wikilink_edges,
        "keyword_edges": keyword_edges,
        "total_files": sum(fd["files"] for fd in folders.values()),
        "vault_path": str(vault_path),
    }


# ── GRAPH BUILDER ─────────────────────────────────────────────────────────────

def build_graph_data(scan: dict) -> tuple[list, list]:
    """Convert scan results into D3-ready nodes and links."""
    folders = scan["folders"]
    nodes = []
    links = []
    node_ids = set()

    # ── Folder nodes ──────────────────────────────────────────────────────
    for name, fd in sorted(folders.items(), key=lambda x: -x[1]["files"]):
        if fd["files"] == 0:
            continue
        category = FOLDER_CATEGORIES.get(name, "reference")
        size = max(12, min(32, 10 + math.log(fd["files"] + 1) * 5))
        nodes.append({
            "id":       name,
            "label":    name.replace(" ", "\n", 1) if len(name) > 10 else name,
            "type":     "folder",
            "category": category,
            "size":     round(size, 1),
            "files":    fd["files"],
            "words":    fd["word_count"],
            "desc":     f"{fd['files']} notes · {fd['word_count']:,} words. "
                        f"Top topics: {', '.join(fd['keywords'][:5]) or 'n/a'}.",
            "tags":     fd["keywords"][:6],
        })
        node_ids.add(name)

    # ── Concept nodes ─────────────────────────────────────────────────────
    for c in MANUAL_CONCEPTS:
        if c["id"] not in node_ids:
            nodes.append({
                "id":       c["id"],
                "label":    c["label"],
                "type":     "concept",
                "category": "concept",
                "size":     15,
                "files":    0,
                "desc":     c["desc"],
                "tags":     c["tags"],
            })
            node_ids.add(c["id"])
        for target in c["connects_to"]:
            if target in node_ids:
                links.append({
                    "source": c["id"], "target": target,
                    "type": "concept", "color": CATEGORY_COLORS["concept"],
                    "label": ""
                })

    # ── Gap nodes ─────────────────────────────────────────────────────────
    for g in MANUAL_GAPS:
        nodes.append({
            "id":       g["id"],
            "label":    g["label"],
            "type":     "gap-node",
            "category": "gap",
            "size":     14,
            "files":    0,
            "desc":     g["desc"],
            "tags":     g["tags"],
        })
        node_ids.add(g["id"])
        for target in g["connects_to"]:
            if target in node_ids:
                links.append({
                    "source": g["id"], "target": target,
                    "type": "gap", "color": CATEGORY_COLORS["gap"],
                    "label": ""
                })

    # ── Wikilink edges ────────────────────────────────────────────────────
    for e in scan["wikilink_edges"]:
        if e["source"] in node_ids and e["target"] in node_ids:
            links.append({
                "source": e["source"], "target": e["target"],
                "type":  "strong" if e["count"] >= 3 else "normal",
                "color": "#58a6ff",
                "label": f"{e['count']} wikilinks"
            })

    # ── Keyword overlap edges ─────────────────────────────────────────────
    for e in sorted(scan["keyword_edges"], key=lambda x: -x["score"]):
        if e["source"] in node_ids and e["target"] in node_ids:
            # Don't duplicate wikilink edges
            already = any(
                (l["source"] in (e["source"], e["target"]) and
                 l["target"] in (e["source"], e["target"]))
                for l in links if l.get("type") in ("strong", "normal")
            )
            link_type = "normal" if e["score"] >= 6 else "weak"
            color = CATEGORY_COLORS.get(
                FOLDER_CATEGORIES.get(e["source"], "reference"), "#8b949e")
            links.append({
                "source": e["source"], "target": e["target"],
                "type":  link_type,
                "color": color,
                "label": f"shared: {', '.join(e['shared'][:3])}"
            })

    return nodes, links


# ── HTML TEMPLATE ─────────────────────────────────────────────────────────────

def generate_html(nodes: list, links: list, scan: dict) -> str:
    from datetime import datetime
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    total_files  = scan["total_files"]
    total_nodes  = len(nodes)
    total_links  = len([l for l in links if l["type"] != "gap"])
    total_gaps   = len([n for n in nodes if n["type"] == "gap-node"])

    nodes_json = json.dumps(nodes, indent=2)
    links_json = json.dumps(links, indent=2)
    colors_json = json.dumps(CATEGORY_COLORS)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Knowledge Graph — {generated_at}</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/d3/7.8.5/d3.min.js"></script>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ background:#0d1117; color:#e6edf3; font-family:'Segoe UI',system-ui,sans-serif; overflow:hidden; }}
#canvas {{ width:100vw; height:100vh; }}
.link {{ stroke-opacity:.45; stroke-width:1.5px; }}
.link.strong {{ stroke-width:2.5px; stroke-opacity:.7; }}
.link.weak   {{ stroke-width:1px; stroke-opacity:.2; stroke-dasharray:4,3; }}
.link.gap    {{ stroke-width:1.5px; stroke-opacity:.5; stroke-dasharray:6,4; }}
.link.concept{{ stroke-width:1.5px; stroke-opacity:.35; stroke-dasharray:3,3; }}
.node circle {{ cursor:pointer; transition:r .2s; }}
.node text   {{ pointer-events:none; fill:#c9d1d9; text-anchor:middle; dominant-baseline:central; }}
.node.gap-node > circle {{ animation:pulse 2s ease-in-out infinite; }}
@keyframes pulse {{ 0%,100%{{opacity:.55}} 50%{{opacity:1}} }}
#tooltip {{
  position:absolute; pointer-events:none;
  background:rgba(13,17,23,.97); border:1px solid #30363d;
  border-radius:10px; padding:14px 18px; max-width:320px;
  font-size:13px; line-height:1.6; box-shadow:0 8px 32px rgba(0,0,0,.6);
  display:none; z-index:100;
}}
#tooltip h3   {{ font-size:14px; font-weight:700; margin-bottom:6px; }}
#tooltip .tag {{ display:inline-block; padding:2px 8px; border-radius:12px; font-size:11px;
                 font-weight:600; margin-right:4px; margin-bottom:8px; }}
#tooltip p    {{ color:#8b949e; font-size:12px; }}
#tooltip .conn-list {{ margin-top:8px; }}
#tooltip .conn-list span {{ display:block; color:#58a6ff; font-size:12px; }}
#tooltip .gap-note {{ margin-top:8px; color:#f85149; font-size:12px; font-style:italic; }}
#legend {{
  position:absolute; bottom:24px; left:24px;
  background:rgba(13,17,23,.92); border:1px solid #30363d;
  border-radius:10px; padding:14px 18px; font-size:12px; min-width:195px;
}}
#legend h4 {{ font-size:13px; font-weight:700; margin-bottom:10px; color:#e6edf3; }}
.li {{ display:flex; align-items:center; gap:8px; margin-bottom:7px; color:#8b949e; }}
.dot {{ width:12px; height:12px; border-radius:50%; flex-shrink:0; }}
.dash-circle {{ width:12px; height:12px; border-radius:50%; border:2px dashed #f85149; flex-shrink:0; }}
.line-solid {{ width:24px; height:2px; flex-shrink:0; }}
.line-dash  {{ width:24px; height:0; border-top:2px dashed; flex-shrink:0; }}
#controls {{
  position:absolute; top:24px; right:24px;
  background:rgba(13,17,23,.92); border:1px solid #30363d;
  border-radius:10px; padding:14px 18px; font-size:12px;
}}
#controls h4 {{ font-size:13px; font-weight:700; margin-bottom:10px; color:#e6edf3; }}
.fbtn {{
  display:block; width:100%; text-align:left; padding:5px 10px;
  margin-bottom:4px; background:#161b22; border:1px solid #30363d;
  border-radius:6px; color:#8b949e; cursor:pointer; font-size:11px; transition:all .2s;
}}
.fbtn:hover,.fbtn.active {{ background:#1f6feb33; border-color:#1f6feb; color:#58a6ff; }}
#reset-btn {{
  margin-top:8px; display:block; width:100%; padding:6px 10px;
  background:#21262d; border:1px solid #30363d; border-radius:6px;
  color:#e6edf3; cursor:pointer; font-size:11px;
}}
#reset-btn:hover {{ background:#30363d; }}
#title {{ position:absolute; top:24px; left:24px; pointer-events:none; }}
#title h1 {{ font-size:18px; font-weight:700; color:#e6edf3; }}
#title p  {{ font-size:11px; color:#8b949e; margin-top:2px; }}
#stats {{
  position:absolute; bottom:24px; right:24px;
  background:rgba(13,17,23,.92); border:1px solid #30363d;
  border-radius:10px; padding:10px 16px; font-size:12px; color:#8b949e;
  display:flex; gap:20px;
}}
#stats span {{ font-weight:700; color:#e6edf3; }}
</style>
</head>
<body>
<div id="title">
  <h1>🧠 Knowledge Graph</h1>
  <p>Generated {generated_at} &nbsp;·&nbsp; {total_files} notes &nbsp;·&nbsp; scroll to zoom · drag to pan · hover nodes</p>
</div>
<svg id="canvas"></svg>
<div id="tooltip"></div>
<div id="legend">
  <h4>Legend</h4>
  <div class="li"><div class="dot" style="background:#1f6feb"></div>AI / ML</div>
  <div class="li"><div class="dot" style="background:#3fb950"></div>Investing</div>
  <div class="li"><div class="dot" style="background:#f78166"></div>Personal</div>
  <div class="li"><div class="dot" style="background:#d2a8ff"></div>Reference</div>
  <div class="li"><div class="dot" style="background:#e3b341"></div>Cross-cutting Concept</div>
  <div class="li"><div class="dash-circle"></div>Gap / Missing</div>
  <div style="margin-top:10px;border-top:1px solid #30363d;padding-top:10px;">
    <div class="li"><div class="line-solid" style="background:#58a6ff"></div>Wikilink</div>
    <div class="li"><div class="line-solid" style="background:#8b949e"></div>Keyword overlap</div>
    <div class="li"><div class="line-dash" style="border-color:#f85149"></div>Gap link</div>
  </div>
</div>
<div id="controls">
  <h4>Filter</h4>
  <button class="fbtn active" data-f="all">🌐 All Nodes</button>
  <button class="fbtn" data-f="ai">🤖 AI / ML</button>
  <button class="fbtn" data-f="investing">💰 Investing</button>
  <button class="fbtn" data-f="personal">🙋 Personal</button>
  <button class="fbtn" data-f="gaps">⚠️ Gaps Only</button>
  <button id="reset-btn">↺ Reset View</button>
</div>
<div id="stats">
  <div>Nodes <span>{total_nodes}</span></div>
  <div>Links <span>{total_links}</span></div>
  <div>Gaps <span>{total_gaps}</span></div>
  <div>Notes <span>{total_files}</span></div>
</div>
<script>
const NODES = {nodes_json};
const LINKS = {links_json};
const CAT_COLOR = {colors_json};

const svg   = d3.select("#canvas");
const W = window.innerWidth, H = window.innerHeight;
svg.attr("width", W).attr("height", H);
const g = svg.append("g");

const zoom = d3.zoom().scaleExtent([0.15,4])
  .on("zoom", e => g.attr("transform", e.transform));
svg.call(zoom);

// Arrow markers
svg.append("defs").selectAll("marker")
  .data(["normal","strong","weak","gap","concept"])
  .join("marker")
  .attr("id", d=>"arr-"+d)
  .attr("viewBox","0 -5 10 10").attr("refX",22).attr("refY",0)
  .attr("markerWidth",6).attr("markerHeight",6).attr("orient","auto")
  .append("path").attr("d","M0,-5L10,0L0,5")
  .attr("fill", d => d==="gap" ? "#f85149" : d==="concept" ? "#e3b341" : "#555");

const sim = d3.forceSimulation(NODES)
  .force("link", d3.forceLink(LINKS).id(d=>d.id)
    .distance(d => d.type==="strong"?110 : d.type==="weak"?220 : d.type==="gap"?140 : 155)
    .strength(d => d.type==="strong"?.6 : d.type==="concept"?.15 : .2))
  .force("charge", d3.forceManyBody().strength(d => d.type==="folder"?-650:-320))
  .force("center",  d3.forceCenter(W/2, H/2))
  .force("collide", d3.forceCollide().radius(d=>d.size*2+14))
  .force("x", d3.forceX(W/2).strength(.04))
  .force("y", d3.forceY(H/2).strength(.04));

const link = g.append("g").selectAll("line").data(LINKS).join("line")
  .attr("class", d=>"link "+d.type)
  .attr("stroke", d=>d.color)
  .attr("marker-end", d=>`url(#arr-${{d.type}})`);

const node = g.append("g").selectAll("g").data(NODES).join("g")
  .attr("class", d=>"node "+d.type)
  .call(d3.drag()
    .on("start",(e,d)=>{{ if(!e.active) sim.alphaTarget(.3).restart(); d.fx=d.x; d.fy=d.y; }})
    .on("drag", (e,d)=>{{ d.fx=e.x; d.fy=e.y; }})
    .on("end",  (e,d)=>{{ if(!e.active) sim.alphaTarget(0); d.fx=null; d.fy=null; }}))
  .on("mouseover", showTip).on("mousemove", moveTip)
  .on("mouseout",  ()=>document.getElementById("tooltip").style.display="none")
  .on("click", highlightNode);

node.append("circle")
  .attr("r", d=>d.size)
  .attr("fill", d => {{
    const c = CAT_COLOR[d.category]||"#555";
    return d.type==="gap-node" ? "transparent" : c+"22";
  }})
  .attr("stroke", d=>CAT_COLOR[d.category]||"#555")
  .attr("stroke-width", d=>d.type==="folder"?3:2)
  .attr("stroke-dasharray", d=>d.type==="gap-node"?"5,3":"none");

node.filter(d=>d.type==="folder"||d.type==="concept")
  .append("circle").attr("r",d=>d.size*.35)
  .attr("fill",d=>CAT_COLOR[d.category]||"#555").attr("opacity",.8);

const label1 = d => d.label.includes("\\n") ? d.label.split("\\n")[0] : d.label;
const label2 = d => d.label.includes("\\n") ? d.label.split("\\n")[1] : null;

node.append("text").text(label1)
  .attr("y",d=>d.size+14)
  .attr("font-size",d=>d.type==="folder"?"11px":"10px")
  .attr("fill",d=>d.type==="gap-node"?"#f85149":"#c9d1d9");

node.filter(d=>d.label.includes("\\n"))
  .append("text").text(label2)
  .attr("y",d=>d.size+25)
  .attr("font-size","10px")
  .attr("fill",d=>d.type==="gap-node"?"#f85149":"#8b949e");

node.filter(d=>d.files>0)
  .append("text").text(d=>d.files+"f")
  .attr("y",d=>d.size+36).attr("font-size","8px")
  .attr("fill","#8b949e").attr("opacity",.6);

sim.on("tick",()=>{{
  link.attr("x1",d=>d.source.x).attr("y1",d=>d.source.y)
      .attr("x2",d=>d.target.x).attr("y2",d=>d.target.y);
  node.attr("transform",d=>`translate(${{d.x}},${{d.y}})`);
}});

// Tooltip
const tip = document.getElementById("tooltip");
function showTip(e,d){{
  const c = CAT_COLOR[d.category]||"#555";
  const tags = (d.tags||[]).map(t=>`<span class="tag" style="background:${{c}}22;color:${{c}}">${{t}}</span>`).join("");
  const conns = LINKS.filter(l=>{{
    const s=typeof l.source==="object"?l.source.id:l.source;
    const t=typeof l.target==="object"?l.target.id:l.target;
    return s===d.id||t===d.id;
  }});
  const connHtml = conns.length ? `<div class="conn-list"><strong style="color:#e6edf3;font-size:11px">Connections (${{conns.length}}):</strong>`+
    conns.slice(0,6).map(l=>{{
      const s=typeof l.source==="object"?l.source.id:l.source;
      const t=typeof l.target==="object"?l.target.id:l.target;
      const other=s===d.id?t:s;
      return `<span>↔ ${{other}}${{l.label?` <em style="color:#555">(${{l.label}})</em>`:""}}</span>`;
    }}).join("") + (conns.length>6?`<span style="color:#555">+${{conns.length-6}} more…</span>`:"") + "</div>" : "";
  const gapHtml = d.type==="gap-node"?`<div class="gap-note">⚠️ This is a knowledge gap — an area to develop.</div>`:"";
  tip.innerHTML=`<h3 style="color:${{c}}">${{d.label.replace("\\n"," ")}}</h3><div>${{tags}}</div><p>${{d.desc}}</p>${{connHtml}}${{gapHtml}}`;
  tip.style.display="block"; moveTip(e);
}}
function moveTip(e){{
  tip.style.left=Math.min(e.clientX+16,window.innerWidth-340)+"px";
  tip.style.top =Math.min(e.clientY-10,window.innerHeight-320)+"px";
}}

// Highlight on click
let highlighted=null;
function highlightNode(e,d){{
  if(highlighted===d.id){{ highlighted=null; link.attr("opacity",1); node.attr("opacity",1); return; }}
  highlighted=d.id;
  const conn=new Set([d.id]);
  LINKS.forEach(l=>{{
    const s=typeof l.source==="object"?l.source.id:l.source;
    const t=typeof l.target==="object"?l.target.id:l.target;
    if(s===d.id||t===d.id){{ conn.add(s); conn.add(t); }}
  }});
  link.attr("opacity",l=>{{
    const s=typeof l.source==="object"?l.source.id:l.source;
    const t=typeof l.target==="object"?l.target.id:l.target;
    return(conn.has(s)&&conn.has(t))?1:.05;
  }});
  node.attr("opacity",n=>conn.has(n.id)?1:.12);
}}

// Filters
document.querySelectorAll(".fbtn").forEach(b=>b.addEventListener("click",()=>{{
  document.querySelectorAll(".fbtn").forEach(x=>x.classList.remove("active"));
  b.classList.add("active");
  highlighted=null;
  const f=b.dataset.f;
  if(f==="all"){{ node.attr("opacity",1); link.attr("opacity",1); return; }}
  if(f==="gaps"){{
    node.attr("opacity",n=>n.type==="gap-node"?1:.12);
    link.attr("opacity",l=>l.type==="gap"?1:.04); return;
  }}
  const catMap={{ai:["ai"],investing:["investing"],personal:["personal","reference"]}};
  const cats=catMap[f]||[];
  node.attr("opacity",n=>cats.includes(n.category)||n.category==="concept"?1:.12);
  link.attr("opacity",l=>{{
    const s=typeof l.source==="object"?l.source:NODES.find(n=>n.id===l.source);
    const t=typeof l.target==="object"?l.target:NODES.find(n=>n.id===l.target);
    return(s&&t&&(cats.includes(s.category)||cats.includes(t.category)))?1:.04;
  }});
}}));

document.getElementById("reset-btn").addEventListener("click",()=>{{
  highlighted=null; node.attr("opacity",1); link.attr("opacity",1);
  document.querySelectorAll(".fbtn").forEach(b=>b.classList.remove("active"));
  document.querySelector("[data-f='all']").classList.add("active");
  svg.transition().duration(500).call(zoom.transform,d3.zoomIdentity);
}});

window.addEventListener("resize",()=>{{
  const w=window.innerWidth,h=window.innerHeight;
  svg.attr("width",w).attr("height",h);
  sim.force("center",d3.forceCenter(w/2,h/2)).alpha(.1).restart();
}});
</script>
</body>
</html>"""


# ── SERVER ────────────────────────────────────────────────────────────────────

def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def _open_browser(url: str):
    """Open URL in Windows default browser from WSL2."""
    os.system(f'explorer.exe "{url}" 2>/dev/null || wslview "{url}" 2>/dev/null || true')


def serve(html_file: Path):
    port = _free_port()
    url  = f"http://localhost:{port}/{html_file.name}"

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(html_file.parent), **kwargs)
        def log_message(self, *args):
            pass  # suppress request logs

    server = http.server.HTTPServer(("localhost", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    print(f"\n🌐  Serving at {url}")
    print("    Press Ctrl+C to stop.\n")
    _open_browser(url)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n⛔  Server stopped.")
        server.shutdown()


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    print(f"🔍  Scanning vault: {VAULT_PATH}")
    scan = scan_vault(VAULT_PATH)
    print(f"✅  Found {scan['total_files']} notes across {len(scan['folders'])} folders")
    print(f"    Wikilink edges: {len(scan['wikilink_edges'])}")
    print(f"    Keyword-overlap edges: {len(scan['keyword_edges'])}")

    print("🔗  Building graph data…")
    nodes, links = build_graph_data(scan)
    print(f"    Nodes: {len(nodes)}  |  Links: {len(links)}")

    print(f"🖊️   Writing → {OUTPUT_FILE}")
    html = generate_html(nodes, links, scan)
    OUTPUT_FILE.write_text(html, encoding="utf-8")

    serve(OUTPUT_FILE)


if __name__ == "__main__":
    main()

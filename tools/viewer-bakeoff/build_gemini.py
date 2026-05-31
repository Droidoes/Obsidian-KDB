#!/usr/bin/env python3
"""Build the Gemini submission for the GraphDB viewer bake-off (#97).

Reads graph-export-run3.json, injects it into the HTML template,
and writes the self-contained kdb-graph-viewer-gemini.html.
"""
import json
import sys
from pathlib import Path


def main():
    bakeoff_dir = Path(__file__).resolve().parent

    data_path = bakeoff_dir / "graph-export-run3.json"
    template_path = bakeoff_dir / "gemini_template.html"
    out_path = bakeoff_dir / "kdb-graph-viewer-gemini.html"

    if not data_path.is_file():
        print(f"Error: export data not found at {data_path}", file=sys.stderr)
        sys.exit(1)

    if not template_path.is_file():
        print(f"Error: HTML template not found at {template_path}", file=sys.stderr)
        sys.exit(1)

    try:
        graph_data = json.loads(data_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"Error loading JSON data: {exc}", file=sys.stderr)
        sys.exit(1)

    graph_json = json.dumps(graph_data, separators=(",", ":"))

    template = template_path.read_text(encoding="utf-8")
    html = template.replace("/*__GRAPH_DATA__*/", graph_json, 1)

    try:
        out_path.write_text(html, encoding="utf-8")
    except Exception as exc:
        print(f"Error writing compiled HTML: {exc}", file=sys.stderr)
        sys.exit(1)

    n = len(graph_data.get("nodes", []))
    e = len(graph_data.get("edges", []))
    print(f"✓ Wrote {out_path}")
    print(f"  {n} nodes, {e} edges")
    print(f"  File size: {out_path.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()

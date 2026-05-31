#!/usr/bin/env python3
"""Build the Qwen submission for the GraphDB viewer bake-off (#97).

Reads graph-export-run3.json, injects it into the HTML template,
and writes the self-contained kdb-graph-viewer-qwen.html.
"""
import json
from pathlib import Path


def main():
    bakeoff_dir = Path(__file__).resolve().parent

    data_path = bakeoff_dir / "graph-export-run3.json"
    template_path = bakeoff_dir / "qwen_template.html"
    out_path = bakeoff_dir / "kdb-graph-viewer-qwen.html"

    graph_data = json.loads(data_path.read_text(encoding="utf-8"))
    graph_json = json.dumps(graph_data, separators=(",", ":"))

    template = template_path.read_text(encoding="utf-8")
    html = template.replace(
        "/*__GRAPH_DATA__*/null/*__END__*/", graph_json, 1
    )

    out_path.write_text(html, encoding="utf-8")

    n = len(graph_data["nodes"])
    e = len(graph_data["edges"])
    print(f"✓ Wrote {out_path}")
    print(f"  {n} nodes, {e} edges")
    print(f"  File size: {out_path.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()

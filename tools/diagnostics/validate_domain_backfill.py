#!/usr/bin/env python3
"""Validate D1-A: derive domains from run-3 compile_result, no LLM cost.

Usage:
  python3 tools/diagnostics/validate_domain_backfill.py \
      --vault ~/Obsidian/Vault-in-place-test-run
"""
import argparse, json, tempfile
from pathlib import Path
from kdb_graph.graphdb import GraphDB

ap = argparse.ArgumentParser()
ap.add_argument("--vault", required=True)
args = ap.parse_args()
vault = Path(args.vault).expanduser()
cr = json.loads((vault / "KDB/state/compile_result.json").read_text())

# Minimal scan from compiled_sources (CHANGED action for each).
files = [{"path": cs["source_id"], "action": "CHANGED",
          "current_hash": "sha256:x", "size_bytes": 1, "file_type": "markdown",
          "is_binary": False} for cs in cr["compiled_sources"]]
scan = {"files": files, "to_reconcile": []}

with tempfile.TemporaryDirectory() as d:
    with GraphDB(Path(d) / "g") as gdb:
        gdb.apply_compile_result(cr, scan, cr["run_id"])
        r = gdb.conn.execute(
            "MATCH (e:Entity)-[b:BELONGS_TO]->(d:Domain) "
            "RETURN d.name, count(DISTINCT e), max(b.support_count) "
            "ORDER BY count(DISTINCT e) DESC")
        print(f"{'domain':<28} entities  max_support")
        domains = []
        while r.has_next():
            name, ents, maxsup = r.get_next()
            domains.append(name)
            print(f"{name:<28} {ents:>5}     {maxsup}")
        tot = gdb.conn.execute("MATCH (e:Entity) WHERE e.canonical_id IS NULL RETURN count(*)").get_next()[0]
        cov = gdb.conn.execute("MATCH (e:Entity)-[:BELONGS_TO]->() RETURN count(DISTINCT e)").get_next()[0]
        print(f"\ndistinct domains: {len(domains)}")
        print(f"canonical entities with a domain: {cov}/{tot}")
        assert "value-investing" in domains, "value-investing missing — D1-A failed"
        print("\nOK: value-investing present; derived projection healthy.")

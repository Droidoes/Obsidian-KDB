"""Allow `python -m kdb_graph` to dispatch to cli.main."""
from kdb_graph.cli import main

if __name__ == "__main__":
    raise SystemExit(main())

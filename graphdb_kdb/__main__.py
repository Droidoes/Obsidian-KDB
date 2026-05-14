"""Allow `python -m graphdb_kdb` to dispatch to cli.main."""
from graphdb_kdb.cli import main

if __name__ == "__main__":
    raise SystemExit(main())

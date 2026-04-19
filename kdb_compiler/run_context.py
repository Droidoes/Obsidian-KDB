"""run_context — per-run metadata: run_id, timestamps, versions, dry_run flag.

One RunContext is created at the start of each compile run and threaded
through every stage. This is the ONLY place in the pipeline where "now"
is read, run_id is generated, and compiler_version is stamped.

Enforces D8: the LLM never sees timestamps, versions, or run IDs. Python
owns all of them; CLAUDE.md forbids the LLM from emitting these fields.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from . import paths

SCHEMA_VERSION = "1.0"


def utc_now_iso() -> str:
    """ISO-8601 UTC timestamp with 'Z' suffix, second precision."""
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def run_id_from_timestamp(iso_ts: str) -> str:
    """Filename-safe run_id derived from an ISO timestamp."""
    return iso_ts.replace(":", "-").replace(".", "-")


@dataclass
class RunContext:
    run_id: str
    started_at: str
    compiler_version: str
    schema_version: str
    dry_run: bool
    vault_root: Path
    kdb_root: Path
    log_entries: list[dict] = field(default_factory=list)

    @classmethod
    def new(cls, *, dry_run: bool = False, vault_root: Path | None = None) -> "RunContext":
        root = vault_root if vault_root is not None else paths.vault_root()
        now = utc_now_iso()
        return cls(
            run_id=run_id_from_timestamp(now),
            started_at=now,
            compiler_version=__version__,
            schema_version=SCHEMA_VERSION,
            dry_run=dry_run,
            vault_root=root,
            kdb_root=paths.kdb_root(root),
        )

    def frontmatter_for(self, *, raw_path: str, raw_hash: str, raw_mtime: float) -> dict:
        """Build the frontmatter Python prepends to every LLM-authored page."""
        return {
            "raw_path": raw_path,
            "raw_hash": raw_hash,
            "raw_mtime": raw_mtime,
            "compiled_at": self.started_at,
            "compiler_version": self.compiler_version,
            "schema_version_used": self.schema_version,
        }

    def append_log(self, level: str, message: str, **extras) -> None:
        """Accumulate a log entry; patch_applier flushes these to wiki/log.md."""
        entry = {"level": level, "message": message, "run_id": self.run_id}
        entry.update(extras)
        self.log_entries.append(entry)

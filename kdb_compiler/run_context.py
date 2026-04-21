"""run_context — per-run metadata: run_id, timestamps, versions, dry_run flag.

One RunContext is created at the start of each compile run and threaded
through every stage. This is the ONLY place in the pipeline where "now"
is read, run_id is generated, and compiler_version is stamped.

Enforces D8: the LLM never sees timestamps, versions, or run IDs. Python
owns all of them; the KDB compiler system prompt forbids the LLM from
emitting these fields.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from . import __version__
from . import paths

# The schema version stamped into manifest.json (ensure_manifest_shape)
# and into per-page frontmatter (`schema_version_used`). Journal files
# now declare their own JOURNAL_SCHEMA_VERSION in run_journal.py; keep
# the names separate so manifest changes don't accidentally force a
# journal migration (or vice versa).
MANIFEST_SCHEMA_VERSION = "1.0"
SCHEMA_VERSION = MANIFEST_SCHEMA_VERSION  # legacy alias — prefer MANIFEST_SCHEMA_VERSION


def now_iso() -> str:
    """ISO-8601 local timestamp with offset, second precision.

    Example: '2026-04-19T22:34:09-04:00'. Local time is used everywhere
    in the project for human readability — this is a single-user,
    single-machine system where DST sortability across timezones is a
    theoretical concern, not a real one.
    """
    return (
        datetime.now().astimezone()
        .replace(microsecond=0)
        .isoformat()
    )


def run_id_from_timestamp(iso_ts: str) -> str:
    """Filename-safe run_id: 'YYYY-MM-DDTHH-MM-SS_<TZ>'.

    Example: '2026-04-19T22:34:09-04:00' -> '2026-04-19T22-34-09_EDT'.

    The TZ abbreviation comes from the system's current zone, not from
    the parsed timestamp's tzinfo — fixed-offset tzinfos (what
    ``datetime.fromisoformat`` produces) report ``tzname()`` as
    ``'UTC-04:00'``, which isn't what we want. In practice callers
    always feed a just-produced ``now_iso()`` so the two agree on DST.
    """
    dt = datetime.fromisoformat(iso_ts)
    tz = datetime.now().astimezone().tzname() or "LOCAL"
    return dt.strftime("%Y-%m-%dT%H-%M-%S") + f"_{tz}"


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
        now = now_iso()
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
        """Accumulate a log entry; persisted to state/runs/<run_id>.json journal."""
        entry = {"level": level, "message": message, "run_id": self.run_id}
        entry.update(extras)
        self.log_entries.append(entry)

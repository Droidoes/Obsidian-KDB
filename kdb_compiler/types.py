"""types — typed dataclasses for pipeline payloads.

Single source of truth for cross-module shapes. Mirrors the JSON schemas
in kdb_compiler/schemas/ and docs/manifest.schema.md.

M1a: minimal set needed by scanner + validator + manifest updater.
     (More shapes land with later M1 modules as needed.)

Serialization convention: every dataclass with a to_dict() produces a dict
shaped for direct JSON serialization. from_dict() does the inverse.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Literal, Optional

FileType = Literal["markdown", "binary", "unknown"]
ScanAction = Literal["NEW", "RECOMPILE", "UNCHANGED", "MOVED", "DELETED"]
ReconcileType = Literal["MOVED", "DELETED"]
PageType = Literal["summary", "concept", "article"]
PageStatus = Literal["active", "stale", "orphan_candidate", "archived"]
Confidence = Literal["low", "medium", "high"]
SourceRefRole = Literal["primary", "supporting", "historical"]


@dataclass
class ScanEntry:
    """One file observed by kdb_scan in KDB/raw/."""
    path: str                # POSIX relative to vault: "KDB/raw/foo.md"
    current_hash: str        # "sha256:<64-hex>"
    current_mtime: float     # unix seconds; advisory
    size_bytes: int
    file_type: FileType
    is_binary: bool
    action: ScanAction       # classification vs prior manifest state

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ReconcileOp:
    """MOVED or DELETED row in last_scan.to_reconcile[]."""
    type: ReconcileType
    path: Optional[str] = None        # DELETED: old path. MOVED: unused.
    from_path: Optional[str] = None   # MOVED: old path
    to_path: Optional[str] = None     # MOVED: new path
    hash: Optional[str] = None        # content hash at time of reconciliation

    def to_dict(self) -> dict:
        d: dict[str, Any] = {"type": self.type}
        if self.type == "DELETED":
            d["path"] = self.path
            if self.hash:
                d["hash"] = self.hash
        else:  # MOVED
            d["from"] = self.from_path
            d["to"] = self.to_path
            if self.hash:
                d["hash"] = self.hash
        return d


@dataclass
class SkippedEntry:
    """Something kdb_scan found but did not scan (symlink, permission error, etc.)."""
    path: str
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ScanResult:
    """Full last_scan.json payload."""
    schema_version: str
    run_id: str
    scanned_at: str
    vault_root: str
    files: list[ScanEntry] = field(default_factory=list)
    to_compile: list[str] = field(default_factory=list)         # source_ids NEW or RECOMPILE
    to_reconcile: list[ReconcileOp] = field(default_factory=list)
    skipped: list[SkippedEntry] = field(default_factory=list)
    stats: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "scanned_at": self.scanned_at,
            "vault_root": self.vault_root,
            "files": [e.to_dict() for e in self.files],
            "to_compile": list(self.to_compile),
            "to_reconcile": [op.to_dict() for op in self.to_reconcile],
            "skipped": [s.to_dict() for s in self.skipped],
            "stats": dict(self.stats),
        }


@dataclass
class PageIntent:
    """One page the LLM wants to create or replace. Full-body model (D18)."""
    slug: str
    page_type: PageType
    title: str
    body: str
    status: PageStatus = "active"
    supports_page_existence: list[str] = field(default_factory=list)
    outgoing_links: list[str] = field(default_factory=list)
    confidence: Confidence = "medium"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CompiledSource:
    """LLM output for one source."""
    source_id: str
    summary_slug: str
    pages: list[PageIntent]
    concept_slugs: list[str] = field(default_factory=list)
    article_slugs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "source_id": self.source_id,
            "summary_slug": self.summary_slug,
            "concept_slugs": list(self.concept_slugs),
            "article_slugs": list(self.article_slugs),
            "pages": [p.to_dict() for p in self.pages],
        }


@dataclass
class LogEntry:
    level: Literal["info", "notice", "contradiction", "warning"]
    message: str
    related_slugs: list[str] = field(default_factory=list)
    related_source_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CompileResult:
    run_id: str
    success: bool
    compiled_sources: list[CompiledSource] = field(default_factory=list)
    log_entries: list[LogEntry] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "success": self.success,
            "compiled_sources": [cs.to_dict() for cs in self.compiled_sources],
            "log_entries": [le.to_dict() for le in self.log_entries],
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }

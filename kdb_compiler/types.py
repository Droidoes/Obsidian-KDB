"""types — typed dataclasses for pipeline payloads.

Single source of truth for cross-module shapes. Mirrors the JSON schemas
in kdb_compiler/schemas/ and docs/manifest.schema.md.

Serialization convention: every dataclass with a to_dict() produces a dict
shaped for direct JSON serialization. Plain asdict() is used where the
dataclass field names already match the JSON shape.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal, Optional

FileType = Literal["markdown", "binary", "unknown"]
ScanAction = Literal["NEW", "CHANGED", "UNCHANGED", "MOVED"]  # DELETED lives in ReconcileOp only
ReconcileType = Literal["MOVED", "DELETED"]
SymlinkPolicy = Literal["skip", "follow"]
PageType = Literal["summary", "concept", "article"]
PageStatus = Literal["active", "stale", "orphan_candidate", "archived"]
Confidence = Literal["low", "medium", "high"]
SourceRefRole = Literal["primary", "supporting", "historical"]


# ---------- scan artifact shapes ----------

@dataclass
class ScanEntry:
    """One file currently present in KDB/raw/.

    DELETED files are NOT represented here — they live only in ReconcileOp.
    """
    path: str                              # POSIX relative to vault: "KDB/raw/foo.md"
    action: ScanAction
    current_hash: str                      # "sha256:<64-hex>"
    current_mtime: float                   # unix seconds; advisory
    size_bytes: int
    file_type: FileType
    is_binary: bool
    previous_hash: Optional[str] = None    # CHANGED/UNCHANGED/MOVED
    previous_mtime: Optional[float] = None # CHANGED/UNCHANGED/MOVED
    previous_path: Optional[str] = None    # MOVED only

    def to_dict(self) -> dict:
        d: dict[str, Any] = {
            "path": self.path,
            "action": self.action,
            "current_hash": self.current_hash,
            "current_mtime": self.current_mtime,
            "size_bytes": self.size_bytes,
            "file_type": self.file_type,
            "is_binary": self.is_binary,
        }
        if self.previous_hash is not None:
            d["previous_hash"] = self.previous_hash
        if self.previous_mtime is not None:
            d["previous_mtime"] = self.previous_mtime
        if self.previous_path is not None:
            d["previous_path"] = self.previous_path
        return d


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
class ErrorEntry:
    """Read/stat failure observed during scan."""
    path: str
    error: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SkippedSymlinkEntry:
    """Symlink encountered in raw/, skipped by policy."""
    path: str
    link_target: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ScanSummary:
    new: int = 0
    changed: int = 0
    unchanged: int = 0
    moved: int = 0
    deleted: int = 0            # reconcile-only count
    error: int = 0
    skipped_symlink: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SettingsSnapshot:
    """Scanner config captured into the output for reproducibility."""
    rename_detection: bool
    symlink_policy: SymlinkPolicy
    scan_binary_files: bool
    binary_compile_mode: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ScanResult:
    """Full last_scan.json payload."""
    schema_version: str
    run_id: str
    scanned_at: str                       # ISO UTC
    vault_root: str                       # absolute path (debugging)
    raw_root: str                         # POSIX relative: "KDB/raw"
    settings_snapshot: SettingsSnapshot
    summary: ScanSummary
    files: list[ScanEntry] = field(default_factory=list)
    to_compile: list[str] = field(default_factory=list)
    to_reconcile: list[ReconcileOp] = field(default_factory=list)
    to_skip: list[str] = field(default_factory=list)
    errors: list[ErrorEntry] = field(default_factory=list)
    skipped_symlinks: list[SkippedSymlinkEntry] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "scanned_at": self.scanned_at,
            "vault_root": self.vault_root,
            "raw_root": self.raw_root,
            "settings_snapshot": self.settings_snapshot.to_dict(),
            "summary": self.summary.to_dict(),
            "files": [e.to_dict() for e in self.files],
            "to_compile": list(self.to_compile),
            "to_reconcile": [op.to_dict() for op in self.to_reconcile],
            "to_skip": list(self.to_skip),
            "errors": [e.to_dict() for e in self.errors],
            "skipped_symlinks": [s.to_dict() for s in self.skipped_symlinks],
        }


# ---------- compile artifact shapes (unchanged) ----------

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
class CompileMeta:
    """Per-source model-call metadata. Stamped by Python after a live compile;
    absent on fixture-backed compiled sources."""
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    attempts: int
    ok: bool
    error: Optional[str] = None

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
    compile_meta: Optional[CompileMeta] = None

    def to_dict(self) -> dict:
        d: dict[str, Any] = {
            "source_id": self.source_id,
            "summary_slug": self.summary_slug,
            "concept_slugs": list(self.concept_slugs),
            "article_slugs": list(self.article_slugs),
            "pages": [p.to_dict() for p in self.pages],
        }
        if self.compile_meta is not None:
            d["compile_meta"] = self.compile_meta.to_dict()
        return d


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


# ---------- M2 planner / context / resp-stats shapes ----------

@dataclass
class ContextPage:
    """Compact view of one existing page, shown to the LLM in the context
    snapshot. Intentionally drops body, paths, timestamps (D8)."""
    slug: str
    title: str
    page_type: PageType
    outgoing_links: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ContextSnapshot:
    """Per-source manifest snapshot passed into the prompt."""
    source_id: str
    pages: list[ContextPage] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "source_id": self.source_id,
            "pages": [p.to_dict() for p in self.pages],
        }


@dataclass
class CompileJob:
    """One unit of compile work: a source_id + resolved path + its
    pre-built context snapshot."""
    source_id: str                 # "KDB/raw/..."
    abs_path: str                  # absolute filesystem path
    context_snapshot: ContextSnapshot


@dataclass
class ParsedSummary:
    """Lossy reduction of a parsed per-source response. Stored in every
    resp-stats record (when parse succeeded) as a body-free shape digest."""
    summary_slug: Optional[str]
    page_count: int
    page_types: dict[str, int]
    slugs: list[str]
    outgoing_link_count: int
    log_entry_count: int
    warning_count: int
    source_id_echoed: Optional[str]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RespStatsRecord:
    """One response-stats record written per compile_one call. Metadata +
    hashes + four well-formedness flags + parsed_summary are always on.
    parsed_json and full prompt/response bodies are gated by
    KDB_RESP_STATS_CAPTURE_FULL=1.

    These are CALL-TELEMETRY fields (did the call run; is the response
    well-formed), NOT response-quality scores. A response can pass all
    four flags and still be a poor answer — quality scoring is a
    separate feature (see M2 E3 deferred).

    response_hash == 'sha256:none' indicates no response was captured
    (pre-response failure). prompt_hash == 'sha256:none' indicates the
    prompt itself could not be built. These sentinels distinguish missing
    data from empty-string data.
    """
    run_id: str
    source_id: str
    provider: str
    model: str
    attempts: int
    latency_ms: int
    input_tokens: int
    output_tokens: int
    prompt_hash: str
    response_hash: str
    extract_ok: bool
    parse_ok: bool
    schema_ok: bool
    semantic_ok: bool
    schema_errors: list[str] = field(default_factory=list)
    semantic_errors: list[str] = field(default_factory=list)
    parsed_summary: Optional[ParsedSummary] = None
    parsed_json: Optional[dict] = None
    system_prompt: Optional[str] = None
    user_prompt: Optional[str] = None
    raw_response_text: Optional[str] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        if self.parsed_summary is not None:
            d["parsed_summary"] = self.parsed_summary.to_dict()
        return d

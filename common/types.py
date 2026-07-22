"""types — typed dataclasses for pipeline payloads.

Single source of truth for cross-module shapes. Mirrors the JSON schemas
in compiler/schemas/ and docs/manifest.schema.md.

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
SourceRefRole = Literal["primary", "supporting", "historical"]
# #115: PageStatus / Confidence aliases deleted — orphaned with the fields
# (status is prose-stamped, confidence logically deprecated).


# ---------- source-file frontmatter ----------

@dataclass
class SourceFrontmatter:
    """Parsed GraphDB-input section of Pass-1 frontmatter. Audit section +
    user-added keys are ignored by compile per D-89-16."""
    kdb_signal: str
    domain: str
    source_type: str
    author: str | None
    summary: str
    key_themes: list[str]
    entity_search_keys: list[str]  # ≤10 slugs; T2-rewrite input (D-89-20); not seen by Pass-2

    @classmethod
    def from_dict(cls, fm: dict) -> "SourceFrontmatter | None":
        """Return None if frontmatter does not contain Pass-1 GraphDB-input keys.

        v0.2.2 (D-89-20): key_entities dropped; entity_search_keys added (the
        sole consumer is Task #90 context-loader T2-rewrite). Pre-v0.2.2
        frontmatter without `entity_search_keys` still parses (defaults to []).
        """
        required = {"kdb_signal", "domain", "source_type", "summary"}
        if not required.issubset(fm.keys()):
            return None
        return cls(
            kdb_signal=fm["kdb_signal"],
            domain=fm["domain"],
            source_type=fm["source_type"],
            author=fm.get("author"),
            summary=fm["summary"],
            key_themes=fm.get("key_themes", []) or [],
            entity_search_keys=fm.get("entity_search_keys", []) or [],
        )


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
    compiled_hash: Optional[str]           # prior last_compiled_hash, or None — required-but-nullable (Q3)
    previous_hash: Optional[str] = None    # CHANGED/UNCHANGED/MOVED
    previous_mtime: Optional[float] = None # CHANGED/UNCHANGED/MOVED
    previous_path: Optional[str] = None    # MOVED only
    pipeline_id: Optional[str] = None      # Task #91: owning ingestion pipeline

    def to_dict(self) -> dict:
        d: dict[str, Any] = {
            "path": self.path,
            "action": self.action,
            "current_hash": self.current_hash,
            "current_mtime": self.current_mtime,
            "size_bytes": self.size_bytes,
            "file_type": self.file_type,
            "is_binary": self.is_binary,
            "compiled_hash": self.compiled_hash,
        }
        if self.previous_hash is not None:
            d["previous_hash"] = self.previous_hash
        if self.previous_mtime is not None:
            d["previous_mtime"] = self.previous_mtime
        if self.previous_path is not None:
            d["previous_path"] = self.previous_path
        if self.pipeline_id is not None:
            d["pipeline_id"] = self.pipeline_id
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


# ---------- compile artifact shapes ----------

@dataclass
class PageIntent:
    """One page the LLM wants to create or replace. Full-body model (D18).

    #115 wiki-native contract: the LLM authors slug/page_type/title/body only.
    `status` is Python-owned (page_writer stamps 'active' when absent); graph
    edges derive from body wikilinks (no outgoing_links field); `confidence`
    is logically deprecated (D-115-12, Entity scope).
    """
    slug: str
    page_type: PageType
    title: str
    body: str
    supports_page_existence: list[str] = field(default_factory=list)

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
    """LLM output for one source (#115: no summary_slug / slug lists —
    Python derives the summary identity via compiler.summary_slug)."""
    source_id: str
    pages: list[PageIntent]
    compile_meta: Optional[CompileMeta] = None
    source_meta: Optional[dict] = None  # D-89-17: Pass-1 frontmatter projection

    def to_dict(self) -> dict:
        d: dict[str, Any] = {
            "source_id": self.source_id,
            "pages": [p.to_dict() for p in self.pages],
        }
        if self.compile_meta is not None:
            d["compile_meta"] = self.compile_meta.to_dict()
        if self.source_meta is not None:
            d["source_meta"] = self.source_meta
        return d


@dataclass
class CompileSourceResult:
    """Per-source Pass-2 PRODUCE result from compiler.compile_source().
    Produce-don't-write: holds the compiled `cr` only — the orchestrator
    owns stage-8 apply-pages, provenance, manifest commit, and graph-sync.
    error non-None ==> pre-commit failure (D-91-13 case a); cr is None and
    `failure_stage` in {context, compile, validate, canonicalize} routes the
    orchestrator's case-aware summary without string-parsing."""
    cr: Optional[dict]
    failure_stage: Optional[str] = None
    exception_type: Optional[str] = None
    error: Optional[str] = None
    artifacts: dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.error is None


@dataclass
class CompileResult:
    """#115: `warnings` renamed to `compilation_notes`; `log_entries` and
    `LogEntry` deleted (the LLM contract no longer carries them)."""
    run_id: str
    success: bool
    compiled_sources: list[CompiledSource] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    compilation_notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "success": self.success,
            "compiled_sources": [cs.to_dict() for cs in self.compiled_sources],
            "errors": list(self.errors),
            "compilation_notes": list(self.compilation_notes),
        }


# ---------- M2 context / resp-stats shapes ----------

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
    pre-built context snapshot. The orchestrator (in-memory path) also
    supplies source_text + frontmatter so compile reads nothing from disk."""
    source_id: str                 # "KDB/raw/..."
    abs_path: str                  # absolute filesystem path (legacy path only)
    context_snapshot: ContextSnapshot
    source_text: str | None = None              # in-memory body (orchestrator path)
    frontmatter: "SourceFrontmatter | None" = None


@dataclass
class ParsedSummary:
    """Lossy reduction of a parsed per-source response. Stored in every
    resp-stats record (when parse succeeded) as a body-free shape digest.

    #115 (D-115-15): `summary_slug` is emitted ONLY when exactly one
    well-formed summary page is observable (else None);
    `outgoing_link_count` derives from body wikilinks (pure extraction);
    `compilation_note_count` renamed from warning_count; log_entry_count
    and source_id_echoed dropped."""
    summary_slug: Optional[str]
    page_count: int
    page_types: dict[str, int]
    slugs: list[str]
    outgoing_link_count: int
    compilation_note_count: int

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

    Task #25 failure_* triplet: when the compile halts at a non-validation
    stage (source_read | prompt_build | model_call | truncation | extract
    | parse), all three fields are populated together; otherwise all three
    are None. Schema failures keep using schema_errors — a structured list
    surface, out of the failure_* triplet's scope. #115: VALIDATION-stage
    rejections also populate the triplet with stage "validate" — the
    pre-call underivable-stem route (PathError) and the terminal post-call
    semantic rejection (synthetic "SemanticCheckError"); semantic_errors
    remains the structured detail surface. exception_type is the Python
    class name (or the synthetic "TokenOverrun" for truncation /
    "SemanticCheckError" for terminal semantic rejection); message is the
    exception's str(e) or the first gate error, truncated to 2000 chars +
    '...[truncated]'.
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
    parsed_json: object | None = None
    system_prompt: Optional[str] = None
    user_prompt: Optional[str] = None
    raw_response_text: Optional[str] = None
    stop_reason: Optional[str] = None
    token_overrun: bool = False
    # #110 Task 2.1: per-call cost diagnostic, USD. Derived from pool pricing
    # (price_in/price_out per 1M tokens) × AGGREGATED tokens (every retry
    # attempt is billed). 0.0 on unpriced runs (no pool pricing threaded).
    cost_usd: float = 0.0
    source_words: int = 0
    failure_stage: Optional[str] = None
    failure_exception_type: Optional[str] = None
    failure_exception_message: Optional[str] = None
    # #106 repair-ladder telemetry (compositional — NOT mutually exclusive).
    # `attempts` above is SDK-level retry count; these describe the Pass-2 ladder.
    compile_attempts: Optional[int] = None      # loop attempt (1 or 2) that produced final parsed_json
    syntax_repaired: bool = False               # rung-1 escaping rescued a parse
    slug_coerced: bool = False                  # rung-2 coercion rescued schema/semantic
    # #114 recovery telemetry (Pass-2 only; always serialized, False/0 default).
    boundary_recovered: bool = False            # selection recovered a document amid carrier noise
    prefix_discarded_chars: int = 0             # carrier noise before the selected root boundary
    tail_discarded_chars: int = 0               # carrier noise after the decoder boundary
    final_status: Optional[str] = None          # clean | repaired | retried-and-repaired | quarantined
    # #109 Task 2: discarded-attempt aggregation.
    # Aggregated across ALL Pass-2 loop attempts (including failed/discarded ones).
    # For a 1-attempt run: totals == per-attempt values, call_count=1, final_attempt_index=1.
    # Defaults to 0/1 so older persisted JSON without these fields still loads cleanly.
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_latency_ms: int = 0
    call_count: int = 1                         # number of model calls made in the Pass-2 loop
    final_attempt_index: int = 1                # loop attempt number that produced the winning record

    def to_dict(self) -> dict:
        d = asdict(self)
        if self.parsed_summary is not None:
            d["parsed_summary"] = self.parsed_summary.to_dict()
        return d


# ---------- serialized CompiledSource helpers (#115) ----------

class SummaryPageError(ValueError):
    """Raised by summary_page() when the page set has no unique summary."""


def summary_page(source: "Mapping[str, Any]") -> "Mapping[str, Any]":
    """Return the one page with page_type == 'summary' from a serialized
    CompiledSource-shaped mapping. FAIL CLOSED (#115): raises
    SummaryPageError on zero or multiple summary pages — the summary
    identity is never guessed."""
    from collections.abc import Mapping as _Mapping
    pages = source.get("pages") or []
    summaries = [
        p for p in pages
        if isinstance(p, _Mapping) and p.get("page_type") == "summary"
    ]
    if len(summaries) != 1:
        raise SummaryPageError(
            f"expected exactly one summary page, got {len(summaries)} "
            f"(source_id={source.get('source_id')!r})"
        )
    return summaries[0]

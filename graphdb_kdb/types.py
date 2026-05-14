"""Public dataclasses returned by GraphDB queries.

#63.1 shipped Page + Source. #63.2 adds SyncResult. VerifyResult / RebuildResult
arrive in their respective sub-tasks (#63.5 / #63.6).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SyncResult:
    """Per-run ingest summary returned by apply_compile_result."""
    run_id: str = ""
    pages_upserted: int = 0       # Page MERGE ops in Phase 3
    edges_upserted: int = 0       # LINKS_TO edges present after replacement (Phase 3)
    sources_upserted: int = 0     # Source MERGE ops in Phase 1 (scan refresh)
    supports_upserted: int = 0    # SUPPORTS edges present after replacement (Phase 3)
    orphans_detected: list[str] = field(default_factory=list)  # newly orphan_candidate slugs


@dataclass(frozen=True)
class Page:
    slug: str
    title: str
    page_type: str
    status: str
    confidence: str
    created_at: str
    updated_at: str
    first_run_id: str
    last_run_id: str


@dataclass(frozen=True)
class Source:
    source_id: str
    source_type: str
    canonical_path: str
    status: str
    file_type: str
    hash: str
    size_bytes: int
    first_seen_at: str
    last_seen_at: str
    last_compiled_at: str
    compile_state: str
    compile_count: int
    last_run_id: str
    moved_to: str

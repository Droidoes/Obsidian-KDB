"""Public dataclasses returned by GraphDB queries.

#63.1 shipped Entity + Source (renamed from Page per D-A1 2026-05-14).
#63.2 adds SyncResult. VerifyResult / RebuildResult arrive in their
respective sub-tasks (#63.5 / #63.6).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SyncResult:
    """Per-run ingest summary returned by apply_compile_result."""
    run_id: str = ""
    entities_upserted: int = 0    # Entity MERGE ops in Phase 3 (renamed from pages_upserted per D-A1)
    edges_upserted: int = 0       # LINKS_TO edges present after replacement (Phase 3)
    sources_upserted: int = 0     # Source MERGE ops in Phase 1 (scan refresh)
    supports_upserted: int = 0    # SUPPORTS edges present after replacement (Phase 3)
    orphans_detected: list[str] = field(default_factory=list)  # newly orphan_candidate slugs


@dataclass(frozen=True)
class Entity:
    slug: str
    title: str
    page_type: str       # values still Obsidian-flavored: 'summary'|'concept'|'article' (D-A2: rename of values deferred to producer #2)
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
    last_ingested_at: str    # renamed from last_compiled_at per D-A2 (graph-side ingestion concept, not producer's compile concept)
    ingest_state: str         # renamed from compile_state per D-A2
    ingest_count: int         # renamed from compile_count per D-A2
    last_run_id: str
    moved_to: str

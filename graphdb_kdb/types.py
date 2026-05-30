"""Public dataclasses returned by GraphDB queries.

#63.1 shipped Entity + Source (renamed from Page per D-A1 2026-05-14).
#63.2 adds SyncResult. VerifyResult / RebuildResult arrive in their
respective sub-tasks (#63.5 / #63.6).
#83/#84 schema v2.2 adds Claim (D-83/84-6 F1 family/version split;
STRING[] arrays for scope + object slugs).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SyncResult:
    """Per-run ingest summary returned by apply_compile_result."""
    run_id: str = ""
    entities_upserted: int = 0    # Entity MERGE ops in Phase 3 (renamed from pages_upserted per D-A1)
    edges_upserted: int = 0       # LINKS_TO edges present after replacement (Phase 3)
    sources_upserted: int = 0     # Source MERGE ops in Phase 1 (scan refresh)
    supports_upserted: int = 0    # SUPPORTS edges present after replacement (Phase 3)
    alias_of_upserted: int = 0    # ALIAS_OF edges created this run by Phase 3.5 (#74.5); accumulator across aliases_emitted entries, mirrors supports_upserted convention
    domains_upserted: int = 0     # Domain MERGE ops in Phase 3.6 (#76.3); counts upsert operations (not only new nodes)
    belongs_to_upserted: int = 0  # BELONGS_TO MERGE ops in Phase 3.6 (#76.3); mirrors supports_upserted convention
    entities_deleted: int = 0     # Entity DETACH DELETE ops in apply_cleanup (#68)
    orphans_detected: list[str] = field(default_factory=list)  # newly orphan_candidate slugs


@dataclass(frozen=True)
class Entity:
    slug: str
    title: str
    page_type: str       # values still Obsidian-flavored: 'summary'|'concept'|'article' (D-A2: rename of values deferred to producer #2); #74.5 adds 'alias' for graph-only alias rows
    status: str
    confidence: str
    created_at: str
    updated_at: str
    first_run_id: str
    last_run_id: str
    canonical_id: str | None = None  # #74.5 D-R5-5: NULL ⇒ self is canonical; otherwise points at the (chain-flattened, D-R5-13) root canonical slug


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
    ingest_state: str         # graph-side name for producer run_state
    ingest_count: int         # renamed from compile_count per D-A2
    last_run_id: str
    moved_to: str
    # D-89-17: Pass-1 frontmatter fields written by ingestor when source_meta present
    summary: Optional[str] = None
    author: Optional[str] = None
    domain: Optional[str] = None


@dataclass(frozen=True)
class Claim:
    """A versioned belief about an Entity.

    Mirrors the Claim Kuzu node table (schema v2.2). Identity is
    `claim_id` = `<claim_family_id>__v<N>` per D-83/84-6 F1; siblings in
    a family share `subject_slug + predicate_class_canonical +
    predicate_scope_slugs` and differ on polarity / modality /
    condition_text. Polarity is NOT part of `claim_id` (corrected from
    v1 draft per Codex v1 review Finding 1).

    Created by the O1 Promotion Pipeline; never authored by the
    Producer directly.
    """
    claim_id: str
    claim_family_id: str
    subject_slug: str
    predicate_class_canonical: str
    predicate_class_raw: str
    predicate_scope_slugs: list[str]
    object_slugs: list[str]
    polarity: str           # 'affirms' | 'denies'
    modality: str           # 'declarative' | ...
    condition_text: str     # qualifier text for `qualifies_or_extends` with refines_truth_conditions=true
    assertion_text: str
    confidence: float
    confidence_spread: float  # per D-83/84-12: spread of aggregated EVIDENCES.score values
    state: str              # 'active' | 'superseded' | 'retracted'
    version: int
    created_at: str
    last_revised_at: str

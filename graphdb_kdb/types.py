"""Public dataclasses returned by GraphDB queries.

#63.1 ships Page + Source. SyncResult / VerifyResult / RebuildResult arrive
in their respective sub-tasks (#63.2 / #63.5 / #63.6).
"""
from __future__ import annotations

from dataclasses import dataclass


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

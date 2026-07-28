"""#123 core types (spec §1.1).

Consumer-neutral by ratified design: nothing here distinguishes pass-1.5 from a
human/CLI/MCP caller (R2). The caller passes identities only — this package owns
all text projection, the snapshot hash and the audit artifact.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from common.paths import PageType

from .constants import MAX_EXPRESSIONS, MAX_RESULTS

# ---------------------------------------------------------------------------
# typed failures — fail hard at resolution, before any search work (#121 posture)
# ---------------------------------------------------------------------------


class SearchConfigError(Exception):
    """A route/config precondition failed. Raised before any rendering, body
    read or model call — never surfaced as a `GraphSearchResult`."""


class InvalidGraphSearchRequest(Exception):
    """The request was never valid, so there is no search to describe (codex P3
    option 2). Deliberately an exception rather than a fifth `status`: a
    `GraphSearchResult` implies an audit payload for work that was performed.
    Pins zero rendering, zero body reads, zero calls, zero StageRecords."""

    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


# ---------------------------------------------------------------------------
# request side
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class QueryPayload:
    """`text` is the query as the selector sees it; `expressions` are the
    discrete expressions hits are attributed to (pass-1.5: entity_search_keys;
    human: a single free-form expression)."""

    text: str
    expressions: tuple[str, ...] = ()

    def validate(self) -> None:
        """Enforced for EVERY consumer before rendering (D9)."""
        if len(self.expressions) > MAX_EXPRESSIONS:
            raise InvalidGraphSearchRequest(
                f"{len(self.expressions)} expressions exceeds MAX_EXPRESSIONS={MAX_EXPRESSIONS}",
                code="max_expressions_exceeded",
            )


@dataclass(frozen=True)
class SpaceEntity:
    """One eligible canonical identity. `page_type` is the `common.paths`
    Literal rather than a bare `str` (spec §1.1 says `str`; narrowed here) so a
    bad page_type fails at the type boundary instead of inside projection."""

    slug: str
    title: str
    page_type: PageType


@dataclass(frozen=True)
class GraphSnapshotRef:
    """The bound read-only graph identity (blueprint §6)."""

    schema_version: str
    active_entity_count: int
    space_fingerprint: str
    source_kind: str
    source_detail: str | None = None


ScopeKind = Literal["domain_subtree", "whole_graph", "explicit"]


@dataclass(frozen=True)
class SearchSpaceRef:
    """THE closed world for this search. Ordered deterministically at
    construction (slug ascending) so the snapshot hash is order-stable."""

    entities: tuple[SpaceEntity, ...]
    scope_kind: ScopeKind
    graph_ref: GraphSnapshotRef
    domain: str | None = None


@dataclass(frozen=True)
class SearchOpts:
    evidence_excerpt: bool = True  # v1 always true; reserved


@dataclass(frozen=True)
class GraphSearchRequest:
    query: QueryPayload
    search_space: SearchSpaceRef
    max_results: int = MAX_RESULTS
    opts: SearchOpts = field(default_factory=SearchOpts)


# ---------------------------------------------------------------------------
# result side
# ---------------------------------------------------------------------------

Status = Literal["completed", "abstain_empty_space", "budget_exceeded", "selector_failure"]
Execution = Literal[
    "not_executed", "thin_attempted", "two_stage_attempted", "fat_after_thin_failure"
]
EvidenceStatus = Literal["not_applicable", "complete", "partial"]
BudgetDetected = Literal["pre_call", "post_call"]
BudgetSide = Literal["input", "output"]


@dataclass(frozen=True)
class Hit:
    """Every hit is LLM-selected — there is no deterministic path anywhere in
    this contract. `matched_expressions` is resolved controller-side from the
    wire's `matched` labels (D8 as amended by D11) and may be empty (an
    unattributed hit)."""

    slug: str
    title: str
    page_type: PageType
    matched_expressions: tuple[str, ...] = ()

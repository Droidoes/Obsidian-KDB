"""#123 P3a.1 — the pass-1.5 search adapter (blueprint §4.1). UNWIRED.

The graph→search-space materializer and the core's only pipeline consumer:
materialize the eligible domain space (T1 excluded BEFORE the selector runs,
#128 page_type vocabulary enforced at this boundary), assemble the SD-1
QueryPayload, run one `graph_search` per source, sink the discriminated
SearchRunEnvelope (§5.1 B9: compact success / full failure, warn-only), and
stamp per-hit provenance via ONE batched `entity_first_run_ids` read.

Nothing calls `run_pass15` outside its tests yet — P3a.2b wires it into
`compile_source` step 1. Layering: this module imports {common, kdb_graph,
kdb_search}; the kdb_search core stays I/O-free and consumer-neutral.

Failure channels (§4.1, B4): typed outcomes (abstain_empty_space,
budget_exceeded, selector_failure) are result.status values — returned here as
an honest empty T2. Warn-and-continue applies to the two named post-search
steps only — the envelope write (OSError from the atomic write) and the
provenance read (what entity_first_run_ids can raise). InvalidGraphSearchRequest,
SearchConfigError, ContractViolation, and any unexpected exception PROPAGATE.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from functools import partial
from pathlib import Path

import kuzu

from common.atomic_io import atomic_write_json
from common.call_model import call_model
from common.llm_telemetry import safe_source_id
from common.model_pool import ModelSpec
from common.paths import PAGE_TYPES
from common.types import (
    MatchRecency,
    QueryKind,
    SearchBudgetRecord,
    SearchHitSummary,
    SearchStageSplit,
    SearchSummary,
    SourceFrontmatter,
)
from common.wiki_io import get_body
from kdb_graph import queries
from kdb_graph.schema import SCHEMA_VERSION as GRAPH_SCHEMA_VERSION
from kdb_search import projection
from kdb_search.artifact import (
    SEARCH_ENVELOPE_SCHEMA_VERSION,
    CompactSearchReceipt,
    SearchAuditPayload,
    SearchRunEnvelope,
    StageRecord,
    compact_receipt,
    receipt_kind_for,
    search_envelope_to_dict,
    space_fingerprint,
)
from kdb_search.projection import RenderedQuery
from kdb_search.result import BudgetRecord, GraphSearchResult
from kdb_search.search import graph_search
from kdb_search.types import (
    GraphSearchRequest,
    GraphSnapshotRef,
    QueryPayload,
    SearchSpaceRef,
    SpaceEntity,
)

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Pass15Outcome:
    """The adapter-internal contract (§4.1). t2_selection is None when no
    search ran (pre-Pass-1 gate); t1_slugs is the adapter's SINGLE T1 read,
    scoped to active entities (B1), passed through to the context builder."""

    search_ran: bool
    t2_selection: list[str] | None
    search_summary: SearchSummary | None
    envelope_written: bool
    t1_slugs: frozenset[str] | None


def _match_recency(first_run_id: str | None, run_id: str) -> MatchRecency:
    """§4.1 step 8: cohort if the stamp IS this run, pre_run if a different
    known id, age_unknown if None."""
    if first_run_id is None:
        return "age_unknown"
    return "cohort" if first_run_id == run_id else "pre_run"


def _truncated_indices(rendered: RenderedQuery) -> tuple[int, ...]:
    """Indices of the expressions the query-block renderer truncated (§5.2's
    query_truncated_indices) — empty when nothing was fitted."""
    original = rendered.original_fields.get("entity_search_keys")
    if original is None:
        return ()
    fitted = rendered.rendered_fields["entity_search_keys"]
    return tuple(i for i, (before, after) in enumerate(zip(original, fitted)) if before != after)


def _stage_splits(stages: tuple[StageRecord, ...]) -> tuple[SearchStageSplit, ...]:
    """Per-stage {thin, fat} token/cost splits (§4.5). provider_input_tokens is
    None when ANY attempt's count is unknown — never zero-coerced (B10)."""
    out: list[SearchStageSplit] = []
    for stage_name, label in (("thin_selection", "thin"), ("fat_selection", "fat")):
        rows = [s for s in stages if s.stage == stage_name]
        tokens: int | None = 0
        for row in rows:
            if row.provider_input_tokens is None:
                tokens = None
            elif tokens is not None:
                tokens += row.provider_input_tokens
        out.append(SearchStageSplit(
            stage=label,
            attempts=len(rows),
            provider_input_tokens=tokens if rows else None,
            cost_usd=sum(row.cost for row in rows),
        ))
    return tuple(out)


def _budget_record(record: BudgetRecord) -> SearchBudgetRecord:
    return SearchBudgetRecord(
        stage=record.stage,
        budget_estimate_tokens=record.budget_estimate_tokens,
        selector_window=record.selector_window,
        headroom_factor=record.headroom_factor,
        visible_output_allowance=record.visible_output_allowance,
        hidden_output_reserve=record.hidden_output_reserve,
        fits=record.fits,
        detected=record.detected,
        budget_side=record.budget_side,
        finish_reason_raw=record.finish_reason_raw,
        finish_reason_normalized=record.finish_reason_normalized,
    )


def _build_summary(
    *,
    result: GraphSearchResult,
    query_kind: QueryKind,
    selector: ModelSpec,
    rendered: RenderedQuery,
    space_entity_count: int,
) -> SearchSummary:
    """The §5.2 summary — built IMMEDIATELY after graph_search returns (§4.1
    step 6), before the failure-sensitive post-processing, so a later raise
    still leaves context_failed.search non-null when a search ran. artifact_path
    and hits are attached by the caller once known (frozen ⇒ replace)."""
    telemetry = result.telemetry
    audit = result.audit
    stages = audit.stages if audit is not None else ()
    return SearchSummary(
        search_ran=True,
        query_kind=query_kind,
        status=result.status,
        failure_class=telemetry.selector_failure_class,
        execution=result.execution,
        evidence_status=result.evidence_status,
        body_coverage=result.body_coverage,
        query_truncated_indices=_truncated_indices(rendered),
        eligible_space_size=telemetry.eligible_space_size,
        stage1_retained=telemetry.stage1_retained,
        stage2_pool_size=telemetry.stage2_pool_size,
        returned_entries=telemetry.returned_entries,
        valid_entry_yield=telemetry.valid_entry_yield,
        unattributed_hit_count=telemetry.unattributed_hit_count,
        retry_attempts=telemetry.retry_attempts,
        watched=tuple(telemetry.watched),
        concordance=telemetry.concordance,
        selector_provider=selector.provider,
        selector_model=selector.model,
        selector_route=selector.route.api_call_type,
        latency_ms=sum(s.latency_ms for s in stages),
        cost_usd=sum(s.cost for s in stages),
        budget_records=tuple(_budget_record(r) for r in telemetry.budget_records),
        stage2_budget_bound=telemetry.stage2_budget_bound,
        stage_splits=_stage_splits(stages),
        artifact_path=None,
        search_snapshot_hash=audit.search_snapshot_hash if audit is not None else None,
        space_entity_count=space_entity_count,
        hits=(),
    )


def run_pass15(
    conn: kuzu.Connection,
    *,
    frontmatter: SourceFrontmatter | None,
    selector: ModelSpec,
    vault_root: Path,
    state_root: Path,
    run_id: str,
    source_id: str,
    intra_run_order: int,
) -> Pass15Outcome:
    """§4.1's nine steps. One search per source; the adapter is seat-agnostic —
    the selector ModelSpec is passed in (R-P3a-5's seat is the run's choice)."""

    # 1. Gate — pre-Pass-1 sources do not search (R-P3a-3).
    if frontmatter is None:
        return Pass15Outcome(
            search_ran=False,
            t2_selection=None,
            search_summary=None,
            envelope_written=False,
            t1_slugs=None,
        )

    # 2. Materialize the space — the graph→search-space materializer. T1 is
    #    excluded BEFORE the selector runs (A1); the T1 read is single and
    #    shared with the context builder, scoped to active entities (B1).
    #    #128's page_type vocabulary check lives HERE, at the boundary.
    domain = frontmatter.domain or None
    active = queries.active_entities(conn)
    t1_raw = queries.source_supported_slugs(conn, source_id)
    t1_slugs = frozenset(t1_raw & set(active))
    if domain is None:
        candidates: list[str] = []
    else:
        candidates = sorted(
            (queries.domain_entity_slugs(conn, domain) & set(active)) - t1_raw
        )
    entities: list[SpaceEntity] = []
    dropped = 0
    for slug in candidates:
        row = active[slug]
        if row["page_type"] not in PAGE_TYPES:
            dropped += 1
            continue
        entities.append(SpaceEntity(slug=slug, title=row["title"], page_type=row["page_type"]))
    if dropped:
        log.warning(
            "pass-1.5 materialization dropped %d entities with non-vocabulary "
            "page_type for %s (#128)", dropped, source_id)
    manifest = tuple(entities)
    graph_ref = GraphSnapshotRef(
        schema_version=GRAPH_SCHEMA_VERSION,
        active_entity_count=len(active),
        space_fingerprint=space_fingerprint(manifest),
        source_kind="domain_subtree",
        source_detail=domain,
    )
    space_ref = SearchSpaceRef(
        entities=manifest,
        scope_kind="domain_subtree",
        graph_ref=graph_ref,
        domain=domain,
    )

    # 4. QueryPayload (SD-1 incl. author; State C ⇒ expressions [], valid by
    #    construction). query_kind is adapter-side telemetry — never sent to
    #    the core. The core resolves wire labels against the RENDERED
    #    expressions, so those are what the request carries.
    rendered = projection.render_query_block(
        summary=frontmatter.summary,
        domain=domain or "",
        author=frontmatter.author or "",
        key_themes=tuple(frontmatter.key_themes),
        expressions=tuple(frontmatter.entity_search_keys),
    )
    query_kind: QueryKind = "state_b" if frontmatter.entity_search_keys else "state_c"
    request = GraphSearchRequest(
        query=QueryPayload(text=rendered.text, expressions=rendered.rendered_expressions),
        search_space=space_ref,
    )

    # 5. One graph_search per source. body_reader binds THIS caller's
    #    vault_root (§6); ContentNotFoundError degrades to title-only inside
    #    projection. An empty space (missing domain, empty cluster) lands in
    #    the core's abstention terminal with `call` never invoked (step 3).
    result = graph_search(
        request,
        selector=selector,
        call=call_model,
        body_reader=partial(get_body, root=vault_root),
    )

    # 6. Search summary FIRST — before any failure-sensitive post-processing.
    summary = _build_summary(
        result=result,
        query_kind=query_kind,
        selector=selector,
        rendered=rendered,
        space_entity_count=len(manifest),
    )

    # 7. Envelope sink — warn-only (B4): an OSError from the atomic write is a
    #    counted warning, artifact_path stays null, the source continues.
    envelope_written = False
    artifact_path: str | None = None
    if result.audit is not None:
        kind = receipt_kind_for(result.status)
        receipt: CompactSearchReceipt | SearchAuditPayload = (
            result.audit if kind == "full" else compact_receipt(result.audit)
        )
        path = (
            state_root / "runs" / run_id / "search"
            / f"{safe_source_id(source_id)}.json"
        )
        envelope = SearchRunEnvelope(
            schema_version=SEARCH_ENVELOPE_SCHEMA_VERSION,
            run_id=run_id,
            source_id=source_id,
            intra_run_order=intra_run_order,
            receipt_kind=kind,
            receipt=receipt,
        )
        try:
            atomic_write_json(path, search_envelope_to_dict(envelope))
        except OSError as exc:
            log.warning(
                "pass-1.5 envelope write failed for %s: %s", source_id, exc)
        else:
            envelope_written = True
            artifact_path = str(path)

    # 8. Provenance read — ONE batched read over the validated hits; no
    #    resolver participates (codex c-2). Warn-and-continue (B4): a failure
    #    lands every hit in age_unknown and the source continues.
    hit_slugs = [h.slug for h in result.hits]
    provenance: dict[str, str | None] | None = None
    if hit_slugs:
        try:
            provenance = queries.entity_first_run_ids(conn, hit_slugs)
        except Exception as exc:  # what entity_first_run_ids can raise — named scope
            log.warning(
                "pass-1.5 provenance read failed for %s: %s; hits land in "
                "age_unknown", source_id, exc)
            provenance = None

    # 9. Ordered validated hits + the summary with its post-search attachments.
    hits = tuple(
        SearchHitSummary(
            slug=hit.slug,
            first_run_id=None if provenance is None else provenance.get(hit.slug),
            match_recency=_match_recency(
                None if provenance is None else provenance.get(hit.slug), run_id),
            matched_expressions=hit.matched_expressions,
        )
        for hit in result.hits
    )
    summary = replace(summary, artifact_path=artifact_path, hits=hits)
    return Pass15Outcome(
        search_ran=True,
        t2_selection=[hit.slug for hit in result.hits],
        search_summary=summary,
        envelope_written=envelope_written,
        t1_slugs=t1_slugs,
    )

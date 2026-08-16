"""task123_p3a_cost_projection — Task #123 P3a.0 pre-run cost projection (READ-ONLY).

Produces the LOWER / EXPECTED / UPPER cost projection for the Pass-1.5 semantic
graph search that blueprint v0.3 §8 ("P3a.0 — foundations") requires BEFORE the
selector seat is chosen between `deepseek-v4-flash` and `qwen3.7-flash`
(R-P3a-5, §4.7). No paid LLM calls: every number is measured from the sandbox
corpus (vault + Kuzu graph) or taken from the repo's own constants/registry.

Cost model (blueprint v0.3 §8 row, spec R4/D3/D-123-G):
  per compiled source, one search =
    THIN call: entire eligible identity space N as rendered thin lines
      (`kdb_graph_search.projection.render_thin_line` — slug + title + page_type)
    FAT call: stage-2 pool of whole bodies (filled to the 0.8 budget, capped by
      M = thins's retention ceiling) — skipped when thin retains zero (D3)
  terminal branches accounted separately:
    - empty eligible space (incl. missing Pass-1 domain — contracts.py:109
      "never a silent whole-graph fallback") => abstain, ZERO calls
    - thin retains zero candidates => thin-only, NO fat call
  N is a function of compile order (the graph grows after each successful
  compile), so per-source N is projected along the run, NOT measured once and
  multiplied by the source count.

Measured inputs (sandbox vault ~/Obsidian/Vault-in-place-test-run, read-only):
  - active entities / per-domain sizes / per-domain source counts (Kuzu graph)
  - entities contributed per compiled source (166 active / 31 sources) and the
    raw SUPPORTS-per-source mean (dedup vs authored)
  - mean rendered thin-line bytes over the 166 active entities
  - mean rendered fat-block bytes over the same entities, bodies read via
    `common.wiki_io.get_body` — the same read the production body_reader does
  - expected query-block bytes, rendered per graph Source with its real
    summary/domain/author (+ a stated synthesis for themes/keys, which the
    graph does not store)

Bytes->tokens: D5 measured families for the THIN stage
(`benchmark/truth/task123_search_calibration_v1.json`: deepseek-v4-flash
3.7632 B/token, qwen3.7-flash 3.7911 B/token). D5 measured the thin block
only, so the FAT stage uses the estimator (`ESTIMATOR_BYTES_PER_TOKEN` = 4)
for both seats — stated assumption.

Pricing: `common/models.json` price_in/price_out, USD per 1,000,000 tokens
(unit verified at common/llm_telemetry.py:180).

Usage:
  .venv/bin/python scripts/task123_p3a_cost_projection.py
"""
from __future__ import annotations

import json
import math
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path

# kdb_graph_search is not yet in the installed package list (P3a lands it); run from
# the repo root with the repo on the path, like the test suite does.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.model_pool import resolve_models_json
from common.wiki_io import ContentNotFoundError, get_body
from kdb_graph import queries
from kdb_graph.graphdb import GraphDB
from kdb_graph_search.budget import fat_input_byte_allowance
from kdb_graph_search.constants import (
    ESTIMATOR_BYTES_PER_TOKEN,
    M,
    MAX_RESULTS,
    PROVIDER_MAX_TOKENS_FAT,
    PROVIDER_MAX_TOKENS_THIN,
    SYSTEM_TEMPLATE_BUDGET_BYTES,
    VISIBLE_OUTPUT_ALLOWANCE_FAT,
    VISIBLE_OUTPUT_ALLOWANCE_THIN,
)
from kdb_graph_search.projection import (
    ProjectedEntity,
    render_fat_block,
    render_query_block,
    render_thin_line,
)
from kdb_graph_search.types import SpaceEntity

SANDBOX_VAULT = Path.home() / "Obsidian" / "Vault-in-place-test-run"
SANDBOX_GRAPH = SANDBOX_VAULT / "KDB" / "graph"
PRODUCTION_VAULT = Path.home() / "Obsidian"
CALIBRATION = Path("benchmark/truth/task123_search_calibration_v1.json")

SEAT_CANDIDATES = ("deepseek-v4-flash", "qwen3.7-flash")

# --- stated assumptions (not measurable with current data) -------------------
# The graph stores summary/author/domain per Source but NOT key_themes /
# entity_search_keys. Synthesized at pass-1-schema-typical sizes
# (5 themes x 40 B, 8 keys x 50 B) so the query block is mostly measured.
ASSUMED_THEMES = ("t" * 40,) * 5
ASSUMED_KEYS = ("k" * 50,) * 8
# Overlap scenarios for graph growth, as net entities contributed per compiled
# source. Measured today: raw authored 5.58/src (SUPPORTS mean), net 5.35/src
# (166 active / 31 sources) — a 4% dedup rate early in compile order.
RATE_LOWER = 2.7    # ~50% of authored entities already in graph at scale
RATE_EXPECTED = 5.35  # measured net contribution
RATE_UPPER = 5.58   # raw authored mean — near-zero dedup (near-linear growth)
# Terminal-branch rates (never fired live; assumptions, direction chosen so
# UPPER is cost-maximal): fraction of searches that abstain on empty space
# (missing Pass-1 domain / undecided) and that stop thin-only (D3).
EMPTY_RATE = {"LOWER": 0.05, "EXPECTED": 0.02, "UPPER": 0.0}
THIN_ZERO_RATE = {"LOWER": 0.05, "EXPECTED": 0.02, "UPPER": 0.0}


# ---------------------------------------------------------------------------
# measurement
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Corpus:
    active_entities: int
    compiled_sources: int
    supports_mean_per_source: float
    domain_entity_counts: dict[str, int]
    domain_source_counts: dict[str, int]
    thin_line_mean_bytes: float
    fat_block_mean_bytes: float
    slug_mean_bytes: float
    query_block_mean_bytes: float
    body_missing: int


def measure_corpus() -> Corpus:
    with GraphDB(SANDBOX_GRAPH, read_only=True) as gdb:
        conn = gdb.conn
        entities = queries.active_entities(conn)

        domain_entity_counts: dict[str, int] = {}
        r = conn.execute(
            "MATCH (e:Entity)-[:BELONGS_TO]->(d:Domain) WHERE e.status='active' "
            "RETURN d.name, COUNT(e)"
        )
        while r.has_next():
            row = r.get_next()
            domain_entity_counts[row[0]] = int(row[1])

        domain_source_counts: dict[str, int] = {}
        supports_counts: list[int] = []
        summaries: list[tuple[str, str, str]] = []
        r = conn.execute("MATCH (s:Source) RETURN s.summary, s.author, s.domain")
        while r.has_next():
            row = r.get_next()
            domain = row[2] or "<none>"
            domain_source_counts[domain] = domain_source_counts.get(domain, 0) + 1
            summaries.append((row[0] or "", row[1] or "", row[2] or ""))
        compiled_sources = sum(domain_source_counts.values())

        r = conn.execute(
            "MATCH (s:Source)-[:SUPPORTS]->(e:Entity) RETURN s.source_id, COUNT(e)"
        )
        while r.has_next():
            supports_counts.append(int(r.get_next()[1]))

    thin_sizes: list[int] = []
    fat_sizes: list[int] = []
    slug_sizes: list[int] = []
    body_missing = 0
    for slug, meta in entities.items():
        entity = SpaceEntity(slug=slug, title=meta["title"], page_type=meta["page_type"])
        thin_sizes.append(len(render_thin_line(entity).encode()) + 1)  # + "\n"
        slug_sizes.append(len(slug.encode()))
        try:
            body = get_body(slug, meta["page_type"], root=SANDBOX_VAULT)
        except ContentNotFoundError:
            body_missing += 1
            body = None
        if body is None:
            fat_sizes.append(len(render_thin_line(entity).encode()) + 1)
        else:
            fat_sizes.append(
                len(render_fat_block(ProjectedEntity(entity=entity, body=body)).encode()) + 1
            )

    query_sizes = [
        len(
            render_query_block(
                summary=summary,
                domain=domain,
                author=author,
                key_themes=ASSUMED_THEMES,
                expressions=ASSUMED_KEYS,
            ).text.encode()
        )
        for summary, author, domain in summaries
    ]

    return Corpus(
        active_entities=len(entities),
        compiled_sources=compiled_sources,
        supports_mean_per_source=statistics.mean(supports_counts),
        domain_entity_counts=domain_entity_counts,
        domain_source_counts=domain_source_counts,
        thin_line_mean_bytes=statistics.mean(thin_sizes),
        fat_block_mean_bytes=statistics.mean(fat_sizes),
        slug_mean_bytes=statistics.mean(slug_sizes),
        query_block_mean_bytes=statistics.mean(query_sizes),
        body_missing=body_missing,
    )


def count_vault_sources() -> tuple[int, int]:
    """(sandbox signal sources, production vault eligible sources), .md only,
    KDB/ + hidden dirs excluded; Daily Notes / Projects are force_noise per
    ingestion/config/scope-config.yaml and never compile (no search)."""
    def eligible(root: Path) -> int:
        n = 0
        for p in root.rglob("*.md"):
            rel = p.relative_to(root)
            parts = rel.parts
            if parts[0] in ("KDB", "Daily Notes", "Projects"):
                continue
            if any(part.startswith(".") for part in parts):
                continue
            n += 1
        return n

    sandbox = eligible(SANDBOX_VAULT)
    # The production vault nests the sandbox copy; don't count it twice.
    production = eligible(PRODUCTION_VAULT) - sandbox
    return sandbox, production


def d5_thin_bytes_per_token() -> dict[str, float]:
    data = json.loads(CALIBRATION.read_text(encoding="utf-8"))
    return {m["model_id"]: m["bytes_per_token"] for m in data["measurements"]}


# ---------------------------------------------------------------------------
# projection
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ScenarioResult:
    searches_total: int
    searches_executed: int
    searches_thin_only: int
    searches_abstained: int
    thin_input_tokens: int
    fat_input_tokens: int
    output_tokens: int
    cost_usd: float


def project(
    *,
    sources: int,
    domain_source_shares: dict[str, float],
    net_rate: float,
    empty_rate: float,
    thin_zero_rate: float,
    corpus: Corpus,
    thin_bpt: float,
    output_per_executed: tuple[float, float],
    price_in: float,
    price_out: float,
    fat_allowance_bytes: int,
) -> ScenarioResult:
    """Sum per-source searches along compile order. Under linear growth the
    per-domain sum r*n*(n-1)/2 is interleaving-independent, so compile ORDER
    within the mix does not move the total (stated in the write-up)."""
    overhead_bytes = SYSTEM_TEMPLATE_BUDGET_BYTES + corpus.query_block_mean_bytes
    fat_pool_cap = fat_allowance_bytes / max(corpus.fat_block_mean_bytes, 1)

    thin_in = fat_in = 0.0
    for domain, share in domain_source_shares.items():
        n_d = sources * share
        # entities already in this domain's space when source j compiles:
        # N_j = net_rate * (j-1); own-supported subtraction ~= 0 (first compile).
        total_n = net_rate * n_d * (n_d - 1) / 2
        thin_in += (overhead_bytes + total_n * corpus.thin_line_mean_bytes / n_d) * n_d / thin_bpt
        # fat pool: min(retained = min(N_j, M), budget fill). The budget fill
        # (~3 MB / ~1 kB bodies >> M=150) never binds at 1M-window seats — the
        # pool is M-bound; the min() is kept so the claim is executable.
        retained_sum = sum(min(min(net_rate * j, M), fat_pool_cap) for j in range(int(n_d)))
        retained_sum += (n_d - int(n_d)) * min(min(net_rate * int(n_d), M), fat_pool_cap)
        fat_in += (overhead_bytes * n_d + retained_sum * corpus.fat_block_mean_bytes) / ESTIMATOR_BYTES_PER_TOKEN

    executed = sources * (1 - empty_rate)
    thin_only = executed * thin_zero_rate
    fat_calls = executed - thin_only
    # thin-only searches skip the fat call: scale fat input down.
    fat_in *= fat_calls / executed if executed else 0.0

    out_thin, out_fat = output_per_executed
    output_tokens = executed * out_thin + fat_calls * out_fat
    input_tokens = thin_in + fat_in
    cost = price_in / 1e6 * input_tokens + price_out / 1e6 * output_tokens
    return ScenarioResult(
        searches_total=sources,
        searches_executed=int(round(executed)),
        searches_thin_only=int(round(thin_only)),
        searches_abstained=sources - int(round(executed)),
        thin_input_tokens=int(thin_in),
        fat_input_tokens=int(fat_in),
        output_tokens=int(output_tokens),
        cost_usd=cost,
    )


def main() -> None:
    corpus = measure_corpus()
    sandbox_sources, production_sources = count_vault_sources()
    d5 = d5_thin_bytes_per_token()

    print("=" * 78)
    print("MEASURED INPUTS (sandbox vault + graph, read-only)")
    print("=" * 78)
    print(f"graph active entities            : {corpus.active_entities}")
    print(f"graph compiled sources           : {corpus.compiled_sources}")
    print(f"net entities / compiled source   : {corpus.active_entities / corpus.compiled_sources:.2f}")
    print(f"raw SUPPORTS / source (authored) : {corpus.supports_mean_per_source:.2f}")
    print(f"domain entity counts             : {corpus.domain_entity_counts}")
    print(f"domain source counts             : {corpus.domain_source_counts}")
    print(f"thin line mean bytes (+newline)  : {corpus.thin_line_mean_bytes:.1f}")
    print(f"fat block mean bytes (+newline)  : {corpus.fat_block_mean_bytes:.1f}")
    print(f"slug mean bytes                  : {corpus.slug_mean_bytes:.1f}")
    print(f"query block mean bytes (see note): {corpus.query_block_mean_bytes:.0f}")
    print(f"bodies missing (graph/disk drift): {corpus.body_missing}")
    print(f"sandbox signal sources (.md)     : {sandbox_sources}")
    print(f"production eligible sources (.md): {production_sources}")
    print(f"D5 thin bytes/token              : { {k: d5[k] for k in SEAT_CANDIDATES} }")
    print(f"fat bytes/token (estimator, both): {ESTIMATOR_BYTES_PER_TOKEN}")
    print()

    total_sources = sum(corpus.domain_source_counts.values())
    shares = {d: c / total_sources for d, c in corpus.domain_source_counts.items()}

    specs = {m: resolve_models_json(m) for m in SEAT_CANDIDATES}
    fat_allowance = {m: fat_input_byte_allowance(specs[m]) for m in SEAT_CANDIDATES}

    scenarios = {
        "LOWER": dict(net_rate=RATE_LOWER),
        "EXPECTED": dict(net_rate=RATE_EXPECTED),
        "UPPER": dict(net_rate=RATE_UPPER),
    }
    # Output per search (thin, fat):
    #   LOWER    — wire-derived: retained-slug / selection JSON at measured sizes
    #   EXPECTED — spec visible allowances (20,000 + 10,000) per the P3a.0 brief
    #   UPPER    — provider caps sent as max_tokens (36,000 + 26,000), both
    #              under the 65,536 run cap (§4.8 registry edit)
    def lower_out() -> tuple[float, float]:
        thin = M * (corpus.slug_mean_bytes + 9) / 3.76
        fat = MAX_RESULTS * (corpus.slug_mean_bytes + 40) / ESTIMATOR_BYTES_PER_TOKEN
        return thin, fat

    output_modes = {
        "LOWER": lower_out(),
        "EXPECTED": (VISIBLE_OUTPUT_ALLOWANCE_THIN, VISIBLE_OUTPUT_ALLOWANCE_FAT),
        "UPPER": (PROVIDER_MAX_TOKENS_THIN, PROVIDER_MAX_TOKENS_FAT),
    }

    for scale_name, scale_sources in (
        ("VAULT SCALE (production ingestion)", production_sources),
        ("SANDBOX GATE RUN", sandbox_sources),
    ):
        print("=" * 78)
        print(f"{scale_name}: {scale_sources} sources")
        print("=" * 78)
        header = (
            f"{'scenario':<9} {'model':<18} {'exec/thin1/abst':<16} "
            f"{'thin_in':>12} {'fat_in':>12} {'out':>12} {'cost_usd':>10}"
        )
        print(header)
        print("-" * len(header))
        for name, kw in scenarios.items():
            for model in SEAT_CANDIDATES:
                res = project(
                    sources=scale_sources,
                    domain_source_shares=shares,
                    net_rate=kw["net_rate"],
                    empty_rate=EMPTY_RATE[name],
                    thin_zero_rate=THIN_ZERO_RATE[name],
                    corpus=corpus,
                    thin_bpt=d5[model],
                    output_per_executed=output_modes[name],
                    price_in=specs[model].price_in,
                    price_out=specs[model].price_out,
                    fat_allowance_bytes=fat_allowance[model],
                )
                branches = f"{res.searches_executed}/{res.searches_thin_only}/{res.searches_abstained}"
                print(
                    f"{name:<9} {model:<18} {branches:<16} "
                    f"{res.thin_input_tokens:>12,} {res.fat_input_tokens:>12,} "
                    f"{res.output_tokens:>12,} {res.cost_usd:>10.2f}"
                )
        print()

    print("fat allowance bytes per seat (0.8 budget less fat output reserve):")
    for m in SEAT_CANDIDATES:
        print(f"  {m:<18} {fat_allowance[m]:>12,} B "
              f"(~{fat_allowance[m] / corpus.fat_block_mean_bytes:,.0f} mean bodies "
              f">> M={M} — pool is M-bound, not budget-bound)")


if __name__ == "__main__":
    main()

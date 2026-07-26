"""#123 pre-flight budget estimator + the output envelope (spec §7.2, D6/D7/D9).

Two quantities that look interchangeable and are not:

  * `estimate_input_tokens` — the **calibrated estimate** (`ceil(bytes / 4)`) that
    the pre-flight guard runs on. It can under-call; the 0.8 headroom explicitly
    carries that density variance, and the "never underestimates" claim is
    withdrawn (opus5 J3).
  * `worst_case_input_tokens` — the **pathological bound** (`tokens == bytes`) that
    the M=100 static guarantee rests on, valid only under `tokens_lte_bytes`.

The guarantee is a proof; the estimate is a guard. Conflating them would turn a
by-construction argument into a measurement, which is the exact regression the
K1→L1→M1→N2 lineage closed.

D9 keeps **four** output quantities distinct, because `max_tokens` caps the whole
completion rather than the visible JSON: the visible response, the hidden
reasoning reserve, the provider cap sent on the wire, and the context reservation.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Literal

from common.model_pool import ModelSpec

from .constants import (
    BUDGET_HEADROOM,
    ESTIMATOR_BYTES_PER_TOKEN,
    EXCERPT_BLOCK_CEILING_BYTES,
    HIDDEN_OUTPUT_RESERVE,
    M,
    MAX_EXPRESSIONS,
    MAX_RESULTS,
    MAX_SLUG_LEN,
    QUERY_BLOCK_CEILING_BYTES,
    SMALLEST_POOL_BUDGET_TOKENS,
    SYSTEM_TEMPLATE_BUDGET_BYTES,
    VISIBLE_OUTPUT_ALLOWANCE_FAT,
    VISIBLE_OUTPUT_ALLOWANCE_THIN,
    WIRE_INDEX_BASE,
    WIRE_JSON_SEPARATORS,
)
from .types import SearchConfigError

Stage = Literal["thin", "fat"]

_VISIBLE_ALLOWANCE: dict[Stage, int] = {
    "thin": VISIBLE_OUTPUT_ALLOWANCE_THIN,
    "fat": VISIBLE_OUTPUT_ALLOWANCE_FAT,
}


# ---------------------------------------------------------------------------
# the output envelope — four distinct quantities (D9 / codex O1)
# ---------------------------------------------------------------------------


def visible_output_allowance(stage: Stage) -> int:
    """Quantity 1: the visible JSON response. Bounded exactly (§7.0a)."""
    return _VISIBLE_ALLOWANCE[stage]


def hidden_output_reserve() -> int:
    """Quantity 2: hidden reasoning/thought tokens.

    An owner-selected POLICY reserve, not a measured bound: hidden output is
    unenforceable at two of three D4 providers. The residual is typed
    (`budget_side: output`), never presented as proof.
    """
    return HIDDEN_OUTPUT_RESERVE


def provider_max_tokens(stage: Stage) -> int:
    """Quantity 3: what goes on the wire as `max_tokens` — the WHOLE completion,
    hidden tokens included."""
    return visible_output_allowance(stage) + hidden_output_reserve()


def reserved_output_tokens(stage: Stage) -> int:
    """Quantity 4: what the pre-flight reserves from the context window.

    Numerically equal to the provider cap, and deliberately a separate function:
    they answer different questions (what the provider will stop at vs what we
    refuse to spend), and a future change to one must not silently move the other.
    """
    return provider_max_tokens(stage)


# ---------------------------------------------------------------------------
# exact max serialization — the executable authority for the allowances (§7.0a)
# ---------------------------------------------------------------------------


def _dump(obj: object) -> str:
    """The normative serializer. A named constant, never "compact JSON" in prose —
    the unnamed serializer is what produced the superseded 12,315/8,404 figures."""
    return json.dumps(obj, separators=WIRE_JSON_SEPARATORS, ensure_ascii=False)


def _max_indices(expression_count: int) -> list[int]:
    return list(range(WIRE_INDEX_BASE, WIRE_INDEX_BASE + expression_count))


def schema_maximum_thin_document(*, retained: int = M) -> str:
    """Every value at its declared maximum: M slugs of MAX_SLUG_LEN."""
    return _dump({"retained": ["x" * MAX_SLUG_LEN] * retained})


def schema_maximum_fat_document(
    *, selections: int = MAX_RESULTS, expressions: int = MAX_EXPRESSIONS
) -> str:
    """Every value at its declared maximum. `expressions` is a parameter because
    the FAT maximum is a FUNCTION of `MAX_EXPRESSIONS`, not a free constant — which
    is precisely why D9 moved that bound into the core contract."""
    indices = _max_indices(expressions)
    return _dump(
        {
            "selections": [{"slug": "x" * MAX_SLUG_LEN, "matched": indices}] * selections,
            "unresolved": indices,
        }
    )


def exact_max_visible_bytes(stage: Stage, *, expressions: int = MAX_EXPRESSIONS) -> int:
    document = (
        schema_maximum_thin_document()
        if stage == "thin"
        else schema_maximum_fat_document(expressions=expressions)
    )
    return len(document.encode())


# ---------------------------------------------------------------------------
# input estimation
# ---------------------------------------------------------------------------


def estimate_input_tokens(rendered_bytes: int) -> int:
    """The calibrated pre-flight estimate — ONE method for both stages (D6,
    Joseph's consistency ruling)."""
    return math.ceil(rendered_bytes / ESTIMATOR_BYTES_PER_TOKEN)


def worst_case_input_tokens(rendered_bytes: int) -> int:
    """The pathological 1-token-per-byte bound. Sound only under
    `tokens_lte_bytes`; this is the static guarantee's arithmetic, never the
    estimator's."""
    return rendered_bytes


def context_budget(spec: ModelSpec) -> int:
    """The usable window after headroom. Computed here rather than via
    `model_pool.fits_context`, which takes a pre-computed estimate and has no
    headroom concept — different semantics, noted rather than force-fitted (G6)."""
    if spec.ctx_window is None:
        raise SearchConfigError(f"selector route {spec.id!r} declares no ctx_window")
    return math.floor(spec.ctx_window * BUDGET_HEADROOM)


# ---------------------------------------------------------------------------
# route resolution — fail hard, before any work
# ---------------------------------------------------------------------------


def resolve_selector_route(spec: ModelSpec) -> ModelSpec:
    """Assert every precondition a selector route must satisfy, before any
    rendering, body read or call.

    `tokens_lte_bytes` is checked HERE and not at Gate 1: `load_pool` cannot know
    which entries will serve as a semantic selector, and failing the whole pool
    over a premise only this consumer needs would break every unrelated call
    (codex N4 + opus5 N3).
    """
    if spec.ctx_window is None:
        raise SearchConfigError(f"selector route {spec.id!r} declares no ctx_window")
    if spec.tokens_lte_bytes is not True:
        raise SearchConfigError(
            f"selector route {spec.id!r} does not declare tokens_lte_bytes; the output "
            "allowances are proved through that premise, so it cannot be assumed"
        )
    for stage in ("thin", "fat"):
        required = provider_max_tokens(stage)  # type: ignore[arg-type]
        if spec.max_output_tokens is not None and required > spec.max_output_tokens:
            raise SearchConfigError(
                f"selector route {spec.id!r} caps output at {spec.max_output_tokens} "
                f"tokens, below the {stage} envelope's {required}"
            )
    return spec


# ---------------------------------------------------------------------------
# the pre-flight verdict
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BudgetVerdict:
    fits: bool
    stage: Stage
    estimated_input_tokens: int
    reserved_output_tokens: int
    context_budget_tokens: int

    @property
    def total_reserved_tokens(self) -> int:
        return self.estimated_input_tokens + self.reserved_output_tokens


def preflight(stage: Stage, *, rendered_bytes: int, spec: ModelSpec) -> BudgetVerdict:
    """R2's uniform pre-flight. A `fits=False` verdict is `budget_exceeded` with
    zero spend and no retry — deterministic, so the same request fails identically.
    """
    reserved = reserved_output_tokens(stage)
    estimated = estimate_input_tokens(rendered_bytes)
    budget = context_budget(spec)
    return BudgetVerdict(
        fits=estimated + reserved <= budget,
        stage=stage,
        estimated_input_tokens=estimated,
        reserved_output_tokens=reserved,
        context_budget_tokens=budget,
    )


# ---------------------------------------------------------------------------
# the M=100 static guarantee (D7) — sizing, not measurement
# ---------------------------------------------------------------------------


def fat_worst_case_request_bytes(*, retained: int = M) -> int:
    """Fat's absolute worst case: every retained entity at the policy-v2 ceiling,
    a saturated query block, and the declared system/template reserve."""
    return (
        retained * EXCERPT_BLOCK_CEILING_BYTES
        + QUERY_BLOCK_CEILING_BYTES
        + SYSTEM_TEMPLATE_BUDGET_BYTES
    )


def fat_static_guarantee_tokens(*, retained: int = M) -> int:
    """The guarantee's total: the pathological input bound plus the fat stage's
    provider-total reserved output. Compared against
    `SMALLEST_POOL_BUDGET_TOKENS`, it holds BY CONSTRUCTION — no estimation
    anywhere in fat's safety path at pool windows.
    """
    return worst_case_input_tokens(fat_worst_case_request_bytes(retained=retained)) + (
        reserved_output_tokens("fat")
    )


__all__ = [
    "BudgetVerdict",
    "Stage",
    "context_budget",
    "estimate_input_tokens",
    "exact_max_visible_bytes",
    "fat_static_guarantee_tokens",
    "fat_worst_case_request_bytes",
    "hidden_output_reserve",
    "preflight",
    "provider_max_tokens",
    "reserved_output_tokens",
    "resolve_selector_route",
    "schema_maximum_fat_document",
    "schema_maximum_thin_document",
    "visible_output_allowance",
    "worst_case_input_tokens",
]

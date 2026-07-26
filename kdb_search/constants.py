"""#123 §7.0 constants — the single normative source.

Blueprint §7.0 is the prose authority; this module is its executable form. Every
other module and every test derives from these names, never from a figure copied
out of a document. That rule exists because four consecutive confirmation rounds
each caught a stale restatement, and the round that added §7.0a shipped a byte
figure computed from an unnamed serializer (one-based indices under
`separators=(",", ": ")`, where the contract is zero-based compact).
"""

from common.paths import MAX_SLUG_LEN  # noqa: F401  — re-exported: one slug bound, not two

# ---------------------------------------------------------------------------
# selection caps
# ---------------------------------------------------------------------------

#: Thin retention + fat hydration cap (D7). Sized so the fat request's absolute
#: worst case fits the configured pool's smallest budget by construction.
M = 100

#: Global result cap (spec §3.2 merged page_cap). `max_results` may be lower.
MAX_RESULTS = 50

#: Declared in the core QueryPayload (D9) — the sole derivation source for the
#: wire's index caps, the index digit width and the FAT allowance. pass-1.5
#: satisfies it by construction (`entity_search_keys` maxItems: 10), but the
#: bound is the core's, not the adapter's: R2 forbids per-consumer contracts.
MAX_EXPRESSIONS = 10

# ---------------------------------------------------------------------------
# wire serialization — NORMATIVE (codex, v0.10 review)
# ---------------------------------------------------------------------------

#: The exact JSON separators the wire maxima are computed with. Named as a
#: constant rather than described as "compact JSON" in prose: the unnamed
#: serializer is precisely what produced the superseded 12,315/8,404 figures.
WIRE_JSON_SEPARATORS = (",", ":")

#: Expression indices on the wire are zero-based — `[0, len(expressions))`
#: (spec §2.3). The digit width in the exact-maxima computation follows from
#: this plus MAX_EXPRESSIONS.
WIRE_INDEX_BASE = 0

# ---------------------------------------------------------------------------
# projection ceilings
# ---------------------------------------------------------------------------

#: Excerpt policy version recorded in the artifact.
EXCERPT_POLICY_VERSION = "2"

#: Policy-v1 word cap (a safety bound, not a sizing lever — SD-3).
EXCERPT_WORD_CAP = 250

#: Sentence extension window: +10% of the word cap.
EXCERPT_SENTENCE_EXTENSION_WORDS = EXCERPT_WORD_CAP // 10

#: Policy v2: the *rendered* per-entity fat block (identity line + excerpt field
#: + delimiters) never exceeds this. The word cap alone cannot bound bytes — one
#: 200-character URL is one "word". Binds on nothing in fixture v1 (largest
#: rendered block 2,209 B), which is why v1 needed no regeneration.
EXCERPT_BLOCK_CEILING_BYTES = 2_500

#: The rendered query block ceiling, enforced by per-field allocations below.
QUERY_BLOCK_CEILING_BYTES = 4_096

#: Deterministic per-field byte allocations (D7 / codex L2). Every one of these
#: pass-1 fields is schema-unbounded (`pass1_schema.py:77-89`), so summary-only
#: truncation was an observed-input assumption rather than a projector property.
#: Allocations are enforced on each field's **rendered contribution**, not on its
#: raw content. That is the only reading under which the total ceiling is a hard
#: property: `key_themes` carries no `maxItems`, so 1,024 one-byte themes satisfy
#: a raw aggregate cap while their rendered `    - ` prefixes alone cost ~14 kB.
QUERY_FIELD_ALLOCATIONS = {
    "author": 256,
    "entity_search_keys_per_item": 128,
    "key_themes_aggregate": 1_024,
    #: SD-1's ceiling list omits `domain` because pass-1 constrains it to an enum
    #: (`pass1_schema.py`), so it is not an unbounded input *for that consumer*.
    #: The core caps it anyway: R2 forbids per-consumer contracts, and the
    #: ceiling has to hold against a P5b CLI/MCP caller too. Sized to match the
    #: per-key allocation — both are short identifiers.
    "domain": 128,
    # `summary` takes the remainder of QUERY_BLOCK_CEILING_BYTES
}

# ---------------------------------------------------------------------------
# output envelope (D9 — visible vs provider-total)
# ---------------------------------------------------------------------------

#: Visible-JSON allowances. Each is >= the exact max serialization of the
#: fully-bounded wire under `tokens_lte_bytes` (tokens <= bytes), so no
#: bytes-per-token density step survives anywhere in the output path.
VISIBLE_OUTPUT_ALLOWANCE_THIN = 13_000
VISIBLE_OUTPUT_ALLOWANCE_FAT = 10_000

#: Owner-selected POLICY reserve for hidden reasoning/thought tokens (D9,
#: confirmed by Joseph 2026-07-26). Not a measured bound: hidden output is
#: unbounded and unenforceable at two of the three D4 providers — gpt carries
#: `reasoning_effort: low`, gemini `thinking_level: minimal` (full-off
#: unsupported), and `_THINKING_DISABLE_EXTRA_BODY` maps neither. The residual
#: risk is typed (`budget_side: output`) rather than presented as proof.
HIDDEN_OUTPUT_RESERVE = 16_000

#: What actually goes to the provider as `max_tokens` — the whole completion,
#: hidden tokens included. Asserted <= the route's `max_output_tokens` at
#: resolution.
PROVIDER_MAX_TOKENS_THIN = VISIBLE_OUTPUT_ALLOWANCE_THIN + HIDDEN_OUTPUT_RESERVE
PROVIDER_MAX_TOKENS_FAT = VISIBLE_OUTPUT_ALLOWANCE_FAT + HIDDEN_OUTPUT_RESERVE

# ---------------------------------------------------------------------------
# pre-flight estimator (R2 / D6)
# ---------------------------------------------------------------------------

#: One calculation method for BOTH stages (D6, Joseph's consistency ruling).
ESTIMATOR_BYTES_PER_TOKEN = 4

#: The guardrail. The "never underestimates" claim stays withdrawn — this
#: headroom explicitly carries density variance (opus5 J3).
BUDGET_HEADROOM = 0.8


#: Declared byte budget for the rendered system block + user wrapper — the
#: "~3 kB system/template" line in the M=100 static guarantee (blueprint §7.0a).
#: Recorded as a constant rather than left as prose so the guarantee is a checkable
#: sum. **P2 obligation:** the real rendered templates must be asserted against
#: this, and this figure raised (with the guarantee recomputed) if they exceed it.
#: Until then it is a declared reserve, not a measurement.
SYSTEM_TEMPLATE_BUDGET_BYTES = 3_072

#: The pool's smallest effective context budget: gpt-5.4-mini's 400,000 window at
#: BUDGET_HEADROOM. The M=100 static guarantee is stated against this.
SMALLEST_POOL_BUDGET_TOKENS = 320_000

"""#123 §7.0 constants — the single normative source.

Blueprint §7.0 is the prose authority; this module is its executable form. Every
other module and every test derives from these names, never from a figure copied
out of a document. That rule exists because four consecutive confirmation rounds
each caught a stale restatement, and the round that added §7.0a shipped a byte
figure computed from an unnamed serializer (one-based indices under
`separators=(",", ": ")`, where the contract of the day was zero-based compact —
since replaced by letter labels, D11).
"""

from common.paths import MAX_SLUG_LEN  # noqa: F401  — re-exported: one slug bound, not two

# ---------------------------------------------------------------------------
# selection caps
# ---------------------------------------------------------------------------

#: **Thin's retention ceiling, and nothing else (D-123-A, 2026-08-02).** Also the
#: small-space threshold. It was 100 and doubled as fat's hydration cap, sized so
#: `M x EXCERPT_BLOCK_CEILING_BYTES` fit the smallest pool budget by construction.
#: That guarantee is withdrawn (D-123-D): the stage-2 pool is now filled to the
#: 0.8 budget entity by entity, so a request that does not fit is never built and
#: no per-entity ceiling is needed to bound one. `M` is no longer an input to any
#: guarantee — raising it costs recall reach, not safety.
M = 150

#: Global result cap (spec §3.2 merged page_cap). `max_results` may be lower.
MAX_RESULTS = 50

#: Declared in the core QueryPayload (D9) — the sole derivation source for the
#: wire's label caps, the label vocabulary and the FAT allowance. pass-1.5
#: satisfies it by construction (`entity_search_keys` maxItems: 10), but the
#: bound is the core's, not the adapter's: R2 forbids per-consumer contracts.
MAX_EXPRESSIONS = 10

#: Logical attempts per executed stage (blueprint §8, frozen by codex c-1). One
#: `StageRecord` per logical attempt, so this is also the per-stage `StageRecord`
#: ceiling. SDK transport sub-retries are the provider's business and are never
#: counted here.
MAX_ATTEMPTS_PER_STAGE = 2

# ---------------------------------------------------------------------------
# wire serialization — NORMATIVE (codex, v0.10 review)
# ---------------------------------------------------------------------------

#: The exact JSON separators the wire maxima are computed with. Named as a
#: constant rather than described as "compact JSON" in prose: the unnamed
#: serializer is precisely what produced the superseded 12,315/8,404 figures.
WIRE_JSON_SEPARATORS = (",", ":")

#: Expressions are addressed on the wire by **letter key-label** — `A`, `B`, … —
#: not by index (D11, replacing D8's zero-based `WIRE_INDEX_BASE = 0`). A letter
#: is not an ordinal, so the 0-vs-1 base ambiguity — a *protocol* ambiguity that
#: produces a *systematic* mis-attribution rather than a visible error — ceases
#: to exist. It also unifies the wire under one rule: every identifier the
#: selector returns is a verbatim echo of something printed in the prompt (slugs
#: already were; indices had to be computed from position).
WIRE_LABEL_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def expression_labels(count: int) -> tuple[str, ...]:
    """The wire labels for `count` expressions, in request order.

    The single derivation source for the rendered markers (`projection.py`), the
    accepted response vocabulary (`response.py`) and the exact-maxima documents
    (`budget.py`) — so no caller can drift from another.

    Bounded by the alphabet rather than extended to `AA`: `MAX_EXPRESSIONS` is 10
    and the FAT allowance is exceeded at 14 labels (§7.0a), so the byte bound
    binds long before the alphabet does. A multi-letter scheme would be untested
    reach for a case the contract already forbids.
    """
    if not 0 <= count <= len(WIRE_LABEL_ALPHABET):
        raise ValueError(
            f"{count} expressions cannot be labelled: the wire alphabet holds "
            f"{len(WIRE_LABEL_ALPHABET)} (MAX_EXPRESSIONS={MAX_EXPRESSIONS})"
        )
    return tuple(WIRE_LABEL_ALPHABET[:count])


def wire_vocabulary(count: int) -> tuple[str, ...]:
    """The labels a response may legitimately carry, for a request of `count`
    expressions — the lenient sibling of `expression_labels()`, sharing its one
    alphabet so the two cannot drift.

    **Total where `expression_labels()` raises**, deliberately. An over-long
    request is refused at request validation (`QueryPayload` ⇒
    `InvalidGraphSearchRequest(code="max_expressions_exceeded")`), which is where
    D9.2 puts that bound, so this branch is unreachable in production. It is total
    anyway because the response path carries §2.3's contract that **a parseable
    response is never discarded** — and discarded-by-exception is still discarded.
    Raising belongs on the render and exact-maxima paths, which state a maximum;
    salvage states the opposite.
    """
    return tuple(WIRE_LABEL_ALPHABET[:count])

# ---------------------------------------------------------------------------
# projection ceilings
# ---------------------------------------------------------------------------

#: **Body truncation is gone (D-123-C, 2026-08-02).** `EXCERPT_WORD_CAP` (250),
#: `EXCERPT_SENTENCE_EXTENSION_WORDS` (25), `EXCERPT_BLOCK_CEILING_BYTES` (2,500)
#: and `EXCERPT_POLICY_VERSION` all lived here. Measured against the data they
#: protected: the byte ceiling had fired 0/163 fixture and 0/83 live, the word cap
#: 2/163 and 0/83. The reason is structural, not luck — pass-2 writes these pages,
#: so their length is governed by the compiler's own prompt contract (live max 129
#: words / 976 B). Fat now receives whole bodies, and the fill bounds the request.
#:
#: The query ceiling below is deliberately NOT removed with them: pass-1 metadata
#: is model-authored and genuinely unbounded, unlike a compiled body. It is filed
#: as a separate candidate, to be decided the same way — by measuring how often it
#: binds on real pass-1 output first.

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
#:
#: **THIN raised 13,000 -> 20,000 at v0.16 — a forced consequence of D-123-A, not
#: a free choice.** Thin's wire is a retained-slug list bounded by `M x
#: MAX_SLUG_LEN`, so M 100 -> 150 moves its exact maximum 12,314 -> 18,464 B,
#: straight through the old allowance. D8(iii)'s ratified rule is that the
#: allowance *derives* from the exact maximum, so it follows M rather than being
#: re-decided; 20,000 keeps roughly the relative headroom 13,000 gave 12,314
#: (8.3% vs 5.6%). `PROVIDER_MAX_TOKENS_THIN` becomes 36,000, still far under the
#: pool's smallest `max_output_tokens` (gemini-3.6-flash, 65,536) — asserted at
#: route resolution.
#:
#: The amendment did not anticipate this: D-123-A reasoned that M was no longer an
#: input to any guarantee, which is true of the INPUT budget and false of the
#: output wire. Recorded rather than absorbed silently.
VISIBLE_OUTPUT_ALLOWANCE_THIN = 20_000
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


#: Byte budget for the rendered system block + user wrapper (blueprint §7.0a).
#: Recorded as a constant rather than prose so the reserve is a checkable sum.
#: It was the template term of the M=100 static guarantee; with that guarantee
#: withdrawn (D-123-D) it is the fill's fixed overhead — the bytes already spent
#: before the first entity is offered a place in the pool.
#:
#: **Raised 3,072 → 4,096 at v0.15 (2026-08-02, Joseph).** The P2 obligation is
#: discharged — both templates are now measured against this by
#: `test_prompts_golden.py`. 3,072 was never a measured bound: it was the
#: "~3 kB system/template" line written into the guarantee before any prompt
#: existed, and the v2 prose left it 74 B of headroom, so the next reviewed
#: sentence would have broken a ratified figure.
#:
#: The reason to raise it rather than trim prose is **architectural capacity**
#: (codex): the golden pin already forces version + review discipline on content
#: changes, so the reserve does not need to do that job too. 4,096 matches
#: `QUERY_BLOCK_CEILING_BYTES`, so the two per-request reserves read as one
#: scheme.
SYSTEM_TEMPLATE_BUDGET_BYTES = 4_096

#: The pool's smallest effective context budget: gpt-5.4-mini's 400,000 window at
#: BUDGET_HEADROOM. It no longer carries a static guarantee (D-123-D) — the fill
#: bounds the request against each route's own budget at request time, which is
#: the stronger property. Kept as the figure sizing claims are stated against:
#: at 150 entities, live body density fills 5.3% of it.
SMALLEST_POOL_BUDGET_TOKENS = 320_000

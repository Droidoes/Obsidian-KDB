"""proposal_bridge — the proposal → canonical normalization boundary (#119, D-119).

Pure: the raw proposal is never mutated (raw evidence is telemetry's point).
Rules in order (blueprint §5): summary count → typed pure page-slug coercion →
summary identity stamping → response-local body-reference policy → canonical
self-check (shape + summary invariant + conservation).

The alias ledger is NOT an authority here — alias resolution stays exclusively
in canonicalize (R6 F3). No string similarity anywhere.
"""
from __future__ import annotations

import hashlib
import json
import re
from enum import StrEnum
from typing import Any, NamedTuple

from common.paths import collapse_slug
from compiler import validate_source_response
from compiler.summary_slug import SUMMARY_PREFIX, expected_summary_slug


class RejectClass(StrEnum):
    """Bridge semantic reject classes — ALL model-correctable (retriable).
    Codex R8 F3: STRUCTURAL_INSUFFICIENCY is not here — it is the
    proposal-STAGE failure class (schema gate, before the bridge), not a
    bridge reject. REWRITE_AMBIGUITY is removed — under response-local
    page-map rewriting, exact mappings are unique and collisions reject
    BEFORE rewriting, so no ambiguity can reach the rewrite stage (ledger
    ambiguity stays fail-closed in canonicalize)."""
    NO_SUMMARY = "no_summary"
    MULTIPLE_SUMMARIES = "multiple_summaries"
    SLUG_COLLISION = "slug_collision"
    UNCOERCIBLE_SLUG = "uncoercible_slug"


RETRIABLE: frozenset[RejectClass] = frozenset(RejectClass)


class CanonicalInvariantError(Exception):
    """Bridge/canonical self-check failure — a SYSTEM bug class. Never a model
    failure, never retried. Raised, not returned."""


class NormalizationDecision(NamedTuple):
    rule: str
    authority: str
    location: str
    raw_type: str
    raw_value: str | None
    raw_preview: str | None
    raw_sha256: str | None
    canonical_value: str | None


class BridgeSuccess(NamedTuple):
    canonical: dict
    decisions: list[NormalizationDecision]


class BridgeReject(NamedTuple):
    reject_class: RejectClass
    detail: str
    decisions: list[NormalizationDecision]

    @property
    def retriable(self) -> bool:
        return self.reject_class in RETRIABLE


BridgeResult = BridgeSuccess | BridgeReject


_RAW_CAP = 120
_JSON_TYPE_NAMES = {
    dict: "object", list: "array", str: "string",
    bool: "boolean", int: "number", float: "number", type(None): "null",
}


def _decision(rule: str, authority: str, location: str,
              raw: Any, canonical: Any) -> NormalizationDecision:
    """Bounded capture (Codex plan-review F7): JSON type names; strings >120
    chars and all non-strings degrade to preview + stable hash so the
    always-on decision list stays small."""
    raw_type = _JSON_TYPE_NAMES.get(type(raw), type(raw).__name__)
    if raw is None:
        raw_value, raw_preview, raw_sha = None, None, None
    elif isinstance(raw, str) and len(raw) <= _RAW_CAP:
        raw_value, raw_preview, raw_sha = raw, None, None
    else:
        text = raw if isinstance(raw, str) else json.dumps(
            raw, ensure_ascii=False, sort_keys=True)
        raw_value, raw_preview = None, text[:_RAW_CAP]
        raw_sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return NormalizationDecision(
        rule=rule, authority=authority, location=location,
        raw_type=raw_type, raw_value=raw_value,
        raw_preview=raw_preview, raw_sha256=raw_sha,
        canonical_value=canonical if isinstance(canonical, str) else None,
    )


# --- the single source of truth (Codex PR3 F1 + PR4 F1): the lossless typed plan ---
ABSENT = object()   # slug-slot sentinel: distinguishes "no slug key" from JSON null


class OpKind(StrEnum):
    SLUG_FORM_COERCION = "slug_form_coercion"
    SUMMARY_IDENTITY_RESOLUTION = "summary_identity_resolution"  # stray-drop + stamp as ONE location op
    BODY_REFERENCE_REWRITE = "body_reference_rewrite"


class NormalizationOp(NamedTuple):
    """ONE lossless, exactly-located normalization step. The bridge is
    PLAN-APPLY-VERIFY (Codex PR4 F1): rules CONSTRUCT the op list and never
    mutate; `_apply_normalization_plan` constructs the canonical object FROM
    the ops (the only mutation path, raising on spurious ops); and
    `_check_conservation` independently diffs raw vs canonical and verifies a
    BIJECTION — every difference consumes exactly one op, every op is
    consumed. `raw`/`canonical` are NEVER bounded (bounded telemetry is
    derived via `_decisions_from_ops`)."""
    kind: OpKind
    authority: str
    page_index: int
    field: str            # "slug" | "body"
    occurrence: int       # body: 0-based occurrence of the raw token in the code-aware token scan of that page's body
    raw: Any              # ABSENT sentinel when the slug key is absent
    canonical: Any


def _decisions_from_ops(ops: list[NormalizationOp]) -> list[NormalizationDecision]:
    """Bounded telemetry projection (aggregate-capped at the compile_one
    boundary via `_cap_decisions`). One resolution op derives an ignore
    decision (when a stray existed) + a stamp decision. Body-rewrite
    locations carry a PER-PAGE running index (`pages[i].body#n` = the n-th
    rewrite op on that page, in scan order) — not a per-token occurrence."""
    out: list[NormalizationDecision] = []
    occurrence: dict[int, int] = {}
    for op in ops:
        if op.kind is OpKind.BODY_REFERENCE_REWRITE:
            occurrence[op.page_index] = occurrence.get(op.page_index, 0) + 1
            out.append(_decision(
                rule="body_reference_rewrite", authority=op.authority,
                location=f"pages[{op.page_index}].body#{occurrence[op.page_index]}",
                raw=op.raw, canonical=op.canonical))
        elif op.kind is OpKind.SLUG_FORM_COERCION:
            out.append(_decision(
                rule="slug_form_coercion", authority=op.authority,
                location=f"pages[{op.page_index}].slug",
                raw=op.raw, canonical=op.canonical))
        else:  # SUMMARY_IDENTITY_RESOLUTION
            if op.raw is not ABSENT:
                out.append(_decision(
                    rule="summary_slug_ignored", authority=op.authority,
                    location=f"pages[{op.page_index}].slug",
                    raw=op.raw, canonical=None))
            out.append(_decision(
                rule="summary_identity_stamp", authority=op.authority,
                location=f"pages[{op.page_index}].slug",
                raw=None, canonical=op.canonical))
    return out


_DECISIONS_CAP = 50


def _cap_decisions(decisions: list[NormalizationDecision]) -> tuple[list[dict], int, str | None]:
    """Aggregate telemetry bound (Codex PR4 F6): ≤50 located samples + total
    count + overflow digest of the truncated tail — the always-on persisted
    list stays small no matter how many body-link occurrences fire."""
    dicts = [d._asdict() for d in decisions]
    if len(dicts) <= _DECISIONS_CAP:
        return dicts, len(dicts), None
    tail = json.dumps(dicts[_DECISIONS_CAP:], ensure_ascii=False, sort_keys=True)
    return dicts[:_DECISIONS_CAP], len(dicts), hashlib.sha256(tail.encode("utf-8")).hexdigest()


# --- token machinery (moved from repair.py; parity semantics preserved) ---
_COERCE_WIKILINK_RE = re.compile(r"(?<!\\)\[\[([^\[\]|#]+?)(#[^\[\]|]*)?(\|[^\[\]]*)?\]\]")
_FENCED_CODE_RE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`[^`\n]*`")


def _outside_code_spans(text: str) -> list[tuple[bool, str]]:
    parts: list[tuple[bool, str]] = []
    fpos = 0
    for fm in _FENCED_CODE_RE.finditer(text):
        seg = text[fpos:fm.start()]
        ipos = 0
        for im in _INLINE_CODE_RE.finditer(seg):
            parts.append((False, seg[ipos:im.start()]))
            parts.append((True, im.group(0)))
            ipos = im.end()
        parts.append((False, seg[ipos:]))
        parts.append((True, fm.group(0)))
        fpos = fm.end()
    tail = text[fpos:]
    ipos = 0
    for im in _INLINE_CODE_RE.finditer(tail):
        parts.append((False, tail[ipos:im.start()]))
        parts.append((True, im.group(0)))
        ipos = im.end()
    parts.append((False, tail[ipos:]))
    return parts


def _iter_mapped_tokens(body: str, rename: dict[str, str]) -> list[tuple[str, str]]:
    """Each code-aware wikilink match whose target is in `rename`, in scan
    order (duplicates yielded per occurrence)."""
    out: list[tuple[str, str]] = []
    for is_code, seg in _outside_code_spans(body):
        if is_code:
            continue
        for m in _COERCE_WIKILINK_RE.finditer(seg):
            tgt = m.group(1)
            if tgt in rename:
                out.append((tgt, rename[tgt]))
    return out


def normalize_proposal(parsed: dict, *, source_id: str) -> BridgeResult:
    ops: list[NormalizationOp] = []
    pages = parsed.get("pages") or []

    # --- rule 1: summary count (role authority) ---
    summary_idx = [i for i, p in enumerate(pages)
                   if isinstance(p, dict) and p.get("page_type") == "summary"]
    if not summary_idx:
        return BridgeReject(RejectClass.NO_SUMMARY,
                            "no page with page_type='summary'",
                            _decisions_from_ops(ops))
    if len(summary_idx) > 1:
        return BridgeReject(RejectClass.MULTIPLE_SUMMARIES,
                            f"{len(summary_idx)} pages with page_type='summary'",
                            _decisions_from_ops(ops))

    # --- rule 2: concept/article page-slug coercion (PLAN construction — no mutation) ---
    for i, p in enumerate(pages):
        if p["page_type"] == "summary":
            continue
        raw = p["slug"]
        coerced = collapse_slug(raw)
        if coerced is None:
            return BridgeReject(
                RejectClass.UNCOERCIBLE_SLUG,
                f"pages[{i}].slug {raw!r} cannot be coerced to a valid slug",
                _decisions_from_ops(ops))
        if coerced != raw:
            ops.append(NormalizationOp(OpKind.SLUG_FORM_COERCION,
                                       "form-rule", i, "slug", 0, raw, coerced))

    # collision detection on PLANNED final slugs (post-coercion)
    planned: dict[str, int] = {}
    for i, p in enumerate(pages):
        if p["page_type"] == "summary":
            continue
        final = next((op.canonical for op in ops
                      if op.kind is OpKind.SLUG_FORM_COERCION
                      and op.page_index == i), p["slug"])
        # D5 (#120 spec v1.4): the summary- namespace is system-owned (Python
        # stamps summary identity); a model-owned summary-* slug can collide
        # with a FUTURE source's derived identity at graph level. Checked on
        # the PLANNED (post-coercion) slug — SUMMARY--Foo must not slip.
        if final.startswith(SUMMARY_PREFIX):
            return BridgeReject(
                RejectClass.SLUG_COLLISION,
                f"pages[{i}].slug {final!r} collides with the system-owned "
                f"{SUMMARY_PREFIX!r} namespace (reserved for Python-stamped "
                f"summary pages)",
                _decisions_from_ops(ops))
        if final in planned:
            return BridgeReject(
                RejectClass.SLUG_COLLISION,
                f"slug {final!r} shared by pages[{planned[final]}] and pages[{i}]",
                _decisions_from_ops(ops))
        planned[final] = i

    # --- rule 3: summary identity resolution (role + provenance; always safe) ---
    si = summary_idx[0]
    expected = expected_summary_slug(source_id)
    if expected in planned:
        return BridgeReject(
            RejectClass.SLUG_COLLISION,
            f"derived summary slug {expected!r} collides with pages[{planned[expected]}]",
            _decisions_from_ops(ops))
    stray = pages[si].get("slug", ABSENT)
    ops.append(NormalizationOp(OpKind.SUMMARY_IDENTITY_RESOLUTION,
                               "role+source_id", si, "slug", 0, stray, expected))

    # --- rule 4: body-reference policy (response-local ONLY; ledger untouched) ---
    # rename derived from the coercion ops; every mapped token OCCURRENCE gets
    # its own exactly-located op (duplicate occurrences never collapse — PR4 F1)
    rename = {op.raw: op.canonical for op in ops
              if op.kind is OpKind.SLUG_FORM_COERCION}
    if rename:
        for i, p in enumerate(pages):
            body = p.get("body")
            if not isinstance(body, str):
                continue
            for raw_tok, canon_tok in _iter_mapped_tokens(body, rename):
                per_token_n = sum(
                    1 for op in ops
                    if op.kind is OpKind.BODY_REFERENCE_REWRITE
                    and op.page_index == i and op.raw == raw_tok)
                ops.append(NormalizationOp(
                    OpKind.BODY_REFERENCE_REWRITE, "response-local",
                    i, "body", per_token_n, raw_tok, canon_tok))

    # --- rule 5: plan VALIDATED → canonical = plan APPLIED → shape + identity + bijection ---
    _validate_plan(ops, summary_index=si, page_count=len(pages))
    canonical = _apply_normalization_plan(parsed, ops)
    errors = validate_source_response.validate(canonical)
    if errors:
        raise CanonicalInvariantError(f"canonical shape: {errors[0]}")
    summaries = [p for p in canonical["pages"] if p["page_type"] == "summary"]
    if len(summaries) != 1 or summaries[0]["slug"] != expected:
        raise CanonicalInvariantError(
            f"summary invariant: expected exactly one summary with slug "
            f"{expected!r}, found {[p.get('slug') for p in summaries]}")
    _check_conservation(parsed, canonical, ops)
    return BridgeSuccess(canonical=canonical,
                         decisions=_decisions_from_ops(ops))


def _apply_normalization_plan(parsed: dict, ops: list[NormalizationOp]) -> dict:
    """Construct the canonical object FROM the ops — the ONLY mutation path.
    Slug ops apply with a raw-match check; ALL of a page's body ops apply in
    ONE scan against the ORIGINAL body (Codex PR5 F1 — sequential
    nth-occurrence rewrites on a mutating body renumber raw occurrences and
    break duplicates). Raises CanonicalInvariantError on spurious ops,
    missing occurrences, or unknown fields."""
    canonical: dict[str, Any] = {"pages": [dict(p) for p in parsed["pages"]]}
    if "compilation_notes" in parsed:
        canonical["compilation_notes"] = parsed["compilation_notes"]
    body_ops: dict[int, list[NormalizationOp]] = {}
    for op in ops:
        page = canonical["pages"][op.page_index]
        if op.field == "slug":
            current = page.get("slug", ABSENT)
            if not _json_equal(current, op.raw):
                raise CanonicalInvariantError(
                    f"spurious op at pages[{op.page_index}].slug: "
                    f"op raw {op.raw!r} != current {current!r}")
            page["slug"] = op.canonical
        elif op.field == "body":
            body_ops.setdefault(op.page_index, []).append(op)
        else:
            raise CanonicalInvariantError(f"unknown op field: {op.field!r}")
    for i, page_ops in body_ops.items():
        body = canonical["pages"][i].get("body")
        if not isinstance(body, str):
            raise CanonicalInvariantError(
                f"body op on pages[{i}] without a string body")
        canonical["pages"][i]["body"] = _apply_body_ops(body, page_ops)
    return canonical


def _apply_body_ops(body: str, page_ops: list[NormalizationOp]) -> str:
    """Apply ALL of one page's body ops in a single code-aware scan against
    the ORIGINAL body. Each raw token's n-th occurrence is rewritten per the
    op with that occurrence; an op whose occurrence never appears raises."""
    by_token: dict[str, dict[int, str]] = {}
    for op in page_ops:
        by_token.setdefault(op.raw, {})[op.occurrence] = op.canonical
    counts: dict[str, int] = {}

    def _rw(m: re.Match) -> str:
        tgt = m.group(1)
        if tgt in by_token:
            n = counts.get(tgt, 0)
            counts[tgt] = n + 1
            if n in by_token[tgt]:
                return f"[[{by_token[tgt][n]}{m.group(2) or ''}{m.group(3) or ''}]]"
        return m.group(0)

    out = "".join(
        seg if is_code else _COERCE_WIKILINK_RE.sub(_rw, seg)
        for is_code, seg in _outside_code_spans(body))
    for tok, occs in by_token.items():
        if counts.get(tok, 0) <= max(occs):
            raise CanonicalInvariantError(
                f"occurrence {max(occs)} of {tok!r} not found in body")
    return out


def _prose_frame(body: str) -> str:
    """The body with every wikilink token blanked — prose + code spans must
    match byte-for-byte between raw and canonical."""
    return "".join(
        seg if is_code else _COERCE_WIKILINK_RE.sub("\x00", seg)
        for is_code, seg in _outside_code_spans(body))


def _token_scan(body: str) -> list[tuple[str, tuple[str, str]]]:
    """Code-aware wikilink scan: (target, (anchor, display)) in document order."""
    out: list[tuple[str, tuple[str, str]]] = []
    for is_code, seg in _outside_code_spans(body):
        if is_code:
            continue
        for m in _COERCE_WIKILINK_RE.finditer(seg):
            out.append((m.group(1), (m.group(2) or "", m.group(3) or "")))
    return out


def _body_diffs(page_index: int, raw_body: str, canon_body: str) -> list[tuple]:
    """Token-level body diff: prose frames must be byte-identical; token
    frames (anchor/display) position-aligned; differences emitted as
    (page, "body", occurrence-of-that-token, raw_tok, canon_tok)."""
    if _prose_frame(raw_body) != _prose_frame(canon_body):
        raise CanonicalInvariantError(
            f"pages[{page_index}].body prose/code changed")
    raw_tokens, canon_tokens = _token_scan(raw_body), _token_scan(canon_body)
    if len(raw_tokens) != len(canon_tokens):
        raise CanonicalInvariantError(
            f"pages[{page_index}].body link count changed")
    diffs: list[tuple] = []
    seen: dict[str, int] = {}
    for (rt, rf), (ct, cf) in zip(raw_tokens, canon_tokens):
        if rf != cf:
            raise CanonicalInvariantError(
                f"pages[{page_index}].body anchor/display changed")
        n = seen.get(rt, 0)
        if rt != ct:
            diffs.append((page_index, "body", n, rt, ct))
        seen[rt] = n + 1
    return diffs


_KIND_MATRIX = {
    OpKind.SLUG_FORM_COERCION: ("slug", "form-rule"),
    OpKind.SUMMARY_IDENTITY_RESOLUTION: ("slug", "role+source_id"),
    OpKind.BODY_REFERENCE_REWRITE: ("body", "response-local"),
}


def _validate_plan(ops: list[NormalizationOp], *, summary_index: int,
                   page_count: int) -> None:
    """Codex PR5 F2 — the plan's structural contract, validated independently
    of application: kind/field/authority matrix, index/occurrence ranges,
    no-op discipline (only summary identity resolution may be a no-op), and
    EXACTLY ONE summary identity resolution at the summary page — even when
    it is a no-op (an already-canonical stray), so the required resolution
    telemetry can never silently disappear."""
    for op in ops:
        expected = _KIND_MATRIX.get(op.kind)
        if expected is None or (op.field, op.authority) != expected:
            raise CanonicalInvariantError(
                f"invalid kind/field/authority: {op!r}")
        if not (0 <= op.page_index < page_count):
            raise CanonicalInvariantError(f"op page_index out of range: {op!r}")
        if op.field == "body" and op.occurrence < 0:
            raise CanonicalInvariantError(f"invalid occurrence: {op!r}")
        if op.field == "slug" and op.occurrence != 0:
            raise CanonicalInvariantError(
                f"slug op with nonzero occurrence: {op!r}")
        if op.kind is not OpKind.SUMMARY_IDENTITY_RESOLUTION \
                and _json_equal(op.raw, op.canonical):
            raise CanonicalInvariantError(
                f"no-op op outside summary resolution: {op!r}")
    resolutions = [op for op in ops
                   if op.kind is OpKind.SUMMARY_IDENTITY_RESOLUTION]
    if len(resolutions) != 1 or resolutions[0].page_index != summary_index:
        raise CanonicalInvariantError(
            f"exactly one SUMMARY_IDENTITY_RESOLUTION at pages[{summary_index}] "
            f"required, got {resolutions!r}")


def _freeze(value: Any) -> Any:
    """Type-faithful, hash-stable form of a JSON value (+ ABSENT sentinel and
    internal tuples) for multiset keys and raw-value comparisons. Every JSON
    type gets a distinct tag — frozen equality == JSON equality, exactly
    (Codex R1 F1: untagged freezing collided dicts with nested arrays and
    booleans with numbers, and Python's True == 1 let a fault-injected op
    slip both apply and conservation). JSON object key order normalized by
    sorting; keys are strings post-parse so the sort is total."""
    if value is ABSENT:
        return ("absent",)
    if isinstance(value, bool):          # before int — bool subclasses int
        return ("boolean", value)
    if isinstance(value, dict):
        return ("object", tuple(sorted((k, _freeze(v)) for k, v in value.items())))
    if isinstance(value, list):
        return ("array", tuple(_freeze(v) for v in value))
    if isinstance(value, tuple):         # internal containers only — JSON has none
        return ("tuple", tuple(_freeze(v) for v in value))
    if isinstance(value, str):
        return ("string", value)
    if value is None:
        return ("null",)
    if isinstance(value, (int, float)):
        return ("number", value)
    raise CanonicalInvariantError(
        f"unfreezable value type: {type(value).__name__}")


def _json_equal(a: Any, b: Any) -> bool:
    """Type-faithful JSON equality (True != 1, {"a":1} != [["a",1]])."""
    return _freeze(a) == _freeze(b)


def _multiset(items: list[tuple]) -> dict[tuple, int]:
    out: dict[tuple, int] = {}
    for it in items:
        key = _freeze(it)
        out[key] = out.get(key, 0) + 1
    return out


def _check_conservation(raw: dict, canonical: dict,
                        ops: list[NormalizationOp]) -> None:
    """Codex PR4 F1 — BIJECTION: independently diff raw vs canonical; every
    difference must consume exactly one op and every op must be consumed.
    Page count/order, page_type, title, prose frames, compilation_notes
    byte-for-byte. No-op ops (raw == canonical — e.g. an already-canonical
    stray) are allowed and still telemetered; any other unmatched op or
    difference is a system bug."""
    rp, cp = raw.get("pages") or [], canonical["pages"]
    if len(rp) != len(cp):
        raise CanonicalInvariantError(
            f"page count changed: {len(rp)} -> {len(cp)}")

    diffs: list[tuple] = []
    for i, (r, c) in enumerate(zip(rp, cp)):
        for f in ("page_type", "title"):
            if r.get(f) != c.get(f):
                raise CanonicalInvariantError(f"pages[{i}].{f} changed")
        rs, cs = r.get("slug", ABSENT), c.get("slug", ABSENT)
        if not _json_equal(rs, cs):
            diffs.append((i, "slug", 0, rs, cs))
        rb, cb = r.get("body"), c.get("body")
        if rb != cb:
            if not (isinstance(rb, str) and isinstance(cb, str)):
                raise CanonicalInvariantError(f"pages[{i}].body type changed")
            diffs.extend(_body_diffs(i, rb, cb))
    if raw.get("compilation_notes") != canonical.get("compilation_notes"):
        raise CanonicalInvariantError("compilation_notes changed")

    op_keys = [(op.page_index, op.field, op.occurrence, op.raw, op.canonical)
               for op in ops if not _json_equal(op.raw, op.canonical)]
    if _multiset(diffs) != _multiset(op_keys):
        raise CanonicalInvariantError(
            f"diff/op mismatch: diffs={diffs!r} ops={op_keys!r}")

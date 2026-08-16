"""The proposal → canonical bridge (#119, D-119)."""
import pytest

from kdb_graph_compiler.proposal_bridge import (
    BridgeReject, BridgeSuccess, CanonicalInvariantError, RejectClass,
    normalize_proposal,
)


def _summary(**kw):
    p = {"page_type": "summary", "title": "T", "body": "B."}
    p.update(kw)
    return p


def test_no_summary_rejected():
    r = normalize_proposal({"pages": [{"page_type": "concept", "slug": "a",
                                      "title": "T", "body": "B."}]},
                           source_id="KDB/raw/x.md")
    assert isinstance(r, BridgeReject) and r.reject_class == RejectClass.NO_SUMMARY
    assert r.retriable


def test_multiple_summaries_rejected():
    r = normalize_proposal({"pages": [_summary(), _summary()]},
                           source_id="KDB/raw/x.md")
    assert (isinstance(r, BridgeReject)
            and r.reject_class == RejectClass.MULTIPLE_SUMMARIES)


def test_summary_stamped_and_raw_preserved():
    proposal = {"pages": [_summary()]}
    r = normalize_proposal(proposal, source_id="KDB/raw/x.md")
    assert isinstance(r, BridgeSuccess)
    assert r.canonical["pages"][0]["slug"] == "summary-x"
    assert "slug" not in proposal["pages"][0]  # purity: raw untouched
    assert any(d.rule == "summary_identity_stamp" for d in r.decisions)


def test_page_slug_coerced_and_body_token_rewritten():
    r = normalize_proposal({"pages": [
        _summary(body="See [[Foo--Bar#Sec|the alias]] and [[Foo Bar]]."),
        {"page_type": "concept", "slug": "Foo--Bar", "title": "FB", "body": "FB."},
    ]}, source_id="KDB/raw/x.md")
    assert isinstance(r, BridgeSuccess)
    assert r.canonical["pages"][1]["slug"] == "foo-bar"
    assert "[[foo-bar#Sec|the alias]]" in r.canonical["pages"][0]["body"]
    assert "[[Foo Bar]]" in r.canonical["pages"][0]["body"]  # uncoercible TOKEN preserved
    assert any(d.rule == "slug_form_coercion" for d in r.decisions)
    assert any(d.rule == "body_reference_rewrite" for d in r.decisions)


def test_body_only_tokens_preserved():
    r = normalize_proposal({"pages": [
        _summary(body="Ticker [[AAPL]] and [[Foo--Bar]] and `[[Code--Span]]`."),
        {"page_type": "concept", "slug": "real-page", "title": "RP", "body": "RP."},
    ]}, source_id="KDB/raw/x.md")
    assert isinstance(r, BridgeSuccess)
    body = r.canonical["pages"][0]["body"]
    assert "[[AAPL]]" in body and "[[Foo--Bar]]" in body and "`[[Code--Span]]`" in body
    assert not any(d.rule == "body_reference_rewrite" for d in r.decisions)


def test_uncoercible_page_slug_rejected():
    r = normalize_proposal({"pages": [
        _summary(), {"page_type": "concept", "slug": "Foo Bar", "title": "T", "body": "B."},
    ]}, source_id="KDB/raw/x.md")
    assert (isinstance(r, BridgeReject)
            and r.reject_class == RejectClass.UNCOERCIBLE_SLUG)


def test_collapse_collision_rejected():
    r = normalize_proposal({"pages": [
        _summary(),
        {"page_type": "concept", "slug": "Foo--Bar", "title": "A", "body": "B."},
        {"page_type": "concept", "slug": "foo-bar", "title": "C", "body": "B."},
    ]}, source_id="KDB/raw/x.md")
    assert (isinstance(r, BridgeReject)
            and r.reject_class == RejectClass.SLUG_COLLISION)


def test_duplicate_page_slugs_rejected():
    r = normalize_proposal({"pages": [
        _summary(),
        {"page_type": "concept", "slug": "dup", "title": "A", "body": "B."},
        {"page_type": "article", "slug": "dup", "title": "C", "body": "B."},
    ]}, source_id="KDB/raw/x.md")
    assert (isinstance(r, BridgeReject)
            and r.reject_class == RejectClass.SLUG_COLLISION)


def test_stray_summary_slug_dropped_with_telemetry():
    r = normalize_proposal({"pages": [
        _summary(slug="summary-x-deviant", body="B.")]}, source_id="KDB/raw/x.md")
    assert isinstance(r, BridgeSuccess)
    assert r.canonical["pages"][0]["slug"] == "summary-x"
    ignored = [d for d in r.decisions if d.rule == "summary_slug_ignored"]
    assert ignored and ignored[0].raw_value == "summary-x-deviant"


def test_stray_nonstring_summary_slug_bounded_capture():
    r = normalize_proposal({"pages": [
        _summary(slug={"unexpected": "object"})]}, source_id="KDB/raw/x.md")
    assert isinstance(r, BridgeSuccess)
    ignored = [d for d in r.decisions if d.rule == "summary_slug_ignored"][0]
    assert ignored.raw_type == "object"
    assert ignored.raw_value is None
    assert ignored.raw_preview is not None and len(ignored.raw_preview) <= 120
    assert ignored.raw_sha256 is not None


def test_stray_bool_summary_slug_succeeds():
    """D-119 type matrix: a bool stray is tolerated like any other JSON type."""
    r = normalize_proposal({"pages": [
        _summary(slug=True)]}, source_id="KDB/raw/x.md")
    assert isinstance(r, BridgeSuccess)
    assert r.canonical["pages"][0]["slug"] == "summary-x"
    ignored = [d for d in r.decisions if d.rule == "summary_slug_ignored"][0]
    assert ignored.raw_type == "boolean"
    assert ignored.raw_value is None and ignored.raw_preview == "true"


def test_derived_slug_collision_rejected():
    r = normalize_proposal({"pages": [
        _summary(),
        {"page_type": "concept", "slug": "summary-x", "title": "A", "body": "B."},
    ]}, source_id="KDB/raw/x.md")
    assert (isinstance(r, BridgeReject)
            and r.reject_class == RejectClass.SLUG_COLLISION)


def test_summary_prefix_concept_rejected():
    """D5 (#120): the summary- namespace is system-owned (post-coercion)."""
    r = normalize_proposal({"pages": [
        _summary(),
        {"page_type": "concept", "slug": "summary-foo", "title": "A", "body": "B."},
    ]}, source_id="KDB/raw/x.md")
    assert (isinstance(r, BridgeReject)
            and r.reject_class == RejectClass.SLUG_COLLISION)
    assert r.retriable


def test_summary_prefix_article_rejected():
    r = normalize_proposal({"pages": [
        _summary(),
        {"page_type": "article", "slug": "summary-foo", "title": "A", "body": "B."},
    ]}, source_id="KDB/raw/x.md")
    assert (isinstance(r, BridgeReject)
            and r.reject_class == RejectClass.SLUG_COLLISION)


def test_summary_prefix_rejected_post_coercion():
    """D5 post-coercion pin: SUMMARY--Foo coerces to summary-foo — must reject."""
    r = normalize_proposal({"pages": [
        _summary(),
        {"page_type": "concept", "slug": "SUMMARY--Foo", "title": "A", "body": "B."},
    ]}, source_id="KDB/raw/x.md")
    assert (isinstance(r, BridgeReject)
            and r.reject_class == RejectClass.SLUG_COLLISION)


def test_summary_prefix_stray_on_summary_page_still_tolerated():
    """D-119 unaffected: a summary- stray ON the summary page is dropped+stamped."""
    r = normalize_proposal({"pages": [
        _summary(slug="summary-foo")]}, source_id="KDB/raw/x.md")
    assert isinstance(r, BridgeSuccess)
    assert r.canonical["pages"][0]["slug"] == "summary-x"


def test_alias_resolvable_token_preserved_for_canonicalize():
    r = normalize_proposal({"pages": [
        _summary(body="Alias [[apple-inc]] noted."),
        {"page_type": "concept", "slug": "real-page", "title": "RP", "body": "RP."},
    ]}, source_id="KDB/raw/x.md")
    assert isinstance(r, BridgeSuccess)
    assert "[[apple-inc]]" in r.canonical["pages"][0]["body"]


def test_conservation_pages_notes_prose_preserved():
    proposal = {
        "pages": [
            _summary(body="See [[Foo--Bar]]."),
            {"page_type": "concept", "slug": "Foo--Bar", "title": "FB", "body": "FB."},
        ],
        "compilation_notes": ["thin source"],
    }
    r = normalize_proposal(proposal, source_id="KDB/raw/x.md")
    assert isinstance(r, BridgeSuccess)
    assert r.canonical["compilation_notes"] == ["thin source"]
    assert [p["page_type"] for p in r.canonical["pages"]] == ["summary", "concept"]
    assert [p["title"] for p in r.canonical["pages"]] == ["T", "FB"]
    assert r.canonical["pages"][1]["body"] == "FB."


def test_success_for_full_proposal():
    r = normalize_proposal({"pages": [
        _summary(body="See [[foo--bar]]."),
        {"page_type": "concept", "slug": "foo--bar", "title": "FB", "body": "FB."},
    ]}, source_id="KDB/raw/x.md")
    assert isinstance(r, BridgeSuccess)
    assert r.canonical["pages"][0]["slug"] == "summary-x"
    assert r.canonical["pages"][1]["slug"] == "foo-bar"
    assert "[[foo-bar]]" in r.canonical["pages"][0]["body"]


# --- conservation negatives (R7 F5 + Codex PR4 F1 fault injection) ---

from kdb_graph_compiler.proposal_bridge import (
    ABSENT, CanonicalInvariantError, NormalizationOp, OpKind,
    _apply_normalization_plan, _check_conservation,
)


def _base_proposal():
    return {"pages": [
        {"page_type": "summary", "title": "T",
         "body": "See [[foo--bar]] and [[foo--bar]] again."},
        {"page_type": "concept", "slug": "foo--bar", "title": "FB", "body": "FB."},
    ], "compilation_notes": ["note one"]}


def _good_canonical():
    return {"pages": [
        {"page_type": "summary", "slug": "summary-x", "title": "T",
         "body": "See [[foo-bar]] and [[foo-bar]] again."},
        {"page_type": "concept", "slug": "foo-bar", "title": "FB", "body": "FB."},
    ], "compilation_notes": ["note one"]}


def _ops():
    return [
        NormalizationOp(OpKind.SLUG_FORM_COERCION, "form-rule", 1, "slug", 0,
                        "foo--bar", "foo-bar"),
        NormalizationOp(OpKind.SUMMARY_IDENTITY_RESOLUTION, "role+source_id",
                        0, "slug", 0, ABSENT, "summary-x"),
        NormalizationOp(OpKind.BODY_REFERENCE_REWRITE, "response-local", 0,
                        "body", 0, "foo--bar", "foo-bar"),
        NormalizationOp(OpKind.BODY_REFERENCE_REWRITE, "response-local", 0,
                        "body", 1, "foo--bar", "foo-bar"),
    ]


def test_conservation_clean_diff_passes():
    _check_conservation(_base_proposal(), _good_canonical(), _ops())


def test_conservation_duplicate_occurrences_each_need_their_op():
    """One op can never 'explain' two changed occurrences (PR4 F1)."""
    with pytest.raises(CanonicalInvariantError):
        _check_conservation(_base_proposal(), _good_canonical(), _ops()[:3])


def test_conservation_detects_dropped_page():
    bad = {"pages": _good_canonical()["pages"][:1],
           "compilation_notes": ["note one"]}
    with pytest.raises(CanonicalInvariantError):
        _check_conservation(_base_proposal(), bad, _ops())


def test_conservation_detects_notes_loss():
    bad = _good_canonical()
    bad["compilation_notes"] = []
    with pytest.raises(CanonicalInvariantError):
        _check_conservation(_base_proposal(), bad, _ops())


def test_conservation_detects_title_mutation():
    bad = _good_canonical()
    bad["pages"][1]["title"] = "changed"
    with pytest.raises(CanonicalInvariantError):
        _check_conservation(_base_proposal(), bad, _ops())


def test_conservation_detects_prose_edit_beyond_tokens():
    bad = _good_canonical()
    bad["pages"][0]["body"] = "Completely rewritten prose."
    with pytest.raises(CanonicalInvariantError):
        _check_conservation(_base_proposal(), bad, _ops())


def test_conservation_requires_resolution_op_for_summary_change():
    """PR3 F1: a summary edit with no recorded resolution op is a violation."""
    bad_ops = [op for op in _ops()
               if op.kind is not OpKind.SUMMARY_IDENTITY_RESOLUTION]
    with pytest.raises(CanonicalInvariantError):
        _check_conservation(_base_proposal(), _good_canonical(), bad_ops)


def test_conservation_explicit_null_stray():
    raw = {"pages": [{"page_type": "summary", "slug": None, "title": "T", "body": "B."}]}
    canon = {"pages": [{"page_type": "summary", "slug": "summary-x", "title": "T", "body": "B."}]}
    ops = [NormalizationOp(OpKind.SUMMARY_IDENTITY_RESOLUTION,
                           "role+source_id", 0, "slug", 0, None, "summary-x")]
    _check_conservation(raw, canon, ops)


def test_conservation_already_canonical_stray_is_allowed_noop():
    """A stray already equal to the derived slug: no-op op, allowed + telemetered."""
    raw = {"pages": [{"page_type": "summary", "slug": "summary-x", "title": "T", "body": "B."}]}
    canon = {"pages": [{"page_type": "summary", "slug": "summary-x", "title": "T", "body": "B."}]}
    ops = [NormalizationOp(OpKind.SUMMARY_IDENTITY_RESOLUTION,
                           "role+source_id", 0, "slug", 0, "summary-x", "summary-x")]
    _check_conservation(raw, canon, ops)


def test_conservation_rejects_unused_op():
    """Every op must be consumed by a real difference."""
    bad_ops = _ops() + [NormalizationOp(
        OpKind.SLUG_FORM_COERCION, "form-rule", 1, "slug", 0, "ghost", "ghost-x")]
    with pytest.raises(CanonicalInvariantError):
        _check_conservation(_base_proposal(), _good_canonical(), bad_ops)


def test_apply_rejects_spurious_op():
    """An op whose raw doesn't match the document at its location raises."""
    with pytest.raises(CanonicalInvariantError):
        _apply_normalization_plan(_base_proposal(), [
            NormalizationOp(OpKind.SLUG_FORM_COERCION, "form-rule", 1,
                            "slug", 0, "wrong-raw", "foo-bar")])


# --- end-to-end duplicate mapped tokens (Codex PR5 F1) ---

def test_normalize_proposal_duplicate_mapped_tokens_end_to_end():
    r = normalize_proposal({"pages": [
        _summary(body="See [[foo--bar]] and [[foo--bar]] again."),
        {"page_type": "concept", "slug": "foo--bar", "title": "FB", "body": "FB."},
    ]}, source_id="KDB/raw/x.md")
    assert isinstance(r, BridgeSuccess)
    assert r.canonical["pages"][0]["body"] == "See [[foo-bar]] and [[foo-bar]] again."
    rewrites = [d for d in r.decisions if d.rule == "body_reference_rewrite"]
    assert len(rewrites) == 2


# --- plan structural validation negatives (Codex PR5 F2) ---

from kdb_graph_compiler.proposal_bridge import _validate_plan


def _resolution_op(raw, canon):
    return NormalizationOp(OpKind.SUMMARY_IDENTITY_RESOLUTION,
                           "role+source_id", 0, "slug", 0, raw, canon)


def test_validate_plan_requires_resolution_even_when_noop():
    with pytest.raises(CanonicalInvariantError):
        _validate_plan([], summary_index=0, page_count=1)


def test_validate_plan_rejects_unused_noop_outside_resolution():
    with pytest.raises(CanonicalInvariantError):
        _validate_plan([
            _resolution_op(ABSENT, "summary-x"),
            NormalizationOp(OpKind.SLUG_FORM_COERCION, "form-rule", 1,
                            "slug", 0, "same", "same"),
        ], summary_index=0, page_count=2)


def test_validate_plan_rejects_wrong_kind_field_combo():
    with pytest.raises(CanonicalInvariantError):
        _validate_plan([
            _resolution_op(ABSENT, "summary-x"),
            NormalizationOp(OpKind.SLUG_FORM_COERCION, "form-rule", 1,
                            "body", 0, "a", "b"),
        ], summary_index=0, page_count=2)


def test_validate_plan_rejects_wrong_authority():
    with pytest.raises(CanonicalInvariantError):
        _validate_plan([
            _resolution_op(ABSENT, "summary-x"),
            NormalizationOp(OpKind.BODY_REFERENCE_REWRITE, "similarity", 0,
                            "body", 0, "a", "b"),
        ], summary_index=0, page_count=1)


def test_validate_plan_rejects_unknown_field():
    with pytest.raises(CanonicalInvariantError):
        _validate_plan([
            _resolution_op(ABSENT, "summary-x"),
            NormalizationOp(OpKind.SLUG_FORM_COERCION, "form-rule", 1,
                            "title", 0, "a", "b"),
        ], summary_index=0, page_count=2)


# --- type-faithful freezing + JSON equality (Codex R1 F1) ---

from kdb_graph_compiler.proposal_bridge import _freeze, _json_equal


def test_freeze_distinguishes_object_from_nested_array():
    assert _freeze({"a": 1}) != _freeze([["a", 1]])
    assert not _json_equal({"a": 1}, [["a", 1]])


def test_freeze_distinguishes_bool_from_number():
    assert _freeze(True) != _freeze(1)
    # distinct-keys proof: unequal values may share a hash, so prove the
    # frozen forms act as SEPARATE dict keys rather than asserting hash !=
    d = {_freeze(True): "bool"}
    d[_freeze(1)] = "num"
    assert len(d) == 2 and d[_freeze(True)] == "bool" and d[_freeze(1)] == "num"
    assert not _json_equal(True, 1)


def test_freeze_distinguishes_array_from_tuple():
    assert _freeze([1]) != _freeze((1,))
    assert not _json_equal([1], (1,))


def test_freeze_distinguishes_absent_null_and_absent_string():
    assert _freeze(ABSENT) != _freeze(None)
    assert _freeze(ABSENT) != _freeze("absent")
    assert _freeze(None) != _freeze("absent")


def test_freeze_json_equal_positive_cases():
    assert _json_equal({"b": [1, None], "a": True}, {"a": True, "b": [1, None]})
    assert _json_equal(ABSENT, ABSENT)
    assert _json_equal(None, None)
    assert not _json_equal(ABSENT, None)


def test_apply_rejects_type_loose_raw_match():
    """Codex R1 F1 fault injection: an op claiming raw=1 must NOT match a
    real summary stray of True (Python's True == 1 let it slip before)."""
    raw = {"pages": [{"page_type": "summary", "slug": True,
                      "title": "T", "body": "B."}]}
    op = NormalizationOp(OpKind.SUMMARY_IDENTITY_RESOLUTION,
                         "role+source_id", 0, "slug", 0, 1, "summary-x")
    with pytest.raises(CanonicalInvariantError):
        _apply_normalization_plan(raw, [op])


def test_conservation_rejects_type_loose_op():
    """Codex R1 F1 fault injection: the True-vs-1 op must also fail the
    conservation bijection, not just the apply raw-match."""
    raw = {"pages": [{"page_type": "summary", "slug": True,
                      "title": "T", "body": "B."}]}
    canon = {"pages": [{"page_type": "summary", "slug": "summary-x",
                        "title": "T", "body": "B."}]}
    op = NormalizationOp(OpKind.SUMMARY_IDENTITY_RESOLUTION,
                         "role+source_id", 0, "slug", 0, 1, "summary-x")
    with pytest.raises(CanonicalInvariantError):
        _check_conservation(raw, canon, [op])


def test_normalize_proposal_list_stray_slug_bounded_capture():
    """Legit path: a non-string (array) stray summary slug is still dropped
    and telemetered with bounded capture (raw_type 'array')."""
    r = normalize_proposal({"pages": [_summary(slug=[1, 2])]},
                           source_id="KDB/raw/x.md")
    assert isinstance(r, BridgeSuccess)
    assert r.canonical["pages"][0]["slug"] == "summary-x"
    ignored = [d for d in r.decisions if d.rule == "summary_slug_ignored"][0]
    assert ignored.raw_type == "array"
    assert ignored.raw_value is None
    assert ignored.raw_preview is not None and len(ignored.raw_preview) <= 120
    assert ignored.raw_sha256 is not None


# --- slug ops pin occurrence == 0 (Codex R1 F2) ---

def test_validate_plan_rejects_slug_coercion_nonzero_occurrence():
    with pytest.raises(CanonicalInvariantError):
        _validate_plan([
            _resolution_op(ABSENT, "summary-x"),
            NormalizationOp(OpKind.SLUG_FORM_COERCION, "form-rule", 1,
                            "slug", 1, "foo--bar", "foo-bar"),
        ], summary_index=0, page_count=2)


def test_validate_plan_rejects_resolution_nonzero_occurrence():
    with pytest.raises(CanonicalInvariantError):
        _validate_plan([
            NormalizationOp(OpKind.SUMMARY_IDENTITY_RESOLUTION,
                            "role+source_id", 0, "slug", 99,
                            "stray", "summary-x"),
        ], summary_index=0, page_count=1)


def test_validate_plan_rejects_noop_resolution_nonzero_occurrence():
    """The already-canonical no-op case (raw == canonical) is still a slug
    op — occurrence 99 must be rejected even though the plan is otherwise
    valid (exactly one resolution at the summary page, page_count=1)."""
    with pytest.raises(CanonicalInvariantError):
        _validate_plan([
            NormalizationOp(OpKind.SUMMARY_IDENTITY_RESOLUTION,
                            "role+source_id", 0, "slug", 99,
                            "summary-x", "summary-x"),
        ], summary_index=0, page_count=1)

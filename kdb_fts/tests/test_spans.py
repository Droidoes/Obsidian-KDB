"""spans: anchor validation, source slice, fallback ladder (pure)."""
from __future__ import annotations

from kdb_fts import spans


def test_validate_anchor_counts():
    p = "the quick brown fox jumps over the lazy dog"
    assert spans.validate_anchor(p, "quick brown") == 1
    assert spans.validate_anchor(p, "the") == 2
    assert spans.validate_anchor(p, "absent") == 0


def test_slice_span_valid_and_invalid():
    p = "the quick brown fox jumps over the lazy dog"
    assert spans.slice_span(p, "quick", "lazy") == "quick brown fox jumps over the lazy"
    assert spans.slice_span(p, "the", "lazy") is None       # head not unique
    assert spans.slice_span(p, "lazy", "quick") is None    # tail before head
    assert spans.slice_span(p, "quick", "absent") is None   # tail missing
    assert spans.slice_span(p, "", "lazy") is None          # empty anchor


def test_locate_quote_exact_first():
    p = "Buffett bought Coca-Cola in 1988."
    assert spans.locate_quote(p, "Coca-Cola in 1988") == "Coca-Cola in 1988"


def test_locate_quote_folded_and_fuzzy_still_substring():
    p = "Buffett bought Coca-Cola in 1988."
    got = spans.locate_quote(p, "CocaCola in 1988")  # hyphen removed → fuzzy path
    assert got is None or got in p
    assert spans.locate_quote(p, "totally absent phrase") is None


def test_property_result_is_none_or_substring():
    """Every ladder rung returns a verbatim source substring or None."""
    import random
    rng = random.Random(0)
    for _ in range(200):
        words = ["alpha", "beta", "gamma", "delta", "epsilon", "zeta"]
        n = rng.randint(5, 30)
        para = " ".join(rng.choice(words) for _ in range(n))
        a, b = sorted(rng.sample(range(len(para)), 2))
        quote = para[a:b]
        if rng.random() < 0.5:
            quote = quote.replace(" ", "", 1)  # perturb (may no longer be a substring)
        result = spans.locate_quote(para, quote)
        assert result is None or result in para

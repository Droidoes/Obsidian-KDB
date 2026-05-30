# kdb_compiler/tests/test_pass1_overrides.py
from kdb_compiler.ingestion.overrides import apply_overrides, build_override_block


# --- Task #95: single-producer override constructor ---

def test_build_override_block_default_is_null_block():
    block = build_override_block("signal")
    assert block == {
        "applied": None, "rule": None, "match": None,
        "llm_original": "signal", "reject_reason_cleared": None,
    }


def test_build_override_block_carries_all_fields():
    block = build_override_block(
        "noise", applied="signal", rule="force_signal",
        match="curated/**", reject_reason_cleared="diary-shaped",
    )
    assert block == {
        "applied": "signal", "rule": "force_signal", "match": "curated/**",
        "llm_original": "noise", "reject_reason_cleared": "diary-shaped",
    }


def test_apply_overrides_uses_the_constructor_shape():
    """The block apply_overrides emits is structurally identical to the
    constructor's output (one source of truth)."""
    env = {
        "kdb_signal": "signal", "domain": "ai-ml", "source_type": "post",
        "author": None, "summary": "x", "key_themes": [], "entity_search_keys": [],
        "confidence": 0.9, "uncertainty_reason": None, "reject_reason": None,
        "prompt_version": "1.0.0", "model": "x", "schema_version": 1,
        "override": build_override_block("signal"), "other_reason": None,
    }
    out = apply_overrides(env, source_path="essays/x.md",
                          force_signal=(), force_noise=())
    assert set(out["override"].keys()) == set(build_override_block("signal").keys())


def _envelope(kdb_signal="signal", reject_reason=None):
    return {
        "kdb_signal": kdb_signal,
        "domain": "ai-ml", "source_type": "post", "author": None,
        "summary": "x", "key_themes": [], "entity_search_keys": [],
        "confidence": 0.9, "uncertainty_reason": None,
        "reject_reason": reject_reason,
        "prompt_version": "1.0.0", "model": "x", "schema_version": 1,
        "override": {"applied": None, "rule": None, "match": None,
                     "llm_original": kdb_signal, "reject_reason_cleared": None},
        "other_reason": None,
    }


def test_no_match_emits_null_override_block():
    """Per D-89-3 §4.6 + Grok OQ-3: block always emitted; null when no override."""
    env = _envelope()
    out = apply_overrides(env, source_path="essays/buffett.md",
                          force_signal=(), force_noise=("Daily Notes/**",))
    assert out["kdb_signal"] == "signal"
    assert out["override"]["applied"] is None
    assert out["override"]["rule"] is None
    assert out["override"]["match"] is None
    assert out["override"]["llm_original"] == "signal"


def test_force_noise_match_overrides_to_noise():
    env = _envelope(kdb_signal="signal")
    out = apply_overrides(env, source_path="Daily Notes/2026-05-26.md",
                          force_signal=(), force_noise=("Daily Notes/**",))
    assert out["kdb_signal"] == "noise"
    assert out["override"]["applied"] == "noise"
    assert out["override"]["rule"] == "force_noise"
    assert out["override"]["match"] == "Daily Notes/**"
    assert out["override"]["llm_original"] == "signal"


def test_force_noise_signal_to_noise_populates_reject_reason():
    """Per §4.6 reject_reason survival rule."""
    env = _envelope(kdb_signal="signal", reject_reason=None)
    out = apply_overrides(env, source_path="Daily Notes/x.md",
                          force_signal=(), force_noise=("Daily Notes/**",))
    assert out["reject_reason"]
    assert "force_noise" in out["reject_reason"]


def test_force_signal_match_overrides_to_signal():
    env = _envelope(kdb_signal="noise", reject_reason="diary-shaped")
    out = apply_overrides(env, source_path="curated/essay.md",
                          force_signal=("curated/**",), force_noise=())
    assert out["kdb_signal"] == "signal"
    assert out["override"]["applied"] == "signal"
    assert out["override"]["rule"] == "force_signal"


def test_force_signal_noise_to_signal_clears_reject_reason():
    env = _envelope(kdb_signal="noise", reject_reason="diary-shaped")
    out = apply_overrides(env, source_path="curated/essay.md",
                          force_signal=("curated/**",), force_noise=())
    assert out["reject_reason"] is None
    assert out["override"]["reject_reason_cleared"] == "diary-shaped"


def test_blacklist_wins_ties():
    """Per D-89-3 §4.4: when both lists match, force_noise wins."""
    env = _envelope(kdb_signal="signal")
    out = apply_overrides(env, source_path="Daily Notes/x.md",
                          force_signal=("**/*.md",), force_noise=("Daily Notes/**",))
    assert out["kdb_signal"] == "noise"
    assert out["override"]["rule"] == "force_noise"

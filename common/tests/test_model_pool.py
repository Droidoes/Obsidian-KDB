import pytest
from common.model_pool import (
    ModelSpec,
    resolve_models_json,
    PoolError,
    UnknownModelError,
    DroppedModelError,
    load_pool,
)


def test_dropped_id_raises_dropped_model_error():
    # The dropped-guard must be distinguishable from "unknown id".
    with pytest.raises(DroppedModelError):
        resolve_models_json("qwen-flash-us")  # in pool, marked dropped
    assert issubclass(DroppedModelError, PoolError)


def test_unknown_id_raises_unknown_model_error():
    with pytest.raises(UnknownModelError):
        resolve_models_json("no-such-model")
    assert issubclass(UnknownModelError, PoolError)

def test_resolve_active_entry_returns_modelspec():
    spec = resolve_models_json("deepseek-v4-flash")   # active, direct route, the default
    assert isinstance(spec, ModelSpec)
    assert spec.provider == "deepseek"
    assert spec.model == "deepseek-v4-flash"
    assert spec.ctx_window == 1000000
    # Generated from the `thinking: disabled` field via the per-provider table.
    assert spec.extra_body == {"thinking": {"type": "disabled"}}
    assert spec.price_in == 0.14 and spec.price_out == 0.28

def test_resolve_unknown_id_errors_with_id_list():
    with pytest.raises(PoolError) as e:
        resolve_models_json("no-such-model")
    assert "deepseek-v4-flash" in str(e.value)  # lists available ids

def test_resolve_dropped_entry_errors_with_reason():
    with pytest.raises(PoolError) as e:
        resolve_models_json("deepseek-v4-flash:alibaba")  # the dropped alibaba route
    msg = str(e.value)
    assert "dropped" in msg.lower()
    assert "dominated" in msg  # echoes dropped_reason


def test_resolve_alibaba_thinking_disable_generated_from_field():
    # alibaba's disable param is enable_thinking:False, generated from `thinking`.
    spec = resolve_models_json("qwen3.5-flash")
    assert spec.provider == "alibaba"
    assert spec.extra_body == {"enable_thinking": False}


def test_resolve_undropped_deepseek_pro_returns_modelspec():
    # deepseek-v4-pro is un-dropped (#110): now resolves instead of raising.
    spec = resolve_models_json("deepseek-v4-pro")
    assert isinstance(spec, ModelSpec)
    assert spec.provider == "deepseek"
    assert spec.extra_body == {"thinking": {"type": "disabled"}}


def test_resolve_unmapped_provider_injects_no_thinking_param():
    # anthropic has no verified disable param → no_op even though thinking
    # defaults to "disabled"; never inject a guessed param on a paid provider.
    spec = resolve_models_json("haiku-4.5")
    assert spec.provider == "anthropic"
    assert spec.extra_body is None


def test_resolve_invalid_thinking_value_raises_pool_error(monkeypatch):
    import common.model_pool as mp
    bogus = [{"id": "bogus", "provider": "alibaba", "model": "bogus",
              "thinking": "bogus"}]
    monkeypatch.setattr(mp, "load_pool", lambda: bogus)
    with pytest.raises(PoolError):
        mp.resolve_models_json("bogus")


def test_resolve_explicit_extra_body_merges_and_overrides(monkeypatch):
    # thinking-disable param merges with a raw extra_body; explicit keys win.
    import common.model_pool as mp
    crafted = [{"id": "crafted", "provider": "alibaba", "model": "crafted",
                "thinking": "disabled", "extra_body": {"foo": 1}}]
    monkeypatch.setattr(mp, "load_pool", lambda: crafted)
    spec = mp.resolve_models_json("crafted")
    assert spec.extra_body == {"enable_thinking": False, "foo": 1}

def test_load_pool_returns_all_entries_including_dropped():
    pool = load_pool()
    ids = {e["id"] for e in pool}
    assert "deepseek-v4-flash" in ids        # active default
    assert "deepseek-v4-flash:alibaba" in ids  # dropped ones still present (ledger)

def test_resolve_local_model_has_zero_price_and_default_knobs():
    spec = resolve_models_json("gemma4-obsidian-bench")
    assert spec.provider == "ollama-local"
    assert spec.price_in == 0.0 and spec.price_out == 0.0
    assert spec.extra_body is None
    assert spec.use_completion_tokens is False


from common.model_pool import estimate_prompt_tokens, fits_context

def test_estimate_prompt_tokens_words_x_1_3():
    # "a b c d e" + "f g h i j" = 10 words total -> round(10 * 1.3) = 13
    assert estimate_prompt_tokens("a b c d e", "f g h i j") == 13

def test_estimate_prompt_tokens_handles_none_system():
    # system may be None (some prompts have no system part)
    assert estimate_prompt_tokens(None, "a b c d e f g h i j") == 13

def test_fits_context_true_when_input_plus_output_within_window():
    assert fits_context(est_input=900, requested_output=90, ctx_window=1000) is True

def test_fits_context_false_when_over():
    assert fits_context(est_input=950, requested_output=90, ctx_window=1000) is False

def test_fits_context_exact_boundary_is_ok():
    # est_input + requested_output == ctx_window must fit (<=)
    assert fits_context(est_input=910, requested_output=90, ctx_window=1000) is True

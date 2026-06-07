import pytest
from common.model_pool import (
    ModelSpec,
    resolve,
    PoolError,
    UnknownModelError,
    DroppedModelError,
    load_pool,
)


def test_dropped_id_raises_dropped_model_error():
    # The dropped-guard must be distinguishable from "unknown id".
    with pytest.raises(DroppedModelError):
        resolve("deepseek-v4-pro")  # in pool, marked dropped
    assert issubclass(DroppedModelError, PoolError)


def test_unknown_id_raises_unknown_model_error():
    with pytest.raises(UnknownModelError):
        resolve("no-such-model")
    assert issubclass(UnknownModelError, PoolError)

def test_resolve_active_entry_returns_modelspec():
    spec = resolve("deepseek-v4-flash")   # active, direct route, the default
    assert isinstance(spec, ModelSpec)
    assert spec.provider == "deepseek"
    assert spec.model == "deepseek-v4-flash"
    assert spec.ctx_window == 1000000
    assert spec.extra_body == {"thinking": {"type": "disabled"}}
    assert spec.price_in == 0.14 and spec.price_out == 0.28

def test_resolve_unknown_id_errors_with_id_list():
    with pytest.raises(PoolError) as e:
        resolve("no-such-model")
    assert "deepseek-v4-flash" in str(e.value)  # lists available ids

def test_resolve_dropped_entry_errors_with_reason():
    with pytest.raises(PoolError) as e:
        resolve("deepseek-v4-flash:alibaba")  # the dropped alibaba route
    msg = str(e.value)
    assert "dropped" in msg.lower()
    assert "dominated" in msg  # echoes dropped_reason

def test_load_pool_returns_all_entries_including_dropped():
    pool = load_pool()
    ids = {e["id"] for e in pool}
    assert "deepseek-v4-flash" in ids        # active default
    assert "deepseek-v4-flash:alibaba" in ids  # dropped ones still present (ledger)

def test_resolve_local_model_has_zero_price_and_default_knobs():
    spec = resolve("gemma4-obsidian-bench")
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

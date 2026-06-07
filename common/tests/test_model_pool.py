import pytest
from common.model_pool import ModelSpec, resolve, PoolError, load_pool

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

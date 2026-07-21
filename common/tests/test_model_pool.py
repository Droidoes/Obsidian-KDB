import json
import pytest
from pathlib import Path
from common.model_pool import (
    ModelSpec,
    resolve_models_json,
    PoolError,
    UnknownModelError,
    load_pool,
)


def test_dropped_id_now_raises_unknown_model_error():
    # Post-split: a formerly-dropped id is simply not in the active pool.
    with pytest.raises(UnknownModelError):
        resolve_models_json("qwen-flash-us")  # moved to models_dropped.json


def test_moved_out_route_raises_unknown_model_error():
    with pytest.raises(UnknownModelError):
        resolve_models_json("deepseek-v4-flash:alibaba")  # archived route


def test_load_pool_returns_active_entries_only():
    ids = {e["id"] for e in load_pool()}
    assert "deepseek-v4-flash" in ids              # active default
    assert "deepseek-v4-flash:alibaba" not in ids  # archived, NOT loaded by code


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
    # gemini has no verified disable param → no_op even though thinking
    # defaults to "disabled"; never inject a guessed param on a paid provider.
    spec = resolve_models_json("gemini-3.1-flash-lite")
    assert spec.provider == "gemini"
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

def test_gemma4_12b_qat_128k_archived():
    # Archived 2026-06-07: local 12B-QAT too slow + majority of sources
    # quarantined + couldn't finish a 36-source run → moved to
    # models_dropped.json. No active ollama-local model remains.
    with pytest.raises(UnknownModelError):
        resolve_models_json("gemma4-12b-qat-128k")


def test_old_gemma_4_12b_qat_id_gone():
    # The ollama-local placeholder was renamed gemma-4-12b-qat → gemma4-12b-qat-128k
    # (ctx 65536 → 131072) in the #111 roster swap; the old id no longer resolves.
    with pytest.raises(UnknownModelError):
        resolve_models_json("gemma-4-12b-qat")


def test_temperature_null_resolves_to_none():
    # An explicit JSON `null` (gpt-5.4-mini) → spec.temperature is None → OMIT
    # the temperature kwarg on the call (reasoning family 400s on non-default).
    spec = resolve_models_json("gpt-5.4-mini")
    assert spec.temperature is None
    # extra_body / reasoning config unchanged by the temperature swap.
    assert spec.extra_body == {"reasoning_effort": "low"}
    assert spec.use_completion_tokens is True


def test_temperature_absent_defaults_to_zero():
    # A model without the key → spec.temperature == 0.0 (deterministic default).
    spec = resolve_models_json("deepseek-v4-pro")
    assert spec.temperature == 0.0


def test_old_gemma_bench_alias_gone():
    with pytest.raises(UnknownModelError):
        resolve_models_json("gemma4-obsidian-bench")


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


def test_deprecated_grok_is_archived():
    with pytest.raises(UnknownModelError):
        resolve_models_json("grok-4-1-fast-reasoning")  # deprecated → archived

def test_retired_grok_4_20_archived():
    # Retired 2026-07-21: xAI deprecated the dated grok-4.20 variant
    # (successor: grok-4.3 flagship; xAI killed the 4-1-fast line 2026-05-15).
    # Never fired in the current-gen cohort — pool-only retirement, no board row.
    with pytest.raises(UnknownModelError):
        resolve_models_json("grok-4.20-0309-non-reasoning")


def test_retired_gemini35_flash_archived():
    # Added + retired 2026-07-21 (same day): two cohort runs at both thinking
    # levels flopped identically — systematic 'Extra data' trailing-content
    # JSON on Pass-2 (10 then 13 quarantined). Un-retire trigger: #111
    # Phase-2 response_json_schema. See models_dropped.json for the evidence.
    with pytest.raises(UnknownModelError):
        resolve_models_json("gemini-3.5-flash")


def test_retired_qwen36_flash_us_archived():
    # Added + retired 2026-07-21 (same day): first cohort run quarantined 3/36
    # sources (2 structured-contract failures, 1 DashScope content-filter 400);
    # bottom board score. See models_dropped.json for the full evidence trail.
    with pytest.raises(UnknownModelError):
        resolve_models_json("qwen3.6-flash-us")


_COMMON_DIR = Path(__file__).parent.parent

def test_active_pool_has_no_dropped_entries():
    # After the split, models.json holds ACTIVE entries only.
    active = json.loads((_COMMON_DIR / "models.json").read_text(encoding="utf-8"))
    assert all("dropped" not in e for e in active), \
        "models.json must not contain dropped entries after the split"

def test_dropped_archive_is_valid_json_and_holds_the_moved_entries():
    arch = json.loads((_COMMON_DIR / "models_dropped.json").read_text(encoding="utf-8"))
    ids = {e["id"] for e in arch}
    assert {"gemini-3-flash-preview", "deepseek-v4-flash:cloud",
            "qwen-flash-us", "deepseek-v4-flash:alibaba",
            "haiku-4.5", "sonnet-4.6"} <= ids
    assert all(e.get("dropped") is True and e.get("dropped_reason") for e in arch), \
        "archive entries keep their dropped/dropped_reason record"


def test_retired_anthropic_models_archived():
    # Retired 2026-07-21: Anthropic models left the pool (no API calls, no
    # benchmark references — other providers caught up) → models_dropped.json.
    with pytest.raises(UnknownModelError):
        resolve_models_json("haiku-4.5")
    with pytest.raises(UnknownModelError):
        resolve_models_json("sonnet-4.6")


def test_gpt_5_4_mini_carries_reasoning_config():
    spec = resolve_models_json("gpt-5.4-mini")
    assert spec.provider == "openai"
    assert spec.extra_body == {"reasoning_effort": "low"}


def test_retired_glm_5_turbo_archived():
    # Added + retired 2026-07-21 (same day): first cohort run quarantined 5/36
    # (4x systematic page_type omission on non-summary pages + 1x z.ai
    # content-filter 400 on the Li Lu lecture — the same source DashScope
    # blocked; two-provider compliance-layer pattern). Slowest + priciest run
    # of the cohort; board 26.00, rank 4/5. See models_dropped.json.
    with pytest.raises(UnknownModelError):
        resolve_models_json("glm-5-turbo")

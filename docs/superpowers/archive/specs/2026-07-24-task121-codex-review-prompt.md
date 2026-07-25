Design review request — Task #121 options (config-driven provider wiring).

Repo: /home/ftu/Droidoes/Obsidian-KDB, branch main (HEAD ed3a21d).

Joseph's proposal: each entry in `common/models.json` gains an `endpoint` field and an api-key-name field, so the per-provider hardcoded `elif` chain in `common/call_model.py:86-122` (base_url + settings key per provider) becomes config-driven. Review the options doc — it is the review target:
  docs/superpowers/archive/specs/2026-07-24-task121-config-driven-provider-wiring-options.md

The three options on the table:
1. Per-entry `endpoint` + `api_key_env` with provider-default fallback (recommended in the doc) — chain collapses to a generic lookup; native handlers (gemini, anthropic) untouched; today's hardcoded values survive only as provider defaults; the 4 active entries get fields byte-identical to current wiring.
2. Fields required on every entry, chain deleted, pool-load validation — zero hardcoding, biggest diff, new failure mode.
3. A provider registry (provider → endpoint/key-env) instead of per-model fields — most DRY, loses per-model routing (the qwen3.6-flash vs -us precedent says per-model routing is real).

Plus a sub-question: `api_key_env` as env var name resolved via os.getenv (doc's lean) vs Settings attribute via getattr.

Ground truth to check against:
- `common/call_model.py:86-122` (the elif chain), `:140-167` (anthropic + gemini native paths), `:208` (the openai-SDK shared helper).
- `common/model_pool.py` (`ModelSpec`, `resolve_models_json`, `load_pool`).
- `common/models.json` (4 active entries) + `common/models_dropped.json` (human-only archive).

Focus areas:
1. Which option — is Option 1's fallback table the right amount of residual hardcoding, or is Option 3's registry strictly better given only 4 active entries and 2 providers in use? Is there a fourth shape none of us see?
2. Env-var-name vs settings-attribute for the key field.
3. Pitfalls the doc misses: the openai provider's `base_url=None` convention (default SDK endpoint); ollama-local's dummy key (`api_key="ollama"`); the `_THINKING_DISABLE_EXTRA_BODY` per-provider params; does anything else consume provider→routing mappings (telemetry pricing, model_pool tests)?

Verdict format: GO (with a chosen option) or REVISE, with numbered findings (Critical/Important/Minor, file:line, concrete fix). Write your review to:
  docs/superpowers/archive/specs/2026-07-24-task121-config-driven-provider-wiring-options-review-codex.md

Design review request, round 2 — Task #121 options v1.1 (config-driven provider wiring).

Repo: /home/ftu/Droidoes/Obsidian-KDB, branch main (HEAD ed3a21d).

Your R1 review (`2026-07-24-task121-config-driven-provider-wiring-options-review-codex.md`, verdict REVISE, 5 findings) has been absorbed, plus three decisions from Joseph. The review target is the revised doc:
  docs/superpowers/archive/specs/2026-07-24-task121-config-driven-provider-wiring-options.md (v1.1)

What changed from v1.0 — please verify the absorption is faithful and complete:

1. **F1 (no end-to-end carrier) → ModelRoute adopted.** `ModelRoute(api_type, endpoint, api_key_env)` frozen dataclass; non-optional on `ModelSpec`, optional (`None`) on `ModelRequest`; threaded CLI boundary → `run()` → `call_pass1` / `compile_one` → `ModelRequest`. Forwarding drop-guard tests at both pass boundaries.
2. **F2 (absent/null/URL + escape hatch + Ollama) → two-class layering.** Class A (active pool entries): route REQUIRED, authoritative, validated at pool-resolution; registry never consulted. Class B (raw `--provider` escape hatch, direct `ModelRequest`): provider-default registry in `common/call_model.py` is the compatibility boundary — its only job. Registry owns the special cases: `OLLAMA_BASE_URL` env-overridable endpoint and the literal dummy key `"ollama"` (no-auth ⇒ `api_key_env: None`). Three-state contract: absent = load error, explicit `null` = SDK built-in URL, URL = override.
3. **F3 (mis-cited qwen precedent) → evidence statement corrected.** Doc now states there is no same-provider endpoint variance in repo history; per-model fields justified as ownership/flexibility policy (Joseph's explicit request + future override seam); deepseek triple-route cited as cross-provider variance only.
4. **F4 (api_key_env inert on native) → uniform late resolution.** Env-var NAME resolved to a key once at the final call boundary for ALL transports; resolved value passed into `_call_openai_compat` / `_call_gemini` / `_call_anthropic`; lookup helper in `common.config`; missing var → ModelConfigError naming variable+model+provider, never the value. Test mechanics migrate `_use_settings` → `monkeypatch.setenv`.
5. **F5 (happy-path-only acceptance) → expanded acceptance**: load-time validation, both-pass forwarding, byte-identical active routes, retained-provider registry pins, unknown-provider/missing-key/malformed-route errors, escape-hatch parity, no-secret-in-errors, `_THINKING_DISABLE_EXTRA_BODY` + pricing unchanged, docs at closure.

Joseph's decisions folded in:
- **D1**: your layered fourth shape adopted (supersedes v1.0 Options 1–3; kept as record).
- **D2**: `api_key_env` = environment-variable NAME (e.g. `"DEEPSEEK_API_KEY"`).
- **D3**: explicit `api_type` field (`"openai_compat"` | `"anthropic"` | `"gemini"`) — dispatch switches on the declared type instead of inferring transport from provider; new provider of an existing type = pure JSON, new type = one handler + one enum value. (Value naming is a noted bikeshed deferred to spec.)
- **D4 (added after v1.1 draft)**: fail-hard config contract — missing/incorrect config fails loudly at pool-resolution (`PoolError`) or the call boundary (`ModelConfigError`); NO catch-all, no `or DEFAULT` on route fields, no config-resolution try/except; the Class-B registry is consulted only when `ModelRequest.route is None`, never as a rescue for a broken pool entry; SDK errors propagate. This codifies today's engine behavior — verify the rewrite preserves it by construction.

Ground truth to check against:
- `common/call_model.py:41-62` (ModelRequest), `:86-125` (elif chain), `:139-204` (native handlers), `:207-216` (shared openai-compat helper)
- `common/model_pool.py:39-97` (ModelSpec, resolve_models_json), `:57-61` (archive-never-read)
- `orchestrator/kdb_orchestrate.py:1082-1118` (CLI boundary + escape hatch)
- `ingestion/enrich/pass1_caller.py:104-109,169-176` and `compiler/compiler.py:150-167,354-370` (ModelRequest construction sites)
- `common/config/__init__.py:39-70` (settings, OLLAMA_BASE_URL)
- `common/tests/test_call_model.py:252-321,433-467` (retained-route + error-path pins), `scripts/verify_structured_output_parity.py:51-70` (direct ModelRequest caller)

Focus areas:
1. Is the ModelRoute carrier + two-class layering airtight, or is there still a path where routing authority is ambiguous (e.g. a pool entry whose route partially resolves, a caller that fabricates a route)?
2. Is dispatch-on-`api_type` (D3) sound, and does it interact correctly with the `provider` field's remaining consumers (pricing, `_THINKING_DISABLE_EXTRA_BODY`, telemetry identity)?
3. The os.getenv-at-call-boundary change: any timing/caching hazard vs `common.config`'s .env loading, and is the test-mechanics migration (`monkeypatch.setenv`) sufficient?
4. Anything in the validation contract or acceptance list still missing before this becomes a spec.
5. D4 audit: is there any path in the proposed design (or in today's code that survives the rewrite) where missing/incorrect config silently degrades to a default instead of failing? Check the escape-hatch path, pool resolution, env-var resolution, and the native handlers.

Verdict format: GO or REVISE, with numbered findings (Critical/Important/Minor, file:line, concrete fix). Write your review to:
  docs/superpowers/archive/specs/2026-07-24-task121-config-driven-provider-wiring-options-review-codex-v2.md

# Pass-1 Prompt Review — Synthesis (Task #95)

5-model panel (Codex, DeepSeek, Gemini, Grok, Qwen), full-panel, findings
withheld. All 5 guardrail-clean (git status: only `review-*.md` added). Below:
convergence table, our-vs-theirs reconciliation, then the prioritized fix set.

## Convergence table

| # | Finding | Codex | DeepSeek | Gemini | Grok | Qwen | Conv | We had it? |
|---|---------|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| C-1 | **4 code-owned fields wrongly requested** (`override`/`model`/`prompt_version`/`schema_version`); `override` caused the #21 failure | CRIT | CRIT | CRIT×2 | CRIT | CRIT | **5/5** | ✅ yes |
| C-2 | **No complete JSON exemplar** — 15 fields assembled from prose | HIGH | HIGH | HIGH | HIGH | HIGH | **5/5** | ✅ yes |
| C-3 | **domain/source_type ambiguity → AI-tooling tagged `software` not `ai-ml`** | MED | MED | MED | MED | MED | **5/5** | ✅ yes (Joseph) |
| C-4 | **`entity_search_keys` volume pressure → noisy slugs** (`accountuuid`, `cc-buddy`, `any-buddy`, `legendary`) | MED | HIGH | HIGH | — | MED | **4/5** | ✗ new |
| C-5 | `<your kdb_signal>` placeholder syntax ambiguous (only angle-bracket in prompt) | — | — | ✅(in C-1) | — | LOW | 2/5 | ✅ yes (partial) |
| C-6 | `confidence`/`uncertainty_reason` coupling unsatisfiable ("signal but with doubt") | HIGH | — | — | — | LOW | 2/5 | ✗ new |
| C-7 | bias-to-signal buried in preamble, not restated at `kdb_signal` | — | — | — | MED | — | 1/5 | ✗ new |
| C-8 | `summary` length/voice underspecified (marketing register creep) | — | — | MED | — | — | 1/5 | ✗ new |
| C-9 | enum description lead-ins redundant (token bloat) | — | — | — | LOW | — | 1/5 | ✗ new |
| C-10 | no explicit "no markdown fences" guard | — | MED | — | — | — | 1/5 | ✗ new |
| C-11 | `key_themes` vs `entity_search_keys` overlap | LOW | — | — | — | — | 1/5 | ✗ new |

## Our 4 withheld findings vs panel

1. **Role sentence is meaningless jargon** ("Pass-1 enrichment classifier…") — **panel did NOT raise this.** 0/5. Our unique catch. (They focused on output-contract mechanics; the role/framing got a pass. Worth deciding if it matters — it's a cheap fix either way.)
2. **No full JSON exemplar** → **C-2, 5/5 convergent.** Strongly validated.
3. **4 code-owned fields** → **C-1, 5/5 convergent, all CRITICAL.** The load-bearing finding. Unanimous.
4. **`software`-over-`ai-ml`** → **C-3, 5/5 convergent.** Every reviewer independently found it in the data. Strongly validated. Reframed by all as a *boundary-rule tie-breaker* gap, not a model failure.

## Net new from panel (we missed)

- **C-4 (4/5):** `entity_search_keys` over-production. Strong — 4 reviewers cited the same junk slugs from the Buddy System note. The "aim for 5–10" target + 4 inclusion sub-rules push padding. Fix = quality ceiling, not a count target.
- **C-6 (2/5, 1 HIGH):** `confidence`/`uncertainty_reason` "signal but with doubt" is unsatisfiable/subjective. Codex flags HIGH.
- **C-7/C-8/C-10 (1/5 each):** bias-to-signal restatement · summary register · no-fences guard — low-cost, worth folding.

## Deeper convergent insight (Grok F-3 + Gemini F-1 + DeepSeek F-1)

The `override` block isn't just "code-owned" — it's **incoherent from the model's
seat**: `applied`/`rule`/`match` describe whether a *deterministic force-rule*
fired, which the model has **no access to**. So even a perfectly compliant model
can only guess nulls. This sharpens our own finding: it's not merely redundant,
it asks the model for information it structurally cannot have. (Matches Joseph's
[1]: "this is not redundant/fragile, it is wrong, period.")

## Prioritized fix set (for the #95 contract correction)

**Tier 1 — unanimous, do all:**
1. Remove `override`, `model`, `prompt_version`, `schema_version` from the prompt;
   deterministic layer injects them post-parse (C-1, 5/5).
2. Add one complete worked JSON exemplar before "Return the JSON envelope now."
   (C-2, 5/5).
3. Add a domain tie-breaker for AI-tooling content (ai-ml vs software) (C-3, 5/5).

**Tier 2 — strong, fold in:**
4. Reframe `entity_search_keys` as a quality ceiling, drop "aim for 5–10" (C-4, 4/5).
5. Make `uncertainty_reason` a single objective trigger; drop "signal but with
   doubt" (C-6, 2/5 + 1 HIGH).

**Tier 3 — cheap, low-risk:**
6. Restate bias-to-signal at `kdb_signal` (C-7); tighten `summary` register (C-8);
   add no-markdown-fences guard (C-10); our role-sentence rewrite (0/5 but cheap).

**Open decision for Joseph (C-3 substance):** the tie-breaker direction. Panel
consensus: "notes about *using/building AI tools* → `ai-ml`; general OS/dev
tooling → `software`." This matches your `ai-ml`-lean intuition. But it's a real
ontology call (it widens `ai-ml`) — your ratification needed before we encode it.

# Task #106 — JSON-repair + slug-coercion ladder — Spec Review Prompt (design panel)

> Sent **verbatim** to all 5 CLI reviewers (Codex · Deepseek · Qwen · Gemini · Grok). Only `<OUTPUT_FILE>` differs per reviewer (e.g. `docs/superpowers/specs/2026-06-02-task106-review-codex.md`). Repo root: `/home/ftu/Droidoes/Obsidian-KDB`, branch `main` (Phase B / `v0.5.2` landed).

---

You are a senior staff engineer **pressure-testing a design spec before implementation**. This is a **DESIGN review**, not a code review — nothing is built yet. Your job: find design flaws, missed edge cases, wrong placements, and gaps in the guardrails **now**, while they're cheap to fix. Be skeptical and specific; cite `file:line` in the spec and in the real code you check against. A sharp catch here saves an implementation cycle.

## HARD GUARDRAIL — read first, non-negotiable
- **Read-only.** Do NOT modify, create, rename, or delete ANY file **except** the single output file named at the end (`<OUTPUT_FILE>`). Write your entire review there and nowhere else.
- No state-changing git (`add`/`commit`/`checkout`/etc.), no `pip install`, no formatters. Read-only commands only (`git diff/log/show`, `grep`/`rg`, `cat`, `ls`, `sed -n`).
- You will NOT run tests (nothing is implemented). Verify by reading the spec against the real code.

## The spec under review
**`docs/superpowers/specs/2026-06-02-json-repair-slug-coercion-ladder-design.md`** — read it in full. It proposes a deterministic **repair/normalize ladder** for two recoverable LLM-output malformation classes in the Pass-2 compiler, both currently rescued only by a stochastic retry:
1. **JSON-syntax** (bytes don't parse) — e.g. an unescaped LaTeX `\(n-1\)` inside a JSON string → `Expecting ',' delimiter`. Proposed fix: the `json-repair` pip package, gated on re-parse + schema + semantic. Home: `common/util/json_repair.py` (new).
2. **Schema/slug** (parses, a slug violates the kebab pattern) — e.g. a title's `" - "` slugified to `---`. Proposed fix: a conservative `collapse_slug` (collapse `-{2,}`→`-`, strip edge `-`; nothing else) that **enforces the existing D19 slugify rule post-LLM**, with full reference-propagation across all slug-bearing fields + a collision guard. Homes: transform in `common/paths.collapse_slug()`, rename/propagation/collision-guard in `compiler/repair`.

Ladder: `emit → repair/normalize → validate; else retry (1 fresh emission) → repair/normalize → validate; else quarantine`. Every repair is **re-validation-gated** (must pass the same parse→schema→semantic it would without repair).

## Real code to check the design against (Phase B / v0.5.2 has landed — these paths are live)
- Compile attempt loop + insertion points: `compiler/compiler.py` (loop @242; `json.loads` @305; `validate_source_response.validate` @322).
- Existing reconcilers the new propagation joins: `compiler/repair.py` (`reconcile_body_links` @153, `reconcile_slug_lists` @179, `repair` @220).
- Slug policy the coercion enforces: `common/paths.py` (`slugify` @51, `validate_slug` @63, `SLUG_PATTERN` @26).
- The contract that defines the slug-bearing fields to propagate across: `compiler/schemas/compiled_source_response.schema.json`.
- Existing retry/coercion precedent (#104): same `compiler/compiler.py` attempt loop.

## Pressure-test these (the design's load-bearing decisions)
1. **Rung-1 mechanism — is `json-repair` the right tool, or a liability?** The spec flags a **content-fidelity hole**: `json-repair` may "fix" the unescaped `\(` by silently stripping the backslash, producing valid JSON that passes every gate while corrupting the LaTeX (schema/semantic validate structure, not body content). Is the spec's mitigation (probe behavior + consider **targeted backslash-escaping** instead) right — or should rung-1 be targeted escaping of the *known* class (stray `\` before a non-JSON-escape char) from the start, with `json-repair` rejected as too aggressive? Are there other content-corrupting "repairs" `json-repair` could pass through the gates?
2. **Slug-coercion scope.** Is collapse-`-{2,}` + edge-strip the right conservative boundary? Anything benign-and-confirmed it wrongly excludes, or anything it includes that risks masking a real failure? Is "enforce D19 post-LLM" a sound framing, or does silently rewriting an identifier the LLM emitted violate the "strict extraction" intent more than the spec admits?
3. **Reference-propagation completeness.** Cross-check the spec's slug-bearing field list (§4b) against the REAL `compiler/schemas/compiled_source_response.schema.json`. Is any slug-bearing field missed (which would leave a dangling reference after a rename)? Is the whole-`[[token]]`-not-substring rule sufficient? Does the collision guard (refuse on two distinct slugs colliding) cover the case where a collapsed slug collides with an **already-valid existing** slug (not just two malformed ones)?
4. **Placement & ordering.** Rung 1 at parse-fail, rung 2 at schema-fail, both inside the attempt loop before the retry branch (§5). Any interaction bug — e.g. does rung-2's coercion need a re-run of the *semantic* check (not just schema), and does the spec's "re-validate (schema + semantic)" actually happen at that point in `compiler/compiler.py`'s flow (semantic runs AFTER the loop `break` today)? Does inserting repair change the meaning of `_MAX_COMPILE_ATTEMPTS` or the existing #104 retry?
5. **Homes & dependency contract.** `common/util/json_repair` (new), `common/paths.collapse_slug`, `compiler/repair`. Do these respect the B.3 contract (`compiler→common` legal; `common` stays a leaf)? Is `common/util/` the right home for the json helper, or does it belong elsewhere? Is putting `collapse_slug` in `common/paths` (vs `common/util`) the right "policy-not-util" call?
6. **The re-validation guardrail — is it actually airtight?** It's the spec's core safety claim ("a bad repair just falls to the next rung"). Where does it leak? (The content-fidelity hole is one leak — are there others, e.g. a slug collapse that produces a valid-but-semantically-wrong graph edge that passes schema+semantic?)
7. **Measurability** (§7 rung taxonomy `clean/repaired-syntax/coerced-slug/retried/quarantined`) — sufficient to detect over-reach? Anything missing to make a bad repair observable?
8. **Scope & omissions.** Pass-2 now, Pass-1 later (§6) — right call? Is there a **third** recoverable class the two live examples hint at but the spec doesn't cover? Does the design interact correctly with #104's existing retry/coercion (no double-repair, no masking)?

## Output — write ONLY to `<OUTPUT_FILE>`
1. **Verdict:** `GO` (sound, proceed to writing-plans) / `GO-WITH-CHANGES` (proceed after folding specific fixes) / `REWORK` (a load-bearing decision is wrong).
2. **Findings**, each: `[Severity: Critical | High | Medium | Low]` · spec §/`file:line` · the flaw · why it matters · concrete suggested change.
3. Group under: **(a) correctness/safety of the design**, **(b) scope & conservatism calls**, **(c) placement/integration with the real compiler flow**, **(d) homes/contract**, **(e) gaps/omissions**. If a group is empty, say "none".
4. **One-paragraph bottom line:** is this design sound enough to turn into an implementation plan, and what (if anything) must change first. Call out explicitly your position on the **rung-1 `json-repair` vs targeted-escaping** fork — that's the decision most likely to be wrong.

# Pass-1 Prompt Review — Panel Brief (Task #95)

You are reviewing a **production LLM prompt** and a sample of its **real outputs**.
This is a focused prompt-design review, not a code review.

## Output guardrail (READ FIRST)

Write your review to **one single output file** at the path the dispatcher gives
you (e.g. `docs/task95-pass1-review/review-<yourname>.md`). **Do NOT modify any
other file in this repository** — no edits to the prompt, the schema, source
code, tests, or any other doc. You have filesystem read access to inspect the
artifacts; your only write is your own review file. This guardrail is mandatory.

## What this prompt does

`kdb` is a personal knowledge-base compiler: it turns raw markdown notes into a
knowledge graph. **Pass-1** is the first LLM step — it reads ONE markdown
document and returns a JSON "envelope" classifying it (is it worth keeping? what
is it about? what form does it take?). A later deterministic layer validates that
JSON, applies some overrides, and writes it back as YAML frontmatter on the
source file. The Pass-1 output feeds graph construction downstream.

## The artifacts to review (all in `docs/task95-pass1-review/`)

1. **`rendered_pass1_prompt.txt`** — the EXACT prompt text sent to the model
   (variables resolved; only the source body is stubbed). This is the artifact
   under review. ~200 lines.
2. **`pass1_responses_all.md`** — 21 REAL responses from one model
   (`deepseek-v4-flash`) to this exact prompt, over a real 36-file vault. Each is
   the model's verbatim JSON output. 20 parsed cleanly; 1 (`How Not to Age`)
   failed and its body was **not captured** — that is a known observability gap
   on our side (the raw response was discarded on failure), NOT something for you
   to analyze or work around. Treat it as absent.
3. **`pass1_schema.py.txt`** — the validation schema. **IMPORTANT:** this schema
   is used ONLY to validate the model's output *after the fact* — it is **NOT**
   sent to the model and does **NOT** constrain generation (the call uses a soft
   "return JSON" mode, not enforced structured output). So the prompt TEXT is the
   model's only contract.

## The lens we want (this is the important part)

**Read the prompt AS IF YOU WERE THE LLM receiving it.** For every instruction,
ask: *Can I actually follow this? Is it unambiguous? Does it mean anything to me,
or is it the author's internal jargon? Do I have enough to produce exactly the
JSON they expect?*

We are specifically NOT looking for generic "make it more polite" prompt tips. We
want concrete, model's-seat findings.

## Questions to answer

1. **Followability:** Where would you, as the model, be unsure what to emit?
   Quote the exact line and explain the ambiguity.
2. **Field ownership:** Are there fields the prompt asks the model to emit that
   the model has no business producing (i.e., values the *calling system* should
   own, not the LLM)? Name them and explain.
3. **Output format:** Is the expected JSON object specified clearly enough to
   reproduce exactly (key names, nesting, all fields)? What's missing?
4. **Meaningless-to-the-model content:** Any text written in the author's
   internal vocabulary that gives you no actionable signal? Quote it.
5. **Evidence from the 20 real responses:** Where the outputs diverge from what
   the prompt seems to intend, is the cause the PROMPT (ambiguous/under-specified)
   or the MODEL (ignored a clear instruction)? Cite specific response examples.
   Note any classification you find questionable (e.g. domain/source_type picks
   that seem off given the prompt's own rules).
6. **Cuts and additions:** What would you remove (noise/bloat) and what's the
   single highest-value thing to add?

## Output format for your review file

- A short **summary** (2-4 sentences): is this prompt followable as written?
- A numbered **findings** list. For each: severity (critical/high/medium/low),
  the exact quoted line(s), the problem, and a concrete fix.
- Keep it concrete and cite line numbers / response examples.

Do not coordinate with other reviewers; independent findings are the point.

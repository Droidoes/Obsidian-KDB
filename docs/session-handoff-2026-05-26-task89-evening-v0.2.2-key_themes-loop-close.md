# Session Handoff — 2026-05-26 (evening) — Task #89 v0.2.2 key_themes loop-close

Forensic-walk session: Joseph-led architectural deliberation on what Pass-1's `key_themes` and `key_entities` fields are FOR. Triggered by the Phase E checkpoint's Bug #2 (no landing place for D-89-18's "merged summary"). Ended with two new locked decisions (D-89-19, D-89-20), one full retraction (D-89-18), one partial retraction (D-89-17), and the Task #90 input contract locked.

**No code changes this evening — pure decision-record updates.** Implementation arc resumes next session.

## Discussion arc

1. **Bug #2 surfaced** four candidate paths (a/b/c/d) for where the LLM-merged Source.summary should land. None felt clean.
2. **Joseph pushed back on "intelligent merge" spec** — asked for a sharp definition or concession to mechanical concat. Surfaced the deeper question: what does Pass-2 do with `key_themes`?
3. **Reframe attempt #1 — option (α) themes-as-concept-candidates** — rejected by Joseph: Pass-2 has body; doesn't need pre-extracted concept hints from Pass-1.
4. **Forensic walk of `graph_context_loader`** — surfaced T1/T2/T3 tier algorithm. T2's whole-word slug regex is a pre-Pass-1 heuristic.
5. **Reframe attempt #2 — option (δ) themes feed T2 directly** — promising; led to filing Task #90 (Context-loader T2-rewrite).
6. **Joseph's proposal — `entity_search_keys`** as a purpose-built Pass-1 field. Single sharp consumer (T2-rewrite). Replaces vague descriptive fields.
7. **Joseph's revised proposal** (lower implementation cost): keep `key_themes`, mechanically append to Source.summary, add `entity_search_keys` (≤10 slugs) broadly derived (themes + entity names + related concepts). Pure additive.
8. **Q1 challenge** — Joseph: "why not persist the appended Source.summary?" — assistant conceded the "clean prose" argument was aesthetic; locked persisted version (single source of truth).
9. **Same lens applied to `key_entities`** — Joseph: *"key_entities was an unconscientious attempt to create entity_search_keys"* — drop `key_entities` entirely; `entity_search_keys` subsumes it.

## What got ratified

| ID | Decision | Status |
|---|---|---|
| **D-89-19** | Source.summary = `Pass-1 summary + ". Themes: " + ", ".join(key_themes) + "."` — mechanical append in `compiler.py`; persisted to GraphDB Source.summary; Pass-2 sees the same string | Locked |
| **D-89-20** | Drop `key_entities`; add `entity_search_keys: list[str]` (≤10 kebab-case slugs); sole consumer is Task #90 T2-rewrite | Locked |
| **D-89-18** | Compile LLM merges summary + key_themes | **RETRACTED** — superseded by D-89-19 (mechanical append) + D-89-20 (entity_search_keys upstream of Pass-2) |
| **D-89-17** | Compile consumes frontmatter (`USE domain/source_type/author` + `TREAT key_entities as seeds`) | **Partial retract** — `key_entities` clause dropped; rest stays in force |
| **Task #90 input contract** | `entity_search_keys` is the sole structured signal T2-rewrite consumes | Locked in `docs/TASKS.md` |
| **Bug #2** | "Where does merged_summary land" problem | **DISSOLVED** — there is no merged_summary; mechanical append goes directly to Source.summary |
| **Bug #1** | `Source.source_type` hardcoded at `graphdb_kdb/ingestor.py:144` | Independent — still needs fix |

## Pass-2's view of Pass-1 frontmatter at steady state

```
## PASS-1 SOURCE METADATA

### Frontmatter values
- domain: {domain}
- source_type: {source_type}
- author: {author}

### Source summary (Pass-1 verbatim + appended themes per D-89-19)
{summary}

Instructions:
- USE domain, source_type, and author directly. Do NOT re-derive them.
- The summary above is authoritative; you do not need to rewrite or merge it.
```

Pass-2 no longer sees `key_themes` or `key_entities` as separate fields. The MERGE instruction is gone. The TREAT-as-seeds instruction is gone.

## `entity_search_keys` Pass-1 prompt section (draft)

To be slotted into `kdb_compiler/ingestion/pass1_prompt.j2`:

```text
─── entity_search_keys ─────────────────────────────────────────────

Generate up to 10 kebab-case slug candidates designed to find related
existing entities in a downstream knowledge graph (where each entity is
keyed by a concept slug). The graph contains entities for notable people,
concepts, frameworks, themes, and named ideas across many sources.

What to include:
  1. Each item in key_themes (themes themselves are often already entity slugs).
  2. Common slug variants of each theme (e.g., for "value-investing" you might
     also include "value-investor" or a closely-related concept like "intrinsic-value").
  3. Slugs for entity names mentioned substantively in the source — people,
     organizations, named frameworks. Use surname-only for well-known figures
     ("buffett") and/or full-name form ("warren-buffett") when ambiguity is
     possible.
  4. Closely-related concepts that frequently co-occur with the source's
     themes, even if not named explicitly (a small fanout for graph discovery).

Format:
  - Lowercase, hyphens between words, no spaces, no punctuation other than hyphens.
  - Prefer specificity over breadth: "value-investing" beats "investing";
     "graham-and-doddsville" beats "investors".
  - Cap at 10 keys total. Aim for 5–10.

Example:
  source: Li Lu interview about Warren Buffett and Charlie Munger's value-investing approach
  key_themes: ["value-investing", "margin-of-safety", "compounding"]
  → entity_search_keys: ["value-investing", "margin-of-safety", "compounding",
                         "warren-buffett", "buffett", "charlie-munger", "munger",
                         "intrinsic-value", "berkshire-hathaway", "circle-of-competence"]
```

Joseph delegated final wording to the implementer; refine when wiring it into the actual template.

## Next-session implementation footprint

Pure deletions + additive; no schema migration; backward-compat preserved for pre-Pass-1 sources.

**Pass-1 producer side:**
- `kdb_compiler/ingestion/pass1_schema.py` — drop `key_entities`; add `entity_search_keys`
- `kdb_compiler/ingestion/pass1_prompt.j2` — drop `key_entities` bullet; add `entity_search_keys` section
- `kdb_compiler/ingestion/frontmatter_embedder.py` — field list update
- `kdb_compiler/ingestion/enrich.py:99` — default-empty dict update

**Compile-side integration:**
- `kdb_compiler/compiler.py:298` — implement D-89-19 mechanical append in `source_meta_dict["summary"]`; drop `key_themes` + `key_entities` keys
- `kdb_compiler/compiler.py:115,130,456` — remove `key_entities` references
- `kdb_compiler/prompt_builder.py:130-145,154-170,186-191` — remove MERGE + key_entities sections from PASS-1 META block; replace with the simplified contract above
- `graphdb_kdb/ingestor.py:144` — **Bug #1** independent fix (set `Source.source_type` from `source_meta.source_type`)

**Test:**
- `kdb_compiler/tests/test_pass1_end_to_end.py` (uncommitted from 2026-05-26 morning) — revise the 5 contract assertions to match the D-89-19/D-89-20 reality; fire live; commit if green.

## E.2 (closure ceremony — still pending)

After E.1 test fires green:
1. Append Milestone Changelog entry to `docs/CODEBASE_OVERVIEW.md` per `[[feedback_milestone_closure_rule]]`
2. Flip `docs/TASKS.md` #89 status to closed
3. Commit
4. Memory updates (`feedback_gemini_review_only_guardrail` with agy 3-for-3 evidence; possibly a new memory on "consumer-purpose test for Pass-1 fields")

## Honest assessment

Tonight's session was a clean architectural loop-close — no code shipped, but the architecture got materially better. The Phase E checkpoint had two bugs blocking acceptance; one is now dissolved (Bug #2), the other is unaffected and still small (Bug #1). The Task #90 input contract is locked, giving the future T2-rewrite a clean target.

The bigger lesson: applying a consumer-purpose test to every Pass-1 field surfaced that `key_themes` and `key_entities` were both vague descriptive fields without sharp downstream needs. `entity_search_keys` is the first Pass-1 field where the producer's job is shaped by the consumer's actual data need — and tonight's deliberation showed how much architectural clarity that buys.

Branch state: 1 commit will land tonight (this checkpoint + blueprint v0.2.2 amendments + TASKS.md updates). Pass-1 implementation code changes still ahead for tomorrow.

---

**Status:** v0.2.2 decisions ratified; implementation arc pending; Task #90 input contract locked.

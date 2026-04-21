# Context Pages — the LLM's view of prior KDB state

This doc explains **what a context page is**, **why they exist**, **how they're selected** for each compile call, and **what the cold-start case looks like** (EP1, 2026-04-20 repro).

> **Placement note.** Despite this filename, context pages are part of the **user** prompt half, not the system prompt. The system half is `KDB-Compiler-System-Prompt.md` + `RESPONSE_CONTRACT` (both static across a run). The user half is what varies per-source, and the context snapshot is a block inside it — see `docs/example-prompt-ep1-china.md` for a full concrete example.

Related docs: `kdb_compiler/prompt_builder.py`, `kdb_compiler/context_loader.py`, `docs/wiki.md`, `docs/CODEBASE_OVERVIEW.md` §Track 1.

---

## 1. What a context page is

A **context page** is a body-free snapshot of one *already-existing* wiki page. It has exactly four fields (D8 — drop bodies, paths, timestamps):

```json
{
  "slug": "attention-mechanism",
  "title": "Attention Mechanism",
  "page_type": "concept",
  "outgoing_links": ["transformer", "self-attention", "softmax"]
}
```

The full **context snapshot** sent in the user prompt is:

```json
{
  "source_id": "KDB/raw/<current-source>.md",
  "pages": [<ContextPage>, <ContextPage>, ...]
}
```

That's the LLM's **only** window into prior KB state during a compile. No bodies, no paths, no timestamps, no frontmatter, no hashes — just the minimum the model needs to know which slugs exist and how they link to each other.

---

## 2. Why they exist — compounding vs fragmentation

Without context pages, every compile is a cold start. The LLM would:

- Mint a fresh slug for every concept it names, even when the KB already has that exact concept under a different wording
- Have zero incentive to reuse `[[attention-mechanism]]` vs inventing `[[attn-mechanism]]` vs `[[attention-mech]]`
- Produce parallel ontologies per-source instead of one compounding ontology

With context pages, the LLM sees *"these slugs already exist — use them if you're talking about the same thing"* and the three-type wiki (see `wiki.md`) accumulates instead of fragmenting.

This is the single most important feedback loop in the compile pipeline. If context-page selection is weak, the ontology fragments no matter how good the prompt is.

---

## 3. How context pages are selected (the algorithm)

Implemented in `context_loader.build_context_snapshot()`. Three steps per compile call.

### Step 1 — Seeds

Take the **union** of two rules:

| Rule | What it matches | Why |
|---|---|---|
| **(a) Source-match** | Pages whose `source_refs[].source_id == <current source_id>` | If this source previously contributed to a page, the LLM must see that page to emit a continuous updated version. Prevents accidental overwrites. |
| **(b) Token-match** | Pages whose `slug` appears as a **whole-word token** in the source text (case-insensitive) | If the current source mentions a concept by name, that concept's existing page is relevant context. |

**Whole-word matching detail** — hyphens count as connectors, not boundaries. So the slug `self-attention` matches in `"…uses self-attention to…"` at word edges, but the slug `attention` will NOT match inside `self-attention`. Without this rule, every hyphenated slug would noisily match its sub-terms (a `reinforcement-learning` source would pull in `reinforcement` and `learning` as separate concepts).

### Step 2 — Depth-1 expansion

For every seed, look up its `outgoing_links[]` and add those target pages. Gives the LLM one hop of semantic neighborhood around the matched seeds.

### Step 3 — Order, dedupe, cap

1. Sort seeds alphabetically by slug.
2. Append depth-1 pages, sorted alphabetically by slug (seeds excluded).
3. First-seen wins on duplicates.
4. Truncate to `page_cap` (default **50**).

**Why seeds first?** So the truncation drops depth-1 overflow before it drops seeds. Seeds are always the most directly relevant; neighborhood is a bonus.

---

## 4. The cold-start case — EP1 on 2026-04-20

When we compiled `KDB/raw/EP1 - The Journey of China.md`, the context snapshot came back **empty** (0 pages). Why:

| Rule | Evaluation | Result |
|---|---|---|
| (a) Source-match | EP1 had never compiled before → no page in manifest has EP1 in `source_refs[]` | 0 matches |
| (b) Token-match | The only previously compiled sources were `CODEBASE_OVERVIEW.md` (code docs) and a Buffett interview (finance). Their slugs — `manifest-schema`, `margin-of-safety`, `patch-applier`, etc. — don't appear as tokens in a document about Chinese dynasties. | 0 matches |

So seeds = ∅ → depth-1 = ∅ → snapshot has zero pages.

**Consequence:** the LLM compiled EP1 with no prior ontology to anchor to. This is an expected cold-start signature for any domain that's semantically disjoint from what's already in the KB. It's also a meaningful data point for the `ruling-by-law` drift we observed on that run: any drift came purely from inside the source — there was no prior slug the model could have reused correctly.

**Mitigation (later):** once a few more China-adjacent sources are compiled, subsequent compiles in that domain will find seeds by token-match. The ontology self-bootstraps after the first ~2–3 sources in a new domain cluster.

---

## 5. What a non-empty snapshot looks like

Imagine EP1 has already compiled successfully, and you're now compiling **EP2 — The Journey of India** for the first time. The selection would probably fire like this:

- **(b) Token-match seeds:** `confucianism`, `dynastic-legitimacy`, `ruling-by-law`, `meritocracy` — if those words appear in EP2 (they likely do in a parallel-civilization analysis)
- **Depth-1 expansion:** the concepts those seeds link to — `legalism`, `civil-service-exam`, `filial-piety`, `ruling-by-rights`
- **Sibling summary:** `ep1-the-journey-of-china` (summary page) gets pulled in too, because it's a seed's outgoing-link target

Rendered:

```json
{
  "source_id": "KDB/raw/EP2 - The Journey of India.md",
  "pages": [
    { "slug": "confucianism",
      "title": "Confucianism",
      "page_type": "concept",
      "outgoing_links": ["ruling-by-rights", "meritocracy", "filial-piety"] },
    { "slug": "dynastic-legitimacy",
      "title": "Dynastic Legitimacy",
      "page_type": "concept",
      "outgoing_links": ["mandate-of-heaven", "ruling-by-law"] },
    { "slug": "ep1-the-journey-of-china",
      "title": "The Journey of China (summary)",
      "page_type": "summary",
      "outgoing_links": ["ruling-by-law", "confucianism", "dynastic-legitimacy"] },
    { "slug": "ruling-by-law",
      "title": "Ruling by Law",
      "page_type": "concept",
      "outgoing_links": ["confucianism", "legalism", "dynastic-legitimacy"] },
    ...
  ]
}
```

Now when the LLM goes to emit EP2's take on Indian dynastic authority, it can:
1. **Link to existing slugs** where the concept is shared (`[[ruling-by-law]]`)
2. **Mint a sibling** with explicit cross-reference if parallel-but-distinct (`divine-right-indian` with a `See also: [[ruling-by-law]]` in the body)
3. **Integrate** rather than duplicate — EP1's cluster is visible, so EP2's cluster is built in relation to it

That's the compounding loop working.

---

## 6. Design constraints worth remembering

| Constraint | Where | Why |
|---|---|---|
| **No bodies in context pages** | `ContextPage` dataclass (`types.py`) | D8: LLM sees logical intent only. Passing bodies would balloon token counts and tempt the model to copy existing prose instead of synthesizing. |
| **`page_cap=50` default** | `context_loader.build_context_snapshot` | Token budget for context shouldn't dominate the prompt. At 50 pages × ~80 bytes each = ~4KB of context, leaving headroom for the source text and schema. |
| **Whole-word token matching with hyphen-as-connector** | `context_loader` (regex lookarounds) | Prevents false positives on hyphenated slug substrings. |
| **Seeds sorted alphabetically before truncation** | `context_loader` | Deterministic ordering — same manifest + source → same snapshot, byte-for-byte. Matters for `prompt_hash` reproducibility. |

---

## 7. Pointers

- **Code:** `kdb_compiler/context_loader.py` (selection algorithm), `kdb_compiler/prompt_builder.py` (assembly into user prompt), `kdb_compiler/types.py:260–281` (`ContextPage` / `ContextSnapshot`)
- **Full prompt example:** `docs/example-prompt-ep1-china.md` (cold-start, 0 context pages)
- **Wiki design rationale:** `docs/wiki.md`
- **Decision ledger:** `docs/CODEBASE_OVERVIEW.md` §7 (D8 is the relevant entry)

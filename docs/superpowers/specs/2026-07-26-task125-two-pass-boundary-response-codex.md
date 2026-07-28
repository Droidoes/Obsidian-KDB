# Task #125 Formal Architecture Response — Codex

**Date:** 2026-07-26  
**Reviewer:** Codex  
**Review basis:** `2026-07-26-task125-two-pass-boundary-question.md`

## Assessment

**CONCUR-WITH-ITEMS.**

## Direct answer

Pass-1 earns its keep as a separate durable boundary. It owns admission, domain scoping,
authoritative Pass-2 metadata, persistence, auditability, and independent re-selection.

What has not yet earned its keep is the specific ≤4,096-byte metadata projection used as the
selector query. That should be tested independently of whether Pass-1 remains separate.

## Load-bearing findings

### 1. Q1 conflates two independent decisions

- **Boundary:** should enrichment remain independently persisted?
- **Representation:** should search consume metadata, body content, or both?

A body-informed selector does not require merging Pass-1 and Pass-1.5.

### 2. The proposed one-call alternative cannot reproduce #123's ratified search

Final T2 selection is the fat stage, always preceded by thin selection
(`2026-07-25-task123-semantic-graph-search-spec.md:105`). Above M=100, thin output determines which
bodies are hydrated for fat selection.

A merged call receiving only candidate identities performs thin selection, not final T2 selection.
Receiving every candidate body would defeat the M=100 envelope bound. This independently
invalidates "one call," in addition to the domain circularity already identified.

### 3. The byte threshold needs precise wording

The executable guarantee is 283,168 of 320,000 tokens, leaving 36,832.

- Appending the body beside the 4,096-byte projection permits ≤36,832 body bytes.
- Replacing the projection permits ≤40,928 body bytes.

The brief says "substituting" but uses the append threshold. Its broader conclusion remains valid.

### 4. The probe denominators need correction

- The 25 resolvable probes comprise A=18, B=3, C=2, and F=2.
- Only the 23 A/B/C probes exercise selector quality; F01–F02 force an empty space.
- The 14 unresolved probes include D=3, E=5, G=3, and the omitted adversarial H=3.
- The 25 measurements represent 14 unique source documents. Unique-document sizes are median
  29,336 B, mean 36,753 B, maximum 96,311 B.

### 5. The experiment needs a predeclared decision rule

D7's quality thresholds are intentionally diagnostic. Projection-versus-body results therefore
inform Q1 but cannot automatically settle it until Joseph specifies how much quality gain justifies
additional cost, budget failures, or complexity.

## Architectural options

| Option | Architecture | Tradeoff |
|---|---|---|
| A | Preserve Pass-1 and the existing metadata projection | Simplest and most reversible; preserves all ratified contracts, but projection loss remains untested |
| B | Preserve Pass-1; let Pass-1.5 consume a body-informed query | Preserves domain gating, failure isolation, replay, and thin→fat; costs more context and requires a new query-budget policy |
| C | Joint enrichment and selection call | Requires reopening the domain gate, R4 thin→fat staging, attribution wire, failure matrix, and envelope proof; not viable under D1–D9 |

## Recommended disposition

- Ratify the **Pass-1 boundary**, not the current projection.
- Keep Option A as the production baseline while running Option B as an experiment.
- Do not pursue Option C unless Joseph explicitly reopens the affected #123 decisions.
- Run the comparison on the 23 A/B/C probes with identical model, scope, candidates, evidence, M,
  and result cap. Change only `QueryPayload.text`; do not reduce M in the initial arm because that
  would confound query quality with candidate retention.
- Correct the Pass-1 prompt regardless:
  - redefine `entity_search_keys` for semantic selection rather than canonical PK lookup;
  - require literal JSON `null`, never the string `"null"`, for absent authors.

## Confirmation gate

Explicit owner confirmation is required before converting this disposition into Task #125
architecture, task-ledger, or North Star updates.

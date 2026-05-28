# Memory Workflow

This note explains how to use memory for long-term knowledge, instruction, and
style persistence without blurring project documentation, personal knowledge,
and assistant behavior rules.

## Three Memory Tiers

### 1. Project memory

Location: repository docs, especially `docs/CODEBASE_OVERVIEW.md`,
`docs/TASKS.md`, design blueprints, handoff docs, and tutorial files.

Use for:

- architecture decisions;
- task lineage;
- implementation constraints;
- schema contracts;
- recovery procedures;
- anything future contributors should treat as project truth.

Rule: for this repo, project memory is the North Star. If a decision affects
system architecture, it belongs in project docs before it belongs anywhere else.

### 2. Personal knowledge memory

Location: Obsidian vault, especially daily notes and project notes.

Use for:

- session summaries;
- user-level reasoning;
- open questions;
- personal research;
- decisions that matter beyond this repo;
- retrospective lessons.

Rule: Obsidian is the long-term knowledge base. It is broader than the codebase
and can hold context that is not appropriate to commit into the repo.

### 3. Assistant behavior memory

Location: durable assistant memory files, such as Codex memory storage under
`~/.codex/memories/` when we intentionally create them.

Use for:

- stable communication preferences;
- repeated correction patterns;
- durable workflow rules;
- style preferences;
- "do this by default in future sessions" instructions.

Rule: behavior memories should be short, durable, and general. They should not
duplicate project docs or store transient task details.

## Memory Candidate Types

### Knowledge memory

Fact or decision that should be remembered.

Example:

```text
GraphDB-KDB is the live ontology authority; Markdown is a rendering surface.
```

Best home: project docs first; Obsidian if it is part of broader reasoning.

### Instruction memory

Rule for how future assistants should act.

Example:

```text
For Obsidian-KDB work, do not change files outside the agreed scope; if scope is
unclear, confirm before editing.
```

Best home: assistant behavior memory if the rule should persist across sessions.

### Style memory

Preference for tone, structure, terminology, or presentation.

Example:

```text
When introducing graph concepts, start from the user's Obsidian graph mental
model, then explain the typed Kuzu model.
```

Best home: assistant behavior memory, if repeated and stable.

## Proposed Workflow

1. During work, capture possible memory candidates explicitly.
2. Sort each candidate into project, personal, or assistant behavior memory.
3. Ask before writing behavior memory.
4. Keep behavior memories short and testable.
5. Periodically prune or revise memories that have become obsolete.

## What Not To Store

- Temporary implementation details that belong in a task or handoff.
- Secrets, API keys, private credentials, or account data.
- One-off preferences that may not repeat.
- Large explanations copied from docs.
- Anything that would conflict with the current North Star docs.

## Suggested First Memory Candidates

These are candidates only; do not write them without explicit approval.

```text
For Obsidian-KDB explanations, reconcile new concepts against the user's
existing mental model first, then introduce the more formal implementation
model.
```

```text
When the user says "do not change X" in an iterative doc review, preserve the
exact scope: if they restrict changes to a directory, files inside that
directory remain editable.
```

```text
Use "graph-write application" or "graph sync" when describing compiler-to-GraphDB
writes, and reserve "ingestion pipeline" for upstream source-preparation flows.
```

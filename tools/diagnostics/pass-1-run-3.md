# Pass-1 results — run 2026-05-30T15-53-39_EDT

Total scanned sources: **36**
signal: 29 · noise: 7

Pass-1 SOURCE domain distribution (signal sources only):
  - `value-investing`: 9
  - `software`: 7
  - `ai-ml`: 4
  - `health-wellbeing`: 2
  - `math-statistics-logic`: 1
  - `psychology`: 1
  - `neuroscience-cognition`: 1
  - `geopolitics`: 1
  - `quotes`: 1
  - `history`: 1
  - `personal-finance`: 1

> Note: Pass-1 `domain` is a per-SOURCE classification written to the
> `Source.domain` property. It is SEPARATE from Pass-2 per-ENTITY-page
> `domain` (which drives Domain nodes + BELONGS_TO edges). Compare with
> pass-2-run-3.md to see the disconnect.

---

## AIML/Claude/Claude Code Buddy System.md

- **kdb_signal**: `signal`  ·  outcome: `enriched`  ·  confidence: 0.95
- **domain**: `ai-ml`
- **source_type**: `blog`  ·  author: None
- **key_themes**: ['claude-code', 'buddy-system', 'deterministic-generation', 'pet-reroll']
- **entity_search_keys**: ['claude-code', 'claude-code-buddy', 'fnv-1a', 'mulberry32', 'prng', 'legendary-reroll', 'buddy-reroll', 'any-buddy', 'cc-buddy', 'anthropic']
- summary: This document explains the deterministic generation algorithm behind Claude Code's buddy pet system, detailing how identity strings are hashed via FNV-1a and used as seeds for Mulberry32 PRNG to determine pet attributes. It covers rarity tiers, species list, and provides a reroll strategy to obtain legendary pets, including community tools and an execution log.

## AIML/Claude/Claude Desktop Cowork VM -- Service Failed to Start Fix.md

- **kdb_signal**: `signal`  ·  outcome: `enriched`  ·  confidence: 0.95
- **domain**: `ai-ml`
- **source_type**: `documentation`  ·  author: None
- **key_themes**: ['claude-desktop-troubleshooting', 'vm-service-fix', 'hyper-v-reset', 'windows-service-management']
- **entity_search_keys**: ['claude-desktop', 'cowork-vm-service', 'hyper-v', 'windows-11', 'powershell', 'msix', 'vm-bundle']
- summary: Detailed troubleshooting and resolution steps for fixing a Claude Desktop Cowork VM service failure on Windows 11, including cache cleanup, Hyper-V reset, and service re-registration.

## AIML/Claude/cowork-health-report-2026-03-23.md

- **kdb_signal**: `noise`  ·  outcome: `enriched`  ·  confidence: 0.95
- **domain**: `software`
- **source_type**: `other`  ·  author: None
- reject_reason: Operational health-check report with no substantive knowledge content.
- **key_themes**: ['vm-health', 'system-administration']
- **entity_search_keys**: []
- summary: Weekly health check report for a Cowork VM, detailing VM uptime, mounted folder accessibility, a broken symlink, and cache maintenance schedule. All checks passed with minor observations.

## AIML/Graph RAG/GraphRAG for Adaptive KB - GPT5.2.md

- **kdb_signal**: `signal`  ·  outcome: `enriched`  ·  confidence: 0.95
- **domain**: `value-investing`
- **source_type**: `blog`  ·  author: None
- **key_themes**: ['value-investing', 'qualitative-synthesis', 'knowledge-graph', 'delta-first-learning', 'circle-of-competence']
- **entity_search_keys**: ['synthetic-analyst-engine', 'qualitative-alpha', 'scuttlebutt-funnel', 'belief-versioning', 'too-hard-knowledge-base', 'margin-of-safety', 'capital-cycles', 'incentive-alignment']
- summary: The Synthetic Analyst Engine is a headless, AI-augmented research system designed to compound qualitative insight for long-term value investors by operationalizing mental models through a knowledge graph, semantic memory, and delta-first learning. It emphasizes disciplined accumulation, belief versioning, and explicit handling of exclusion criteria to generate sustainable investment alpha from qualitative synthesis rather than quantitative data.

## AIML/Graph RAG/GraphRAG for Adaptive KB - Gemini3.1.md

- **kdb_signal**: `signal`  ·  outcome: `enriched`  ·  confidence: 0.95
- **domain**: `ai-ml`
- **source_type**: `blog`  ·  author: None
- **key_themes**: ['graphrag', 'value-investing', 'knowledge-graph', 'qualitative-research', 'llm-extraction']
- **entity_search_keys**: ['graphrag', 'value-investing', 'knowledge-graph', 'llm-extraction', 'warren-buffett', 'charlie-munger', 'supabase', 'pgvector', 'gmail-api', 'synthetic-munger']
- summary: Describes a proprietary, headless AI-augmented research pipeline for deep value investing that ingests unstructured qualitative data (e.g., Substack newsletters), uses LLM extraction with a Pydantic schema to filter noise and extract structured knowledge, and employs a GraphRAG architecture with PostgreSQL (pgvector) to build a continuously evolving knowledge graph that connects entities, tracks supply chain bottlenecks, and avoids echo chambers by detecting net-new information.

## AIML/Obsidian/Archiving Claude Conv to Obsidian Vault.md

- **kdb_signal**: `signal`  ·  outcome: `enriched`  ·  confidence: 0.95
- **domain**: `ai-ml`
- **source_type**: `documentation`  ·  author: None
- **key_themes**: ['jsonl-parsing', 'obsidian-vault', 'knowledge-base', 'claude-code', 'automation']
- **entity_search_keys**: ['claude-code', 'obsidian', 'jsonl', 'dataview', 'templater', 'python', 'cron', 'knowledge-base', 'automation', 'markdown']
- summary: A guide for converting Claude Code JSONL conversation logs into Obsidian markdown notes, including a Python script, cron job automation, and methods for building a knowledge base using Obsidian features like tags, Dataview, and MOC notes.

## AIML/Obsidian/Callouts.md

- **kdb_signal**: `signal`  ·  outcome: `enriched`  ·  confidence: 0.95
- **domain**: `software`
- **source_type**: `documentation`  ·  author: None
- **key_themes**: ['obsidian-callouts', 'markdown-syntax', 'note-taking-tool']
- **entity_search_keys**: ['obsidian', 'callouts', 'markdown']
- summary: Reference guide listing Obsidian's built-in callout types (e.g., note, info, warning, question) and explaining syntax features such as folding, custom titles, nesting, and custom CSS callouts.

## AIML/Obsidian/Obsidian CLI Skills for Claude Code.md

- **kdb_signal**: `signal`  ·  outcome: `enriched`  ·  confidence: 0.95
- **domain**: `software`
- **source_type**: `documentation`  ·  author: None
- **key_themes**: ['obsidian-cli', 'claude-code-integration', 'daily-notes', 'knowledge-retrieval', 'graph-analysis']
- **entity_search_keys**: ['obsidian', 'claude-code', 'daily-notes', 'knowledge-retrieval', 'graph-analysis', 'singletonlock', 'cold-start', 'grep', 'vault', 'obsidian-ensure']
- summary: A technical reference document detailing four Obsidian CLI skills (shared, daily, recall, graph) for Claude Code integration, including bash command implementations, cold-start handling, and file-based fallbacks.

## AIML/Obsidian/Obsidian CLI Skills.md

- **kdb_signal**: `signal`  ·  outcome: `enriched`  ·  confidence: 0.95
- **domain**: `software`
- **source_type**: `chat-log`  ·  author: None
- **key_themes**: ['obsidian-cli', 'command-line-skills', 'vault-management', 'automation', 'wsl']
- **entity_search_keys**: ['obsidian-cli', 'obsidian', 'wsl', 'command-line-interface', 'vault-automation', 'nvidia', 'tui', 'obsidian-commands']
- summary: A detailed guide to using the official Obsidian CLI, covering command discovery, high-value commands for graph, vault health, daily notes, and automation, with WSL-specific tips and references to official documentation.

## AIML/Programing-Algorithm/Algorithm/Relative Ranking Methods - Borda, Condorcet, and Aggregation.md

- **kdb_signal**: `signal`  ·  outcome: `enriched`  ·  confidence: 0.95
- **domain**: `math-statistics-logic`
- **source_type**: `blog`  ·  author: None
- **key_themes**: ['borda-count', 'condorcet-method', 'preference-aggregation', 'voting-theory']
- **entity_search_keys**: ['borda-count', 'condorcet-method', 'preference-aggregation', 'voting-theory', 'pairwise-comparison', 'majority-rule', 'consensus']
- summary: This document compares Borda count and Condorcet method for aggregating ranked preferences into a single ranking. It explains their mechanics, strengths, weaknesses, and appropriate use cases, highlighting the philosophical difference between consensus-oriented (Borda) and majority-dominance (Condorcet) approaches.

## AIML/Programing-Algorithm/Vibe Coding/Canonical Ontology for Financial Reports GPT5.2.md

- **kdb_signal**: `signal`  ·  outcome: `enriched`  ·  confidence: 0.95
- **domain**: `software`
- **source_type**: `chat-log`  ·  author: None
- **key_themes**: ['financial-data-mapping', 'canonical-ontology', 'etl-pipeline', 'reconciliation-engine', 'ebitda-derivation']
- **entity_search_keys**: ['financial-data-mapping', 'canonical-ontology', 'etl-pipeline', 'reconciliation-engine', 'ebitda-derivation', 'apple', 'canonical-mapper', 'ontology-adapter', 'balance-sheet', 'income-statement']
- summary: This document is a detailed technical conversation about mapping financial statement line items to canonical terms using a deterministic decision tree and ontology. It covers the design of an ETL pipeline, canonical ontology for financial concepts, automatic EBITDA derivation, and a reconciliation engine for validation. The content provides concrete examples using Apple's financial data.

## AIML/Programing-Algorithm/Vibe Coding/VS Code system prompts at different levels.md

- **kdb_signal**: `signal`  ·  outcome: `enriched`  ·  confidence: 0.95
- **domain**: `software`
- **source_type**: `documentation`  ·  author: None
- **key_themes**: ['copilot-architecture', 'instruction-layers', 'custom-agents', 'slash-commands', 'skills']
- **entity_search_keys**: ['vs-code-copilot', 'copilot-architecture', 'instruction-layers', 'global-instructions', 'custom-agents', 'slash-commands', 'skills', 'function-calling', 'decision-matrix', 'project-structure']
- summary: Explains the four-layer architecture of VS Code Copilot for organizing instructions: Global Instructions, Custom Agents, Slash Commands, and Skills. Provides analogies, use cases, and a decision matrix for placement. Includes directory structure implementation reference.

## AIML/Programing-Algorithm/Vibe Coding/Windows-ports-not-visible-WSL-Ubuntu.md

- **kdb_signal**: `signal`  ·  outcome: `enriched`  ·  confidence: 1.0
- **domain**: `software`
- **source_type**: `other`  ·  author: None
- **key_themes**: ['wsl2-port-conflict', 'hyper-v-port-exclusion', 'service-worker-troubleshooting', 'local-development-networking']
- **entity_search_keys**: ['wsl2', 'hyper-v', 'service-worker', 'port-exclusion', 'python-http-server', 'vite', 'react-router']
- summary: Troubleshooting guide for WSL2 port conflicts where Hyper-V reserved ports 8080/8081 and a stale service worker caused 404 errors when serving static files via Python HTTP server. Root cause identified as dual issues: Hyper-V port exclusions and a cached service worker from an old build. Solution: switch to a non-excluded port (8082). Also evaluates mirrored networking mode as insufficient to resolve port exclusions.

## AIML/Programing-Algorithm/Vibe Coding/what's React and Tailwind.md

- **kdb_signal**: `signal`  ·  outcome: `enriched`  ·  confidence: 0.95
- **domain**: `software`
- **source_type**: `article`  ·  author: None
- **key_themes**: ['react', 'tailwind-css', 'frontend-development', 'utility-first-css']
- **entity_search_keys**: ['react', 'tailwind-css', 'jsx', 'virtual-dom', 'utility-first-css', 'frontend-development']
- summary: Explains React as a JavaScript library for building UIs with reusable components and a Virtual DOM, and Tailwind CSS as a utility-first CSS framework. Describes how they are commonly used together for efficient frontend development.

## Daily Notes/2026-05-25.md

- **kdb_signal**: `noise`  ·  outcome: `enriched_force_overridden`  ·  confidence: 0.95
- **domain**: `ai-ml`
- **source_type**: `daily-note`  ·  author: 'Joseph (primary collaborator)'
- reject_reason: deterministic override via force_noise: Daily Notes/*
- **key_themes**: ['ingestion-pipeline', 'domain-classification', 'two-pass-worth-judgment', 'lego-decomposition', 'architectural-decisions']
- **entity_search_keys**: ['ingestion-system', 'two-pass-worth-judgment', 'lego-decomposition', 'domain-canonicalization', 'reviewer-panel', 'joseph', 'kdb-compile', 'orchestrator', 'producer-contract', 'enrichment-component']
- summary: This daily note documents two work sessions on the KDB ingestion system: (1) architectural reframing of the ingestion pipeline into 6 Lego components, ratification of a two-pass worth-judgment mechanism, and decisions on vocabulary, scope, and reviewer findings; (2) development of a 23-domain canonicalization list for content classification, with a 5-reviewer panel, philosophical corrections on edge pre-declaration, and finalization of domain definitions and boundaries.

## Daily Notes/2026-05-26.md

- **kdb_signal**: `noise`  ·  outcome: `enriched_force_overridden`  ·  confidence: 0.95
- **domain**: `ai-ml`
- **source_type**: `daily-note`  ·  author: None
- reject_reason: deterministic override via force_noise: Daily Notes/*
- **key_themes**: ['knowledge-base-enrichment', 'llm-pipeline', 'source-type-vocabulary', 'architectural-pivot', 'entity-search-keys']
- **entity_search_keys**: ['knowledge-base-enrichment', 'llm-pipeline', 'source-type-vocabulary', 'architectural-pivot', 'entity-search-keys', 'consumer-purpose-test', 'pass-1', 'task-89', 'graphdb', 'deepseek-v4-flash']
- summary: Daily note documenting a day of work on KDB project: NW-7 source_type vocabulary ratification, Pass-1 implementation checkpoint, architectural pivot to drop key_entities and add entity_search_keys, closure of Task #89, and deferred tasks. Includes detailed design decisions, bug fixes, and lessons learned.

## Daily Notes/2026-05-27.md

- **kdb_signal**: `noise`  ·  outcome: `enriched_force_overridden`  ·  confidence: 0.95
- **domain**: `software`
- **source_type**: `daily-note`  ·  author: None
- reject_reason: Content is a daily log of work activities, not substantive knowledge worth retaining. It consists of task tracking, implementation details, and progress updates without standalone reusable insights.
- **key_themes**: ['software-development', 'task-tracking', 'daily-log', 'kdb-project']
- **entity_search_keys**: ['kdb', 'task-90', 'task-91', 'codex', 'deepseek', 'panel-review', 'pass-1-prompt', 't2-mode']
- summary: A detailed daily log of work on the KDB project, including task tracking, implementation steps, decisions, and progress on multiple tasks (Task #90, Task #91). The content is primarily workflow and activity logging rather than substantive knowledge.

## Daily Notes/2026-05-28.md

- **kdb_signal**: `noise`  ·  outcome: `enriched_force_overridden`  ·  confidence: 0.95
- **domain**: `software`
- **source_type**: `daily-note`  ·  author: None
- reject_reason: deterministic override via force_noise: Daily Notes/*
- **key_themes**: ['orchestrator-design', 'kdb-system', 'pipeline-architecture', 'compile-scan-graph']
- **entity_search_keys**: ['kdb-orchestrate', 'kdb-compile', 'pipeline-registry', 'graphdb', 'kdb-old-compile', 'kdb-scan', 'kdb-enrich']
- summary: Design session notes for the kdb-orchestrate end-to-end orchestrator, covering architectural decisions, component definitions (feeder, ingestion, compiler, GraphDB), pipeline registry, hash basis, and deferred tasks. Resolves the scan-enrich-compile loop and establishes per-source compilation.

## Life-Health-Wellbeing/Andrew Weil Breath Method.md

- **kdb_signal**: `signal`  ·  outcome: `enriched`  ·  confidence: 0.95
- **domain**: `health-wellbeing`
- **source_type**: `blog`  ·  author: 'Andrew Weil'
- **key_themes**: ['breathing-exercises', 'meditation', 'relaxation', 'mindfulness', 'integrative-medicine']
- **entity_search_keys**: ['andrew-weil', 'breath-counting', '4-7-8-breath', 'breathing-exercises', 'meditation', 'mindfulness', 'relaxation', 'zen']
- summary: The source describes two breathing exercises recommended by Dr. Andrew Weil: Breath Counting for meditation and the 4-7-8 Breath for relaxation, with step-by-step instructions for each.

## Life-Health-Wellbeing/Dan-Koe-How-to-Fix-Your-Entire-Life-in-1-Day.md

- **kdb_signal**: `signal`  ·  outcome: `enriched`  ·  confidence: 0.95
- **domain**: `psychology`
- **source_type**: `blog`  ·  author: 'Dan Koe'
- **key_themes**: ['behavior-change', 'identity-transformation', 'goal-setting', 'ego-development', 'productivity']
- **entity_search_keys**: ['behavior-change', 'identity-transformation', 'goal-setting', 'ego-development', 'cybernetics', 'dan-koe', 'alfred-adler', 'maxwell-maltz', 'naval-ravikant']
- summary: A comprehensive guide on behavior change, identity transformation, and goal setting. Covers why resolutions fail, stages of ego development, intelligence as cybernetic goal-seeking, and a one-day protocol to overhaul one's life.

## Life-Health-Wellbeing/How Not to Age.md

- **kdb_signal**: `signal`  ·  outcome: `enriched`  ·  confidence: 0.95
- **domain**: `health-wellbeing`
- **source_type**: `transcript-video`  ·  author: 'Dr. Michael Greger'
- **key_themes**: ['anti-aging', 'autophagy', 'spermidine', 'plant-based-diet', 'longevity']
- **entity_search_keys**: ['michael-greger', 'autophagy', 'spermidine', 'plant-based-diet', 'blue-zones', 'aging', 'longevity', 'nutritionfacts-org']
- summary: Dr. Michael Greger presents evidence-based strategies for slowing aging and promoting longevity, focusing on diet (plant-based, whole foods), exercise, and lifestyle habits, with specific emphasis on autophagy, spermidine, and other anti-aging mechanisms.

## Life-Health-Wellbeing/Sleep and Aging - Research on Aging.md

- **kdb_signal**: `signal`  ·  outcome: `enriched`  ·  confidence: 0.9
- **domain**: `neuroscience-cognition`
- **source_type**: `transcript-lecture`  ·  author: None
- **key_themes**: ['sleep-and-aging', 'sleep-physiology', 'sleep-disorders', 'memory-consolidation', 'circadian-rhythm']
- **entity_search_keys**: ['sleep-and-aging', 'sleep-physiology', 'sleep-disorders', 'memory-consolidation', 'circadian-rhythm', 'suprachiasmatic-nucleus', 'cbti', 'cpap', 'melatonin', 'rem-sleep-behavior-disorder']
- summary: This lecture transcript covers the science of sleep and aging, including sleep stages, the importance of sleep for memory consolidation and cardiovascular health, changes in sleep architecture with age, and common sleep disorders in the elderly such as obstructive sleep apnea, insomnia, advanced sleep phase syndrome, and REM sleep behavior disorder.

## NWO/rare-earth-trucks-to-hormuz-leverage.md

- **kdb_signal**: `signal`  ·  outcome: `enriched`  ·  confidence: 0.95
- **domain**: `geopolitics`
- **source_type**: `blog`  ·  author: 'Grok (xAI)'
- **key_themes**: ['rare-earth-supply-chain', 'us-china-leverage', 'myanmar-mining', 'iran-oil-tankers', 'hormuz-strategy']
- **entity_search_keys**: ['myanmar', 'rare-earth', 'kia', 'us-china', 'iran', 'hormuz', 'trump', 'xi-jinping', 'operation-epic-fury', 'geopolitical-leverage']
- summary: This document analyzes the geopolitical leverage between the US and China, focusing on rare earth supply chains from Myanmar, the US-Iran war, and the strategic constraints on both sides. It concludes that China holds the upper hand due to its monopoly on rare earth processing and resilient oil supply routes.

## Quotes/Quotes from Napoleon.md

- **kdb_signal**: `signal`  ·  outcome: `enriched`  ·  confidence: 0.95
- **domain**: `quotes`
- **source_type**: `post`  ·  author: None
- **key_themes**: ['aphorisms', 'wisdom', 'leadership', 'war', 'human-nature']
- **entity_search_keys**: ['napoleon-bonaparte', 'aphorisms', 'quotations', 'leadership', 'war']
- summary: A collection of 71 standalone quotes, many attributed to Napoleon Bonaparte, covering themes of leadership, war, human nature, and wisdom.

## Quotes/The Strong Do What They Can.md

- **kdb_signal**: `signal`  ·  outcome: `enriched`  ·  confidence: 0.95
- **domain**: `history`
- **source_type**: `chat-log`  ·  author: None
- **key_themes**: ['ancient-greek-history', 'peloponnesian-war', 'thucydides', 'melian-dialogue', 'realpolitik']
- **entity_search_keys**: ['thucydides', 'melian-dialogue', 'peloponnesian-war', 'realpolitik', 'history-of-the-peloponnesian-war', 'richard-crawley', 'rex-warner']
- summary: The source provides multiple English translations and original context of Thucydides' famous phrase 'the strong do what they can and the weak suffer what they must' from the Melian Dialogue, explaining its realpolitik theme.

## Value Investing/Accounting/Buffet style ROE discussion with Gemini 3.md

- **kdb_signal**: `signal`  ·  outcome: `enriched`  ·  confidence: 0.95
- **domain**: `value-investing`
- **source_type**: `chat-log`  ·  author: 'Gemini'
- **key_themes**: ['value-investing', 'owner-earnings', 'return-on-equity', 'depreciation', 'amortization']
- **entity_search_keys**: ['value-investing', 'owner-earnings', 'return-on-equity', 'depreciation', 'amortization', 'warren-buffett', 'free-cash-flow', 'adjusted-earnings', 'book-value', 'tangible-net-assets']
- summary: A Q&A conversation explaining Warren Buffett's preferred financial metrics for evaluating companies, including ROE, Owner Earnings, and adjustments for depreciation and amortization. It clarifies accounting concepts like net income, reported earnings, and the distinction between cash and non-cash expenses.

## Value Investing/Accounting/Negative cash-conversion cycle.md

- **kdb_signal**: `signal`  ·  outcome: `enriched`  ·  confidence: 0.95
- **domain**: `personal-finance`
- **source_type**: `blog`  ·  author: None
- **key_themes**: ['cash-conversion-cycle', 'working-capital-management', 'days-inventory-outstanding', 'days-sales-outstanding', 'days-payable-outstanding']
- **entity_search_keys**: ['cash-conversion-cycle', 'working-capital-management', 'days-inventory-outstanding', 'days-sales-outstanding', 'days-payable-outstanding', 'negative-ccc', 'amazon']
- summary: Explains the cash conversion cycle (CCC) metric, its formula (DIO+DSO-DPO), the concept of a negative CCC as interest-free financing, and its implications for working capital management, using Amazon as an example.

## Value Investing/Accounting/Warren Buffett - How To Analyze a BALANCE SHEET.md

- **kdb_signal**: `signal`  ·  outcome: `enriched`  ·  confidence: 0.95
- **domain**: `value-investing`
- **source_type**: `transcript-video`  ·  author: 'Brian Feroldi'
- **key_themes**: ['balance-sheet-analysis', 'financial-ratios', 'stock-buybacks', 'financial-statements']
- **entity_search_keys**: ['warren-buffett', 'balance-sheet', 'debt-to-equity-ratio', 'preferred-stock', 'retained-earnings', 'treasury-stock', 'chipotle', 'value-investing', 'financial-statements', 'stock-buybacks']
- summary: Warren Buffett's five balance sheet rules of thumb are explained: cash vs. debt (more cash than debt), debt-to-equity ratio below 0.8, no preferred stock, growing retained earnings, and positive treasury stock. These rules are applied to Chipotle's balance sheet, showing how each rule is evaluated.

## Value Investing/Buffett Munger/Berkshire Hathaway Annual shareholder meeting - 2023.md

- **kdb_signal**: `noise`  ·  outcome: `enriched`  ·  confidence: 1.0
- **domain**: `undecided`
- **source_type**: `other`  ·  author: None
- reject_reason: Content consists only of image embeddings with no accompanying text; cannot extract substantive knowledge.
- **key_themes**: []
- **entity_search_keys**: []
- summary: 

## Value Investing/Buffett Munger/Warren Buffett Brian Moynihan -Speak at Georgetown.md

- **kdb_signal**: `signal`  ·  outcome: `enriched`  ·  confidence: 0.95
- **domain**: `value-investing`
- **source_type**: `interview`  ·  author: 'Warren Buffett'
- **key_themes**: ['value-investing', 'philanthropy', 'income-inequality', 'economic-outlook']
- **entity_search_keys**: ['warren-buffett', 'brian-moynihan', 'value-investing', 'philanthropy', 'giving-pledge', 'gate-foundation', 'economic-panic', 'circle-of-competence', 'ben-graham', 'intelligent-investor']
- summary: A transcribed conversation between Warren Buffett and Bank of America CEO Brian Moynihan at Georgetown University, covering Buffett's investment philosophy, views on the economy, income inequality, philanthropy (including the Giving Pledge and the Gates Foundation), and advice for investors. Includes student Q&A on stock tips, derivatives, and evaluating new business models.

## Value Investing/Buffett Munger/Warren Buffett On Arbitrage.md

- **kdb_signal**: `noise`  ·  outcome: `enriched`  ·  confidence: 1.0
- **domain**: `undecided`
- **source_type**: `other`  ·  author: None
- reject_reason: Empty content: only an image embed with no textual substance.
- **key_themes**: []
- **entity_search_keys**: []
- summary: The source is an empty note containing only an embedded image reference with no explanatory text or substantive content.

## Value Investing/Li Lu/Li Lu 2021 Enoch Wealth Institute Lecture.md

- **kdb_signal**: `signal`  ·  outcome: `enriched`  ·  confidence: 0.95
- **domain**: `value-investing`
- **source_type**: `interview`  ·  author: 'Li Lu'
- **key_themes**: ['value-investing', 'competitive-advantage', 'margin-of-safety', 'compound-interest', 'globalization']
- **entity_search_keys**: ['value-investing', 'competitive-advantage', 'margin-of-safety', 'compound-interest', 'globalization', 'li-lu', 'warren-buffett', 'charlie-munger', 'berkshire-hathaway']
- summary: Li Lu discusses the challenges and contributions of globalization, emphasizing the need for rational leadership among major economies. He shares his value investing philosophy, focusing on competitive advantage, margin of safety, and the power of compound interest. He also offers advice on wealth management, fund manager selection, and maintaining a positive mindset.

## Value Investing/Li Lu/Li Lu Lecture at Columbia Business School 2006.md

- **kdb_signal**: `signal`  ·  outcome: `enriched`  ·  confidence: 0.95
- **domain**: `value-investing`
- **source_type**: `transcript-lecture`  ·  author: 'Li Lu'
- **key_themes**: ['value-investing', 'margin-of-safety', 'business-owner-mentality', 'case-study-analysis', 'deep-due-diligence']
- **entity_search_keys**: ['li-lu', 'bruce-greenwald', 'warren-buffett', 'charlie-munger', 'ben-graham', 'timberland', 'hyundai-department-store', 'value-investing', 'margin-of-safety', 'mr-market']
- summary: Li Lu, a successful value investor, delivers a lecture at Columbia Business School in 2006. He defines value investing through Ben Graham's principles—business ownership mentality, margin of safety, and long-term focus—and discusses the emotional and institutional challenges that make it a minority approach. Through case studies on Timberland and Hyundai Department Store, he illustrates his research process, which includes deep due diligence, investigative work, and a focus on hidden assets. He emphasizes the need for intense curiosity, self-awareness, and the discipline to act on rare, high-conviction insights for outsized returns.

## Value Investing/Monish Pabrai/How share BUYBACKS can 10x - Boston College 2022.md

- **kdb_signal**: `signal`  ·  outcome: `enriched`  ·  confidence: 0.95
- **domain**: `value-investing`
- **source_type**: `transcript-lecture`  ·  author: 'Mohnish Pabrai'
- **key_themes**: ['uber-cannibals', 'share-buybacks', 'capital-allocation', 'value-investing', 'henry-singleton']
- **entity_search_keys**: ['mohnish-pabrai', 'uber-cannibals', 'share-buybacks', 'capital-allocation', 'value-investing', 'henry-singleton', 'teledyne', 'nvr', 'autozone', 'warren-buffett']
- summary: Mohnish Pabrai presents the 'Uber Cannibals' investing framework, focusing on companies that aggressively buy back their own shares. He provides historical examples like NVR and AutoZone, discusses the formula for returns from buybacks, and emphasizes the importance of stable or growing earnings and avoiding secular decline. He also covers the case of Henry Singleton and Teledyne, and in the Q&A touches on capital allocation, philanthropy, mental models, and investing in global markets.

## Value Investing/Monish Pabrai/Pabrai interview - August 2025 - 3.md

- **kdb_signal**: `signal`  ·  outcome: `enriched`  ·  confidence: 0.95
- **domain**: `value-investing`
- **source_type**: `interview`  ·  author: 'Mohnish Pabrai'
- **key_themes**: ['dhandho-investing', 'mental-models', 'cloning', 'compounding', 'entrepreneurship']
- **entity_search_keys**: ['dhandho-investing', 'mental-models', 'cloning', 'compounding', 'entrepreneurship', 'mohnish-pabrai', 'value-investing', 'heads-i-win', 'circle-of-competence', 'rule-of-72']
- summary: Interview with Mohnish Pabrai covering his Dhandho investment philosophy, mental models for business (cloning, risk minimization, low-hanging fruit), the power of compounding and index investing, and principles for entrepreneurship such as heads I win, tails I don't lose much.

## Value Investing/Monish Pabrai/Pabrai on Investing -Buffett - Life Lessons 2025.md

- **kdb_signal**: `signal`  ·  outcome: `enriched`  ·  confidence: 1.0
- **domain**: `value-investing`
- **source_type**: `interview`  ·  author: 'Mohnish Pabrai'
- **key_themes**: ['inner-scorecard', 'value-investing', 'patience', 'leverage', 'stoicism']
- **entity_search_keys**: ['inner-scorecard', 'value-investing', 'patience', 'leverage', 'stoicism', 'mohnish-pabrai', 'warren-buffett', 'charlie-munger', 'marcus-aurelius', 'reysas']
- summary: In an interview, Mohnish Pabrai discusses his investment philosophy, lessons from Warren Buffett and Charlie Munger, the importance of an inner scorecard, patience, avoiding leverage, and the concept of life as a game, along with practical advice on value investing and parenting.

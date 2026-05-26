# Task #89 v0.1 Architecture Review — Gemini

## Convergence
This review recognizes the architectural soundness of the v0.1 blueprint in several core areas:
- **Filesystem-Native Focus**: Keeping Pass-1 purely filesystem-native and keeping compilation as the sole GraphDB producer in v1 aligns perfectly with the concrete-first engineering philosophy.
- **Binary Classification with Calibration Audit**: Emitting a binary `kdb_signal` routing verdict while capturing `confidence`, `uncertainty_reason`, and `reject_reason` provides both operational simplicity and excellent offline auditability.
- **Path-Based Glob Exclusions**: Utilizing a general-purpose dir-exclusion configuration for circularity guards and defense-in-depth ensures a clean boundary without overloading the LLM.

## Findings

### F-1: User-Edited Frontmatter Protection Gap
- **Reference**: §3.3 (Re-enrichment merge behavior) and §2.1 (Property definitions)
- **Finding**: The re-enrichment merge logic dictates that during subsequent updates, the "Pass-1 schema fields use new values." However, this creates a clobbering risk for manual user adjustments. If a user manually overrides a standard Pass-1 property (such as changing a misclassified `domain` or correcting an `author` attribution in the Obsidian editor), any subsequent re-enrichment triggered by a content change will silently overwrite the user's manual correction with the LLM's new emission.
- **Recommendation**: Introduce a user-override protection check during re-enrichment. The orchestrator should compare the current frontmatter properties against the corresponding historical values stored in the local replay archive. If the current frontmatter value differs from the previous LLM emission, the system should treat it as a manual user override and preserve it rather than clobbering it.

### F-2: Default Blacklist vs. Intended LLM Evaluation for Daily Notes
- **Reference**: §4.2 (Defaults for v0.1) and D-88-11 (Daily Notes IN scope)
- **Finding**: There is a structural contradiction between the parent blueprint decision D-88-11 and the v0.1 enrichment blueprint's override defaults. D-88-11 explicitly mandates that Daily Notes are NOT excluded at the scope-config level so the LLM can evaluate and enhance them. However, §4.2 lists `Daily Notes/**` under the default `force_noise` blacklist. In §4.3, any file matching `force_noise` gets its signal deterministically overridden to `noise`. Thus, under the current v0.1 config, no Daily Note will ever be processed or enhanced by the LLM; they will all be forced to `noise` deterministically.
- **Recommendation**: Remove `Daily Notes/**` from the default `force_noise` config list to align with D-88-11. Allow the LLM to apply the substance criteria (§8.2) to Daily Notes, and only use `force_noise` for absolute structural exclusions (e.g., templates, tracking files, metadata directories).

### F-3: Replay Archive Path Hierarchy Collision
- **Reference**: §5.3 (Replay archive sidecar) and parent blueprint §3.2.1 (Identity)
- **Finding**: The replay archive uses the file path format `~/Obsidian/KDB/state/ingest_runs/<run_id>/<source_id>.json`. Since `source_id` is defined as a vault-relative path (e.g., `Investing/Buffett-letter-2020`), writing to this path directly requires creating a subfolder structure matching the source's folder hierarchy (e.g., `ingest_runs/<run_id>/Investing/`). If the parent folder does not exist, standard file operations will raise a `FileNotFoundError`.
- **Recommendation**: The reviewer proposes either recursively creating nested folders for path-relative `source_id` keys using an operational utility, or flattening/escaping slashes in the filename (e.g., replacing `/` with `__` to yield `ingest_runs/<run_id>/Investing__Buffett-letter-2020.json`). Flattening the filename is cleaner, avoids empty folder sprawl in run states, and simplifies flat lookup in the run journal.

### F-4: Specificity Tiebreaker in Override Precedence
- **Reference**: §4.4 (Precedence)
- **Finding**: The precedence rule states that "blacklist wins ties" when a file matches both `force_signal` and `force_noise`. While defensive, this blanket rule prevents a user from establishing a broad directory blacklist while whitelisting a specific nested subdirectory or file (for example, blacklisting a broad area like `Projects/**` but whitelisting a single key log file `Projects/Subfolder/KeyNote.md`).
- **Recommendation**: The reviewer recommends that glob specificity (length of the matching pattern or explicit file matching) should act as a tiebreaker before defaulting to a blanket blacklist victory. If the matching whitelist pattern is more specific than the blacklist pattern, the whitelist should prevail.

## Open questions

### OQ-1: Prevention of Infinite Retry Loops on Failure
- **Description**: If a source file consistently fails LLM validation (due to malformed JSON, repeated schema violations, or API timeouts), the orchestrator emits an `enrich_failed` event (§5.2) and aborts the write. Because no valid frontmatter is written, this source remains in an "unenriched" state. On the next watch or run execution, Component #3's trigger will detect the file as unenriched and re-attempt enrichment, causing a continuous loop of expensive API failures.
- **Design Need**: Does the system need a minimal failure frontmatter stamp (e.g., `kdb_signal: noise`, `reject_reason: "repeated schema validation failure"`, and a specific audit tag) to mark the file as processed-but-failed, or a persistent local state cache tracking failed paths and limiting retries?

### OQ-2: User-Added Frontmatter Key Management
- **Description**: §3.3 specifies that during re-enrichment merges, the system parses the existing frontmatter and preserves "user-added keys that aren't in the Pass-1 schema." What happens if a user-added key subsequently becomes a standard field in a newer version of the Pass-1 schema? 
- **Design Need**: Explicit schema migration rules are defined for additive/subtractive schema changes, but a collision resolution policy is needed for when a user's custom key clashes with a newly added standard field.

## Wikilink + corpus_index decision (§6)
The reviewer recommends **Option C' (Frontmatter Wikilinks)**, which is a key variation of Option C.

### Reasoning:
- **Tension Resolution**: The primary trade-off between Options A and C is that Option A provides link materialization directly to the Obsidian graph view but risks file sync/clobbering conflicts by modifying the markdown body, whereas Option C preserves the pristine body but loses the direct Obsidian graph-view benefit.
- **The Obsidian YAML Link Feature**: In modern Obsidian vaults, internal links formatted as strings within YAML frontmatter lists—such as `related_links: ["[[Warren Buffett]]", "[[Berkshire Hathaway]]"]`—are fully indexed by Obsidian. They participate in the graph view, show up in backlinks, and allow standard interactive navigation.
- **Option C' Design**: By defining a dedicated frontmatter array `wikilink_suggestions` populated with standard stringified wikilinks, the system achieves the best of both worlds:
  1. The source body remains entirely untouched, avoiding sync conflict risks and complex markdown boundaries.
  2. The Obsidian graph view and interactive navigation are fully preserved via native frontmatter indexation.
  3. The compile phase can read this structured metadata directly to feed its `LINKS_TO` extraction.
- **Cold-Start Alignment**: For the cold-start phase, Option C' naturally aligns with bootstrap Option (a): process files with an empty `corpus_index` initially (yielding empty suggestions), and let subsequent change-triggered runs organically populate links as other documents' metadata registers.

## Concerns on post-LLM override (§4)
- **Path Separation Logic**: The post-LLM deterministic override architecture correctly keeps the LLM focused entirely on content substance (§4.5), which is a key system design success.
- **Precedence Calibration**: As flagged in F-4, a blunt "blacklist wins" rule violates the principle of user control. If a user explicitly whitelists a specific file using `force_signal`, a broad `force_noise` glob should not override that deliberate choice.
- **Uncertainty Audit Trace**: The use of `confidence` and `uncertainty_reason` is highly robust, but it is important to ensure that if a post-LLM override changes `kdb_signal` from `signal` to `noise`, the `reject_reason` field is populated with the override metadata (e.g., "deterministic path override via force_noise rule X") so that false-reject audits can easily distinguish between LLM-driven noise rejection and path-driven override rejection.

## Concerns on no-GraphDB-writes stance (§10)
- **Architectural Discipline**: Keeping Pass-1 purely filesystem-native and compile as the sole GraphDB producer is an excellent structural design decision. The lessons of `JOURNEY.md` clearly demonstrate the extreme pain of parallel state storage and out-of-sync indexes. Creating a secondary GraphDB writer at this stage would inevitably lead to transaction collisions and schema desynchronization.
- **Deferral Validity**: Deferring Pass-1 as a second producer to v1.1+ is highly recommended. For v1, compiling from enriched files is clean and robust. Since compile already reads the source files, it can trivially import the frontmatter `domain`, `author`, and `summary` properties to enrich its own GraphDB writes, avoiding duplicate execution without requiring Pass-1 to write to KuzuDB.

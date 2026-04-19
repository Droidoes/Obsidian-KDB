"""compiler — per-source LLM compile call. Produces compile_result.json.

M0 stub. Implementation in M2.

Pipeline position:
    kdb_scan -> planner -> [compiler] -> validate -> patch_applier -> manifest_update

Responsibilities:
    * Consume job queue from planner.
    * For each job:
        - Load source content from KDB/raw/.
        - Load KDB/CLAUDE.md (compiler invariants).
        - Load related-context slice from manifest (existing pages, links).
        - Build the per-source prompt (strict, short, scoped).
        - Call call_model_with_retry with json_mode=True.
        - Parse response as compile_result entry.
    * Accumulate all entries into a single KDB/state/compile_result.json.
    * The LLM NEVER writes files. It emits JSON only.

Prompt design principles (per Codex 5.3):
    * One source per prompt (no mega-prompt).
    * Inject only relevant pages as context.
    * Strict output format with schema reminder.
    * Self-check list in prompt (see KDB/CLAUDE.md).
"""


def main() -> None:
    raise NotImplementedError("compiler — scheduled for M2")


if __name__ == "__main__":
    main()

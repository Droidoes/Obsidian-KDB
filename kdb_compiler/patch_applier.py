"""patch_applier — writes markdown files from validated compile_result.json.

M0 stub. Implementation in M2.

Pipeline position:
    kdb_scan -> planner -> compiler -> validate -> [patch_applier] -> manifest_update

Responsibilities:
    * Read KDB/state/compile_result.json (already schema-validated).
    * For each compiled_sources[].pages[]:
        - Resolve page_id to absolute path.
        - Write content_patches[] verbatim to the filesystem, atomically.
        - Use temp + fsync + os.replace + retry/backoff (OneDrive-safe).
    * Update wiki/index.md (merge new entries deterministically).
    * Append run block to wiki/log.md.
    * NEVER writes to KDB/raw/. NEVER writes outside KDB/wiki/.
    * Dry-run mode: print every intended write without executing.

This is where structured JSON becomes markdown on disk. The LLM cannot
corrupt files here because it never touched them.
"""


def main() -> None:
    raise NotImplementedError("patch_applier — scheduled for M2")


if __name__ == "__main__":
    main()

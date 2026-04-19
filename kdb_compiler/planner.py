"""planner — chunks last_scan.json into compile job queue.

M0 stub. Implementation in M2.

Pipeline position:
    kdb_scan -> [planner] -> compiler -> validate -> patch_applier -> manifest_update

Responsibilities:
    * Read last_scan.json.
    * Chunk to_compile[] into batches (default: 10-20 sources per batch).
    * For each source, prepare the "related context" slice from manifest.json:
        - existing summary page (if any)
        - incoming/outgoing links from existing pages
        - this is what the LLM sees as "world state" during compile
    * Emit a job queue (in-memory or file) consumed by compiler.py.

Note: chunk size is a heuristic. Validate empirically during M2 first compile.
"""


def main() -> None:
    raise NotImplementedError("planner — scheduled for M2")


if __name__ == "__main__":
    main()

"""manifest_update — applies compile_result.json to manifest.json atomically.

M0 stub. Implementation in M1 ports Codex 5.3's reference implementation verbatim.

Pipeline position:
    kdb_scan -> planner -> compiler -> validate -> patch_applier -> [manifest_update]

Responsibilities:
    * Read manifest.json, last_scan.json, compile_result.json.
    * Apply MOVED/DELETED reconciliation from scan (tombstones, page ref updates).
    * Apply compiled_sources[] payloads (sources{}, pages{} entries).
    * Mark orphan_candidate pages when all supporting sources are deleted.
    * Preserve per-source previous_versions[] history (cap at 20).
    * Update stats, run pointers, timestamps.
    * Journal-then-pointer: write runs/<run_id>.json FIRST, then update manifest.json.
    * Atomic write: temp + fsync + os.replace + 6-retry exponential backoff.
    * Single-writer lock (manifest.lock) to serialize concurrent runs.

Inputs:
    KDB/state/manifest.json
    KDB/state/last_scan.json
    KDB/state/compile_result.json   (must have passed validate_compile_result)

Output:
    KDB/state/runs/<run_id>.json    (journal, written first)
    KDB/state/manifest.json         (ledger, written last, atomically)
"""


def main() -> None:
    raise NotImplementedError("manifest_update.main — scheduled for M1")


if __name__ == "__main__":
    main()

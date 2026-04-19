"""kdb_scan — deterministic scan of KDB/raw/, emits state/last_scan.json.

M0 stub. Implementation arrives in M1.

Pipeline position:
    [kdb_scan] -> planner -> compiler -> validate -> patch_applier -> manifest_update

Responsibilities (per Codex 5.3 hardening):
    * Walk KDB/raw/ recursively; skip symlinks by default.
    * Classify each file: is_binary flag via extension + byte sniff.
    * Compute SHA-256 content hash (authoritative); mtime advisory only.
    * Compare against KDB/state/manifest.json sources{} to build delta.
    * Two-pass rename detection: match by hash before NEW/DELETED classification.
    * Emit to_compile[], to_reconcile[] (MOVED, DELETED).
    * Atomic write: temp file in same dir -> flush -> fsync -> os.replace.

Inputs:
    KDB/raw/**                    (source files)
    KDB/state/manifest.json       (prior state; may be empty shape)

Output:
    KDB/state/last_scan.json      (authoritative scan artifact for this run)
"""


def main() -> None:
    raise NotImplementedError("kdb_scan.main — scheduled for M1")


if __name__ == "__main__":
    main()

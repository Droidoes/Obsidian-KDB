"""atomic_io — minimal atomic file writes. Shared by scan / patch_applier / manifest_update.

M0.1 stub. Implementation in M1.

Design philosophy (D22): no complexity for imaginary risk.
This is a SINGLE-USER, SINGLE-PROCESS system. We are not defending against
concurrent writers, high-contention I/O, or multi-tenant scenarios. Any
individual file's corruption is recoverable by re-compile. Keep cheap
insurance only.

What this module does:
    * atomic_write_bytes(path, data) — temp file in same dir, fsync, os.replace.
    * atomic_write_json(path, obj)    — serialize then atomic_write_bytes.
    * atomic_write_text(path, text)   — encode then atomic_write_bytes.
    * Transient I/O retry: up to 2 attempts, 100ms backoff. No exponential
      ladder, no Retry-After headers, no provider-specific classification.
    * Fails loudly after 2 tries. A failed write is OK — the run aborts,
      nothing downstream touches state, user re-runs the compile.

What this module DOES NOT do:
    * Lock files. Not needed (one user, one process). Dropped from Codex
      hardening proposal per D14.
    * Journal/rollback for cross-file transactions. Not needed — manifest_update
      uses journal-then-pointer at a higher level (D15), which is sufficient.
    * Parent-directory fsync. Overkill for a desktop workload backed by OneDrive.

Public surface:
    atomic_write_bytes(path: Path, data: bytes) -> None
    atomic_write_text(path: Path, text: str) -> None
    atomic_write_json(path: Path, obj: dict | list, indent: int = 2) -> None
"""


def main() -> None:
    raise NotImplementedError("atomic_io — scheduled for M1")


if __name__ == "__main__":
    main()

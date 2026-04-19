"""atomic_io — minimal atomic file writes.

Design philosophy (D22): no complexity for imaginary risk.
Single-user, single-process workload. We do not defend against concurrent
writers, high-contention I/O, or multi-tenant scenarios. Cheap insurance only.

Contract:
    atomic_write_bytes(path, data)          — temp + fsync + os.replace
    atomic_write_text(path, text, encoding) — encode then atomic_write_bytes
    atomic_write_json(path, obj, indent)    — serialize then atomic_write_text

A failed write raises. Nothing downstream should touch state on failure; the
user re-runs the compile. No lock files, no exponential backoff ladders,
no multi-phase commits. One retry on transient I/O, then give up.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

_TRANSIENT_RETRY = 1      # one retry then raise — per D14/D22
_RETRY_DELAY_SEC = 0.1


def atomic_write_bytes(path: Path | str, data: bytes) -> None:
    """Atomic write: temp in same dir -> fsync -> os.replace. One retry."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.parent / f".{target.name}.tmp-{os.getpid()}"

    last_exc: Exception | None = None
    for attempt in range(1 + _TRANSIENT_RETRY):
        try:
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
            try:
                os.write(fd, data)
                os.fsync(fd)
            finally:
                os.close(fd)
            os.replace(tmp, target)
            return
        except OSError as exc:
            last_exc = exc
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            if attempt < _TRANSIENT_RETRY:
                time.sleep(_RETRY_DELAY_SEC)
    assert last_exc is not None
    raise last_exc


def atomic_write_text(path: Path | str, text: str, *, encoding: str = "utf-8") -> None:
    atomic_write_bytes(path, text.encode(encoding))


def atomic_write_json(path: Path | str, obj: Any, *, indent: int = 2, sort_keys: bool = False) -> None:
    """Serialize to JSON and write atomically. Trailing newline appended."""
    text = json.dumps(obj, indent=indent, ensure_ascii=False, sort_keys=sort_keys) + "\n"
    atomic_write_text(path, text)


def main() -> None:  # pragma: no cover
    raise SystemExit("atomic_io is a library module; not meant to be run directly.")


if __name__ == "__main__":
    main()

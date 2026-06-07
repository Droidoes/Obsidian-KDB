"""version — best-effort git release identifier for run provenance.

`git describe --tags --dirty --always` yields the nearest semver tag (e.g.
`v0.5.4`), `v0.5.4-3-g<sha>` off-tag, a `-dirty` suffix when the working tree
has uncommitted changes (so a benchmark run is never silently mislabeled as a
clean release), or a bare short-sha / "unknown" when git is unavailable.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent


def release_version() -> str:
    try:
        out = subprocess.run(
            ["git", "describe", "--tags", "--dirty", "--always"],
            cwd=_REPO_ROOT, capture_output=True, text=True, timeout=5,
        )
        v = out.stdout.strip()
        return v or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"

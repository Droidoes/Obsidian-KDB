"""Behavioral verification of the #123 D7 probe-adjudication reviewer.

`test_task123_probe_adjudicator.py` asserts the page's *structure* — no external
assets, the pinned artifact paths, the presence of `buildExportArtifact` and
friends. None of that is behavior. Three failure modes it structurally cannot
catch, all of which would leave the page loading cleanly:

  1. excerpt paths that resolve to nothing (the layout is three `page_type`
     subdirectories; the structural test pins only the `excerpts/` prefix), so
     every candidate card renders with an empty excerpt;
  2. `validateExport` that exists but does not block an incomplete adjudication;
  3. an export that drops a probe or writes the wrong assignment key — into
     `task123_search_probes_v1.json`, the artifact gating D7 and all of P5a.

So this runs the page's own closure headlessly against the real tracked
artifacts. The page is not modified: its inline script is extracted, the
closure's tail is replaced with an export of its internals, and the assertions
live in the tracked sibling `task123_adjudicator_smoke.mjs`.

Skipped where no node runtime exists — the reviewer is temporary owner tooling,
not a runtime dependency, so it must not make node a hard requirement of the
Python suite.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
REVIEWER = REPO_ROOT / "tools" / "task123_probe_adjudicator.html"
SMOKE = Path(__file__).parent / "task123_adjudicator_smoke.mjs"

# The closure's tail. Replaced by an export of its internals so the smoke can
# drive them. A structural change to the page breaks this loudly rather than
# silently skipping the behavioral checks.
CLOSURE_TAIL = "      start();\n    })();"

CLOSURE_EXPORT = """      globalThis.__reviewer = {
        data, PATHS, loadData, frozenExcerpt, validateExport, buildExportArtifact,
        assignCandidate, labelsForProbe, isSpecialProbe, candidateSlugs,
        eligibleIdentities, defaultState, getState: () => state,
      };
    })();"""

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="no node runtime; the reviewer is owner tooling, not a dependency"
)


def _inline_script() -> str:
    text = REVIEWER.read_text(encoding="utf-8")
    match = re.search(r"<script>\n(.*)\n  </script>", text, re.DOTALL)
    assert match, "the reviewer's inline script block was not found"
    return match.group(1)


def test_inline_script_is_syntactically_valid(tmp_path: Path) -> None:
    script = tmp_path / "reviewer.js"
    script.write_text(_inline_script(), encoding="utf-8")
    subprocess.run(["node", "--check", str(script)], check=True, capture_output=True)


def test_reviewer_loads_the_frozen_artifacts_and_exports_a_faithful_truth_set(
    tmp_path: Path,
) -> None:
    script = _inline_script()
    assert CLOSURE_TAIL in script, (
        "the reviewer's closure tail changed; update CLOSURE_TAIL/CLOSURE_EXPORT so the "
        "behavioral smoke keeps running instead of silently going stale"
    )
    harness = tmp_path / "harness.js"
    harness.write_text(script.replace(CLOSURE_TAIL, CLOSURE_EXPORT), encoding="utf-8")

    result = subprocess.run(
        ["node", str(SMOKE), str(harness), str(REPO_ROOT)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    assert "SMOKE PASSED" in result.stdout

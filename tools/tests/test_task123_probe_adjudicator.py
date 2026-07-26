from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
REVIEWER = REPO_ROOT / "tools" / "task123_probe_adjudicator.html"


class _AssetParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.external_assets: list[tuple[str, str, str]] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        for name, value in attrs:
            if name in {"src", "href"} and value and re.match(
                r"^(?:https?:)?//", value
            ):
                self.external_assets.append((tag, name, value))


def _reviewer_text() -> str:
    return REVIEWER.read_text(encoding="utf-8")


def test_reviewer_is_dependency_free_and_network_independent() -> None:
    text = _reviewer_text()
    parser = _AssetParser()
    parser.feed(text)

    assert parser.external_assets == []
    assert re.search(r"https?://", text) is None
    assert "<script src=" not in text


def test_reviewer_pins_the_frozen_task123_inputs() -> None:
    text = _reviewer_text()

    for path in (
        "benchmark/truth/task123_search_probes_draft_v1.json",
        "benchmark/truth/task123_search_adversarial_v1.json",
        "benchmark/truth/task123_search_snapshot_v1/identities.json",
        "benchmark/truth/task123_search_snapshot_v1/manifest.json",
        "benchmark/truth/task123_search_snapshot_v1/excerpts/",
    ):
        assert path in text


def test_reviewer_contains_the_agreed_workflow_and_safe_export_contract() -> None:
    text = _reviewer_text()

    for element_id in (
        'id="instructions-panel"',
        'id="probe-panel"',
        'id="gates-panel"',
        'id="export-panel"',
    ):
        assert element_id in text

    for assignment in ("relevant", "acceptable", "neither"):
        assert f'data-assignment="{assignment}"' in text

    assert "task123-d7-adjudication-reviewer-v1" in text
    assert "task123_search_probes_v1.json" in text
    assert "adjudication_version" in text
    assert 'artifact.adjudicator = "joseph"' in text
    assert 'probe.adjudicator = "joseph"' in text
    assert "localStorage" in text
    assert "buildExportArtifact" in text
    assert "validateExport" in text


def test_reviewer_never_uses_a_repository_write_endpoint() -> None:
    text = _reviewer_text()

    assert re.search(r"fetch\([^)]*,\s*\{[^}]*method\s*:", text, re.DOTALL) is None
    assert re.search(r"\b(?:POST|PUT|PATCH|DELETE)\b", text) is None

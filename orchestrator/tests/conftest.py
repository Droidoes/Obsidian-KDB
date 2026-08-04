"""orchestrator tests — package-wide seams.

#123 P3a.2b: run() now threads a run-level pass-1.5 selector seat into every
compile_source, and e2e tests exercise the search adapter for real against
the temp graph. The selector CALL seam is faked package-wide so no HTTP ever
fires: thin_retained_zero yields an honest empty T2 on any non-empty space,
and the core abstains (zero calls) on an empty one.
"""
import pytest

from kdb_search.tests import fakes


@pytest.fixture(autouse=True)
def _stub_pass15_selector_call(monkeypatch):
    monkeypatch.setattr(
        "compiler.search_adapter.call_model",
        fakes.FakeSelector(fakes.ScriptedReply(fakes.retained_empty_document())))

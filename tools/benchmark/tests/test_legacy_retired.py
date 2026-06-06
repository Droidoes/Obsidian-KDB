"""Guards that the legacy #5 run engine stays retired (spec 2026-06-06)."""
from __future__ import annotations

import importlib

import pytest

from tools.benchmark import cli


@pytest.mark.parametrize("mod", ["runner", "scorer", "scorecard", "registry"])
def test_legacy_modules_are_gone(mod):
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(f"tools.benchmark.{mod}")


def test_score_subcommand_is_documented():
    parser_help = _capture_help(["--help"])
    assert "score" in parser_help


def test_models_flag_is_rejected():
    with pytest.raises(SystemExit):
        cli.main(["--models", "anything"])


def _capture_help(argv):
    import io
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), pytest.raises(SystemExit):
        cli.main(argv)
    return buf.getvalue()

import re
from common.version import release_version


def test_release_version_returns_git_describe_string():
    v = release_version()
    assert isinstance(v, str) and v
    assert v == "unknown" or re.match(r"^v\d|^[0-9a-f]{7,}", v)


def test_release_version_unknown_on_failure(monkeypatch):
    import common.version as ver
    def boom(*a, **k):
        raise OSError("no git")
    monkeypatch.setattr(ver.subprocess, "run", boom)
    assert release_version() == "unknown"

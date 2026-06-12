from __future__ import annotations

from pathlib import Path

from kdb_mcp import config


def test_default_graph_path_uses_env(monkeypatch):
    monkeypatch.setenv("KDB_GRAPH_PATH", "/tmp/some/graph")
    assert config.default_graph_path() == Path("/tmp/some/graph")


def test_default_graph_path_falls_back(monkeypatch):
    monkeypatch.delenv("KDB_GRAPH_PATH", raising=False)
    assert config.default_graph_path() == (Path.home() / "Droidoes" / "GraphDB-KDB")


def test_default_vault_root_delegates(monkeypatch):
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", "/tmp/some/vault")
    assert config.default_vault_root() == Path("/tmp/some/vault").resolve()

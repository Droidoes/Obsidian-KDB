# kdb_compiler/enrich/config_loader.py
"""Pass-1 config loader.

Reads domains.json (NW-4 v0.4 vocabulary), source_types.json (NW-7 v0.2
vocabulary), and scope-config.yaml (force_signal / force_noise path
globs). Loaded once at process start; cached for the run.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


CONFIG_DIR = Path(__file__).parent.parent / "config"


@dataclass(frozen=True)
class DomainEntry:
    id: str
    display: str
    scope: str
    aliases: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class SourceTypeEntry:
    id: str
    display: str
    scope: str
    aliases: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ScopeConfig:
    exclude_paths: tuple[str, ...]
    force_signal: tuple[str, ...]
    force_noise: tuple[str, ...]


def _load_entries(path: Path, cls):
    data: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
    return [
        cls(
            id=e["id"],
            display=e["display"],
            scope=e["scope"],
            aliases=tuple(e.get("aliases", []) or []),
        )
        for e in data
    ]


@lru_cache(maxsize=1)
def load_domains() -> list[DomainEntry]:
    return _load_entries(CONFIG_DIR / "domains.json", DomainEntry)


@lru_cache(maxsize=1)
def load_source_types() -> list[SourceTypeEntry]:
    return _load_entries(CONFIG_DIR / "source_types.json", SourceTypeEntry)


@lru_cache(maxsize=1)
def load_scope_config() -> ScopeConfig:
    data: dict = yaml.safe_load((CONFIG_DIR / "scope-config.yaml").read_text(encoding="utf-8"))
    return ScopeConfig(
        exclude_paths=tuple(data.get("exclude_paths", []) or []),
        force_signal=tuple(data.get("force_signal", []) or []),
        force_noise=tuple(data.get("force_noise", []) or []),
    )

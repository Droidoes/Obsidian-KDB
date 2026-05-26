# kdb_compiler/tests/test_pass1_config_loader.py
import pytest
from kdb_compiler.ingestion.config_loader import (
    load_domains, load_source_types, load_scope_config,
    DomainEntry, SourceTypeEntry, ScopeConfig,
)


def test_load_domains_returns_23_entries():
    domains = load_domains()
    assert len(domains) == 23
    assert all(isinstance(d, DomainEntry) for d in domains)
    ids = {d.id for d in domains}
    assert "ai-ml" in ids
    assert "value-investing" in ids
    assert "undecided" in ids


def test_load_source_types_returns_21_entries():
    sts = load_source_types()
    assert len(sts) == 21
    ids = {s.id for s in sts}
    assert "blog" in ids
    assert "interview" in ids
    assert "chat-log" in ids
    assert "other" in ids


def test_source_types_aliases_resolve_for_renames():
    sts = load_source_types()
    interview = next(s for s in sts if s.id == "interview")
    assert "transcript-interview" in interview.aliases
    video = next(s for s in sts if s.id == "transcript-video")
    assert "transcript-youtube" in video.aliases


def test_scope_config_loads_defaults():
    cfg = load_scope_config()
    assert isinstance(cfg, ScopeConfig)
    assert cfg.exclude_paths == ()
    assert cfg.force_signal == ()
    assert "Daily Notes/**" in cfg.force_noise
    assert "Projects/**" in cfg.force_noise


def test_domain_ids_are_unique():
    domains = load_domains()
    ids = [d.id for d in domains]
    assert len(ids) == len(set(ids))


def test_source_type_ids_are_unique():
    sts = load_source_types()
    ids = [s.id for s in sts]
    assert len(ids) == len(set(ids))

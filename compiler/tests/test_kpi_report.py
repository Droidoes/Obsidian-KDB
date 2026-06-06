"""Tests for compiler.kpi.report.render_report (#109 refinement 2026-06-06).

render_report turns a measurements payload into a Markdown report written
alongside measurements.json at --emit-kpis time.
"""
from __future__ import annotations

from compiler.kpi.report import render_report


def _payload() -> dict:
    return {
        "header": {
            "run_id": "2026-06-06T09-59-00_EDT",
            "corpus_fingerprint": "db732c11",
            "pass1_prompt_version": "1.2.0",
            "pass2_prompt_version": "",
            "scanned": 36,
            "to_compile": 36,
            "signal": 28,
            "noise": 8,
            "p1_attempted": 36,
            "p2_attempted": 28,
            "provider": "deepseek",
            "model": "deepseek-v4-flash",
        },
        "processing": {
            "scored": {
                "quarantine_rate": 0.0,
                "recovery_rate": 0.0,
                "latency": 1943404.47,
            },
            "diagnostic": {
                "signal_noise_ratio": 0.7778,
                "latency_pass1": 800000.0,
                "latency_pass2": 1100000.0,
            },
        },
        "graph": {
            "scored": {
                "entity_reuse": 0.0265,
                "graph_connectivity": 0.1453,
                "link_density": 2.5587,
                "supports_density": 6.24,
            },
            "watched": {
                "orphan_rate": 0.0,
                "entity_search_key_resolution": None,
            },
            "diagnostic": {
                "belongs_to_coverage": 1.0,
                "domain_null_rate": 0.0,
                "domain_breadth": 0.4348,
            },
        },
    }


def test_render_returns_markdown_string():
    out = render_report(_payload())
    assert isinstance(out, str)
    assert out.endswith("\n")


def test_header_fields_rendered():
    out = render_report(_payload())
    assert "deepseek-v4-flash" in out      # model slug (title + metadata)
    assert "deepseek" in out               # provider
    assert "2026-06-06T09-59-00_EDT" in out
    assert "db732c11" in out
    assert "36 scanned" in out


def test_scored_kpis_present_with_direction_arrows():
    out = render_report(_payload())
    # entity_reuse is higher-is-better → ↑; processing scored are ↓.
    assert "entity_reuse ↑" in out
    assert "quarantine_rate ↓" in out
    assert "latency ↓" in out


def test_none_renders_as_emdash():
    out = render_report(_payload())
    # entity_search_key_resolution is None → em-dash, not "None" or "0".
    assert "entity_search_key_resolution | — |" in out


def test_graph_confound_caveat_present():
    out = render_report(_payload())
    lower = out.lower()
    assert "confound" in lower
    assert "multi-model" in lower


def test_section_headers_present():
    out = render_report(_payload())
    assert "## Processing" in out
    assert "## Graph" in out
    assert "**Watched**" in out


def test_per_pass_latency_in_diagnostic():
    out = render_report(_payload())
    assert "latency_pass1" in out
    assert "latency_pass2" in out

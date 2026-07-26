"""Restoration smoke test for the #123 SearchSnapshot fixture (spec §8.1).

The fixture is the frozen evaluation substrate for semantic graph search —
tracked, minimized, checksummed. This test must pass before any truth-set
labeling begins. stdlib + pytest only (json / hashlib / pathlib); it reads
ONLY the tracked fixture dir (never the gitignored source bundle).
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

FIXTURE_DIR = (Path(__file__).resolve().parents[3]
               / "benchmark" / "truth" / "task123_search_snapshot_v1")

# Pinned from the frozen 2026-07-25 bundle at fixture-build time (verified —
# do not "refresh" from the bundle; the fixture is the authority).
_EXPECTED_TYPE_COUNTS = {"concept": 116, "article": 18, "summary": 29}
_EXPECTED_CAPPED = [
    "pabrai-cannibal-formula-and-singleton-playbook",
    "value-investing-as-owner-mindset-and-analytical-rigor",
]
_HENRY_SINGLETON_PREFIX = (
    b"\nHenry Singleton was the founder and CEO of Teledyne, "
    b"widely regarded by Warren "
)
assert len(_HENRY_SINGLETON_PREFIX) == 80


def _identities() -> list[dict]:
    return json.loads((FIXTURE_DIR / "identities.json").read_text(encoding="utf-8"))


def _manifest() -> dict:
    return json.loads((FIXTURE_DIR / "manifest.json").read_text(encoding="utf-8"))


# ---------- 1. identities shape ----------

def test_identities_count_and_page_type_counts():
    ids = _identities()
    assert len(ids) == 163
    assert Counter(i["page_type"] for i in ids) == _EXPECTED_TYPE_COUNTS
    assert [i["slug"] for i in ids] == sorted(i["slug"] for i in ids)


def test_every_identity_has_domain_and_int_hub_rank():
    for i in _identities():
        assert i["domain"], f"{i['slug']}: empty domain"
        assert isinstance(i["hub_rank"], int) and not isinstance(i["hub_rank"], bool)
        assert set(i) == {"slug", "title", "page_type", "domain", "hub_rank"}


# ---------- 2. excerpts + checksums completeness ----------

def _checksum_lines() -> list[tuple[str, str]]:
    lines = (FIXTURE_DIR / "checksums.sha256").read_text(encoding="utf-8").splitlines()
    out = []
    for line in lines:
        digest, rel = line.split("  ", 1)
        out.append((digest, rel))
    return out


def test_every_identity_has_an_excerpt_file():
    for i in _identities():
        path = FIXTURE_DIR / "excerpts" / i["page_type"] / f"{i['slug']}.txt"
        assert path.is_file(), f"missing excerpt for {i['slug']}"


def test_checksums_cover_every_file_and_hash_matches():
    entries = _checksum_lines()
    recorded = set()
    for digest, rel in entries:
        path = FIXTURE_DIR / rel
        assert path.is_file(), f"recorded file missing: {rel}"
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest, rel
        recorded.add(rel)
    # no unrecorded files anywhere in the fixture dir
    on_disk = {str(p.relative_to(FIXTURE_DIR)) for p in FIXTURE_DIR.rglob("*") if p.is_file()}
    assert on_disk - recorded == {"checksums.sha256"}
    # 165 = manifest.json + identities.json + 163 excerpts
    assert len(entries) == 165


# ---------- 3. manifest provenance + counts ----------

def test_manifest_counts_match_recomputed():
    ids = _identities()
    man = _manifest()
    assert man["counts"]["total"] == len(ids)
    assert man["counts"]["by_page_type"] == dict(
        sorted(Counter(i["page_type"] for i in ids).items()))
    assert man["counts"]["by_domain"] == dict(
        sorted(Counter(i["domain"] for i in ids).items()))
    assert man["source_run_id"] == "gemini-3.6-flash-2026-07-25T09-41-46_EDT"
    assert man["excerpt_policy_version"] == "1"
    assert man["excerpt_policy"] and man["hub_rank_method"]


# ---------- 4. representative entity ----------

def test_henry_singleton_representative_entity():
    ids = {i["slug"]: i for i in _identities()}
    hs = ids["henry-singleton"]
    assert hs["page_type"] == "concept"
    assert hs["domain"] == "value-investing"
    excerpt = (FIXTURE_DIR / "excerpts" / "concept" / "henry-singleton.txt").read_bytes()
    assert excerpt[:80] == _HENRY_SINGLETON_PREFIX


# ---------- 5. excerpt policy spot-check ----------

def test_excerpt_policy_bounds_and_capped_set():
    man = _manifest()
    assert man["capped"] == _EXPECTED_CAPPED
    capped = set(man["capped"])
    for i in _identities():
        path = FIXTURE_DIR / "excerpts" / i["page_type"] / f"{i['slug']}.txt"
        n_words = len(path.read_text(encoding="utf-8").split())
        assert n_words <= 276, f"{i['slug']}: excerpt {n_words} words > 276"
        if i["slug"] not in capped:
            # verbatim path — the frozen body itself was <=250 words
            assert n_words <= 250, f"{i['slug']}: uncapped but {n_words} words"

"""Canonicalization stage for KDB compile (Task #74).

Stage [6] of the kdb-compile pipeline (post-#74.4). Sits between Stage [5]
reconcile and Stage [7] build_source_state. Resolves alias surface forms
to canonical entity slugs so wiki pages and graph entities agree on
names (wiki ≡ graph on entity names per blueprint D-R5-12).

This module currently exposes the **ledger loader** (Task #74.2). The
algorithm `canonicalize.run()` lands in Task #74.3; pipeline wiring in
Task #74.4.

References:
- docs/task74-canonicalization-blueprint.md §6 (contract) and §7 (algorithm)
- docs/what-is-ontology-for-V1.md §8.2 (canonicalization-first mandate)

Errors raised here are fatal per D-R5-9 — Stage [6] failure prevents the
compile from progressing to patch_applier so the vault is not written
inconsistently with the graph.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
import warnings
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping

from kdb_compiler import atomic_io

# Sentinel sha for the "missing file → empty ledger" path (D-R5-8). Stored
# into canonical_meta.ledger_snapshot_sha256 so replay (D39 / D-R5-7) can
# verify the same condition held during the original compile.
EMPTY_LEDGER_SHA = "empty"


class LedgerLoadError(RuntimeError):
    """Raised when aliases.json is present but cannot be loaded or
    validated (malformed JSON, wrong shape, duplicate surface, missing
    required field). Fatal per D-R5-9 — caller must surface the failure
    journal and halt the pipeline before patch_applier."""


@dataclass(frozen=True)
class AliasEntry:
    """One entry in the alias ledger.

    `surface` — the form the LLM might emit (e.g. "AAPL").
    `canonical` — the slug it should resolve to (e.g. "apple-inc").
    `note` — optional human comment for ledger maintainers; no runtime effect.
    """
    surface: str
    canonical: str
    note: str | None = None


@dataclass(frozen=True)
class AliasLedger:
    """Immutable snapshot of `aliases.json` returned by `load_or_empty`.

    `entries` is the parsed list of mappings.
    `snapshot_sha256` is sha256 of the raw file bytes — captured into
        `canonical_meta.ledger_snapshot_sha256` so `graphdb-kdb rebuild`
        can prove the ledger state matched what was archived.
        Equals `EMPTY_LEDGER_SHA` ("empty") when the file was missing.
    `path` is the source location for diagnostics; `None` for purely
        synthetic ledgers built in tests.
    """
    entries: tuple[AliasEntry, ...] = ()
    snapshot_sha256: str = EMPTY_LEDGER_SHA
    path: Path | None = None

    @property
    def is_empty(self) -> bool:
        return len(self.entries) == 0

    def by_surface(self) -> Mapping[str, AliasEntry]:
        """Build a dict view keyed by raw surface form. Surface keys are
        not normalized here — canonicalize.run() (Task #74.3) normalizes
        the LLM-emitted slug before lookup, so the ledger key shape must
        match the post-normalization form the algorithm produces."""
        return {e.surface: e for e in self.entries}


def load_or_empty(path: Path | str) -> AliasLedger:
    """Load the alias ledger from `path`. Behavior per D-R5-8:

    - **Missing file** → returns an empty `AliasLedger` (sha = "empty")
      and emits a `UserWarning` so the operator sees that string
      normalization is the only canonicalization mechanism running.
      First-run convenience: nothing breaks before any aliases exist.
    - **Present + valid** → returns a populated `AliasLedger` with sha
      computed over the raw file bytes.
    - **Present + malformed** → raises `LedgerLoadError`. Fatal per
      D-R5-9; Stage [6] writes a failure journal and the pipeline halts
      before patch_applier so wiki and graph stay aligned on the
      previous state.

    Validation enforced:
    - Root is a JSON object.
    - `aliases` is a list (default `[]` if absent).
    - Each entry is an object with non-empty string `surface` and
      `canonical`; optional `note` is a string if present.
    - No surface appears twice. Duplicate surfaces (whether they map to
      the same canonical or not) raise `LedgerLoadError` so ledger
      ambiguity surfaces at edit time, not at compile time.
    """
    p = Path(path)
    if not p.exists():
        warnings.warn(
            f"Alias ledger not found at {p}; running with empty ledger "
            "(string normalization only — D-R5-8).",
            UserWarning,
            stacklevel=2,
        )
        return AliasLedger(entries=(), snapshot_sha256=EMPTY_LEDGER_SHA, path=p)

    raw_bytes = p.read_bytes()
    sha = hashlib.sha256(raw_bytes).hexdigest()

    try:
        payload = json.loads(raw_bytes)
    except json.JSONDecodeError as e:
        raise LedgerLoadError(f"malformed JSON in ledger at {p}: {e}") from e

    if not isinstance(payload, dict):
        raise LedgerLoadError(
            f"ledger root at {p} must be a JSON object, "
            f"got {type(payload).__name__}"
        )

    raw_entries = payload.get("aliases", [])
    if not isinstance(raw_entries, list):
        raise LedgerLoadError(
            f"`aliases` in ledger at {p} must be a list, "
            f"got {type(raw_entries).__name__}"
        )

    parsed: list[AliasEntry] = []
    seen_surfaces: set[str] = set()
    for i, raw in enumerate(raw_entries):
        if not isinstance(raw, dict):
            raise LedgerLoadError(
                f"ledger at {p}: entry [{i}] must be an object, "
                f"got {type(raw).__name__}"
            )
        surface = raw.get("surface")
        canonical = raw.get("canonical")
        if not isinstance(surface, str) or not surface:
            raise LedgerLoadError(
                f"ledger at {p}: entry [{i}] missing required non-empty "
                "string field 'surface'"
            )
        if not isinstance(canonical, str) or not canonical:
            raise LedgerLoadError(
                f"ledger at {p}: entry [{i}] missing required non-empty "
                "string field 'canonical'"
            )
        note = raw.get("note")
        if note is not None and not isinstance(note, str):
            raise LedgerLoadError(
                f"ledger at {p}: entry [{i}] 'note' must be a string if "
                f"present, got {type(note).__name__}"
            )
        if surface in seen_surfaces:
            raise LedgerLoadError(
                f"ledger at {p}: surface {surface!r} appears more than once "
                "— resolve the duplicate in aliases.json before re-running"
            )
        seen_surfaces.add(surface)
        parsed.append(AliasEntry(surface=surface, canonical=canonical, note=note))

    return AliasLedger(
        entries=tuple(parsed),
        snapshot_sha256=sha,
        path=p,
    )


# =========================================================================
# Algorithm — Stage [6] canonicalize.run() (Task #74.3)
# =========================================================================
#
# Five passes per blueprint §7:
#   1. Build slug→canonical resolve map from the ledger (chain-flattened
#      per D-R5-13, cycle-checked).
#   2. Canonicalize page intents across all compiled_sources; merge
#      collisions per OQ-F (canonical-wins + longest-body fallback) with
#      UNION of outgoing_links + supports_page_existence across all
#      contenders (Codex's refinement).
#   3. Remap outgoing_links metadata + per-source slug lists
#      (summary_slug / concept_slugs / article_slugs).
#   4. Remap [[wikilink]] tokens in page bodies (D-R5-11).
#   5. Emit canonical_meta block + (caller-driven) atomic write-back.
#
# All mutation is in-place on the supplied cr dict — the same object is
# returned via CanonicalizationResult.compile_result.


class CircularAliasError(RuntimeError):
    """The alias ledger or its closure produces a cycle (e.g., A→B→A).

    Fatal per D-R5-9 — Stage [6] writes a failure journal and halts the
    pipeline before patch_applier.
    """


# Wikilink syntax: [[target]] or [[target|display]]. Anchor links
# ([[target#section]]) are out of scope for v1 — the LLM is not instructed
# to emit them and the schema's outgoing_links pattern (kebab slugs)
# disallows them at the metadata level. If they appear in body text we
# leave them untouched.
_WIKILINK_RE = re.compile(r"\[\[([^\[\]|#]+?)(?:\|([^\[\]]+?))?\]\]")


def _normalize_slug(s: str) -> str:
    """Map an arbitrary string to its kebab-case slug form. Tolerant:
    returns `""` if no normalizable content (e.g., pure punctuation).
    Idempotent: ``_normalize_slug(_normalize_slug(s)) == _normalize_slug(s)``.

    The function is deliberately separate from `paths.slugify()` — paths
    raises on empty results (its callers want a valid filename); we want
    to tolerate junk and pass it through unchanged.
    """
    if not s:
        return ""
    nfkd = unicodedata.normalize("NFKD", s)
    ascii_only = nfkd.encode("ascii", "ignore").decode("ascii")
    kebab = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_only).strip("-").lower()
    return kebab


def _dedupe(items: Iterable[str]) -> list[str]:
    """Preserving-order deduplication of strings."""
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def _dedupe_tuples(items: Iterable[tuple[str, str]]) -> list[tuple[str, str]]:
    seen: set[tuple[str, str]] = set()
    out: list[tuple[str, str]] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def build_resolve_map(ledger: AliasLedger) -> dict[str, str]:
    """Pass 1: build a normalized-slug → root-canonical-slug map.

    Both surface and canonical are normalized via `_normalize_slug`. Chains
    (`A→B`, `B→C`) are flattened so the map's values always point at the
    root canonical (D-R5-13 invariant). Cycles raise `CircularAliasError`.

    Surfaces that normalize to the same form as their canonical are
    skipped (no-op mapping). Surfaces or canonicals that normalize to
    empty strings (pure-punctuation entries) are also skipped — defensive
    against ledger entries that have nothing extractable.
    """
    # Single-hop normalized map. Duplicate-surface protection happened at
    # ledger-load time, so any duplicate here is a load-bug rather than a
    # user-content issue.
    single_hop: dict[str, str] = {}
    for entry in ledger.entries:
        surface = _normalize_slug(entry.surface)
        canonical = _normalize_slug(entry.canonical)
        if not surface or not canonical or surface == canonical:
            continue
        single_hop[surface] = canonical

    # Flatten chains via traversal with visited set per starting surface.
    resolve: dict[str, str] = {}
    for surface in single_hop:
        path: list[str] = [surface]
        current = single_hop[surface]
        while current in single_hop:
            if current in path:
                path.append(current)
                raise CircularAliasError(
                    "alias cycle detected: " + " → ".join(path)
                )
            path.append(current)
            current = single_hop[current]
        resolve[surface] = current
    return resolve


def _canonical_of(slug: str, resolve: dict[str, str]) -> str:
    """Look up the canonical form of `slug`. Returns the normalized slug
    itself when no alias mapping exists (i.e. the slug is canonical by
    construction). Returns `""` if the input has no normalizable content
    AND no alias mapping — caller must guard against this if it matters."""
    norm = _normalize_slug(slug)
    return resolve.get(norm, norm)


def _remap_body_wikilinks(
    body: str, resolve: dict[str, str]
) -> tuple[str, list[tuple[str, str]]]:
    """Pass 4: rewrite `[[alias]]` tokens in markdown body to `[[canonical]]`.
    Preserves `[[target|display]]` display text. Returns the new body
    plus the list of `(original_target, canonical)` pairs that changed
    (one per replacement; caller deduplicates)."""
    remaps: list[tuple[str, str]] = []

    def replace(match: re.Match) -> str:
        target = match.group(1).strip()
        display = match.group(2)
        normalized = _normalize_slug(target)
        canonical = resolve.get(normalized, normalized)
        if canonical == normalized:
            # No mapping — leave the wikilink as-is to preserve the
            # author's exact text (could be capitalization, punctuation,
            # etc. that the human wants visible in Obsidian).
            return match.group(0)
        remaps.append((target, canonical))
        if display is not None:
            return f"[[{canonical}|{display}]]"
        return f"[[{canonical}]]"

    new_body = _WIKILINK_RE.sub(replace, body)
    return new_body, remaps


def _merge_page_intents(
    cr: dict, resolve: dict[str, str]
) -> tuple[list[dict], list[tuple[str, str]]]:
    """Pass 2: canonicalize all page intent slugs across `compiled_sources`
    and merge collisions per OQ-F.

    Behavior:
    - For each `(compiled_source_idx, page_idx, page)` tuple, compute the
      canonical slug.
    - Group by canonical slug; groups of size 1 simply rename the slug
      if it was an alias singleton; groups of size 2+ apply the OQ-F
      policy:
        - if any contender's normalized slug equals the canonical, that
          contender's body wins (`canonical-wins`); first match wins
          deterministically when multiple canonicals were emitted (rare).
        - otherwise, the longest body wins (`longest-wins`).
      In both cases the merged page UNIONs `outgoing_links` and
      `supports_page_existence` across all contenders (Codex's refinement),
      preserving emission order with dedup.
    - The merged page is placed at the body-winner's original
      `(compiled_source_idx, page_idx)` position; other contenders are
      removed from their respective `pages[]` lists.
    - Mutates `cr` in place.

    Returns:
        - `merged_log`: list of `{alias_page_slug, merged_into_canonical,
          merge_strategy}` dicts, one entry per alias page intent that
          was folded into a canonical.
        - `used_aliases`: list of `(normalized_alias_slug, canonical_slug)`
          pairs for page-slug renames — feeds into `aliases_emitted`.
    """
    by_canonical: dict[str, list[tuple[int, int, dict]]] = defaultdict(list)
    for cs_idx, cs in enumerate(cr.get("compiled_sources", [])):
        for p_idx, page in enumerate(cs.get("pages", [])):
            canonical = _canonical_of(page["slug"], resolve)
            by_canonical[canonical].append((cs_idx, p_idx, page))

    merged_log: list[dict] = []
    used_aliases: list[tuple[str, str]] = []
    pages_to_remove: dict[int, set[int]] = defaultdict(set)
    pages_to_replace: dict[tuple[int, int], dict] = {}

    for canonical, contenders in by_canonical.items():
        if len(contenders) == 1:
            cs_idx, p_idx, page = contenders[0]
            if _normalize_slug(page["slug"]) != canonical:
                # alias singleton — rename to canonical
                new_page = dict(page)
                new_page["slug"] = canonical
                pages_to_replace[(cs_idx, p_idx)] = new_page
                merged_log.append({
                    "alias_page_slug": page["slug"],
                    "merged_into_canonical": canonical,
                    "merge_strategy": "alias-singleton-rename",
                })
                used_aliases.append((_normalize_slug(page["slug"]), canonical))
            continue

        # Multiple contenders — apply OQ-F.
        canonical_named = [
            t for t in contenders if _normalize_slug(t[2]["slug"]) == canonical
        ]
        if canonical_named:
            winner_cs_idx, winner_p_idx, winner_page = canonical_named[0]
            strategy = "canonical-wins"
        else:
            winner_cs_idx, winner_p_idx, winner_page = max(
                contenders, key=lambda t: len(t[2].get("body", ""))
            )
            strategy = "longest-wins"

        merged = dict(winner_page)
        merged["slug"] = canonical

        # UNION outgoing_links (Codex's refinement)
        all_outgoing: list[str] = []
        for _, _, p in contenders:
            all_outgoing.extend(p.get("outgoing_links", []))
        merged_outgoing = _dedupe(all_outgoing)
        if merged_outgoing:
            merged["outgoing_links"] = merged_outgoing
        elif "outgoing_links" in merged:
            del merged["outgoing_links"]

        # UNION supports_page_existence
        all_supports: list[str] = []
        for _, _, p in contenders:
            all_supports.extend(p.get("supports_page_existence", []))
        merged_supports = _dedupe(all_supports)
        if merged_supports:
            merged["supports_page_existence"] = merged_supports
        elif "supports_page_existence" in merged:
            del merged["supports_page_existence"]

        pages_to_replace[(winner_cs_idx, winner_p_idx)] = merged

        for cs_idx, p_idx, p in contenders:
            if (cs_idx, p_idx) == (winner_cs_idx, winner_p_idx):
                # Even the winner may have been an alias (in longest-wins);
                # if so, the rename is recorded.
                if _normalize_slug(p["slug"]) != canonical:
                    merged_log.append({
                        "alias_page_slug": p["slug"],
                        "merged_into_canonical": canonical,
                        "merge_strategy": strategy,
                    })
                    used_aliases.append((_normalize_slug(p["slug"]), canonical))
                continue
            pages_to_remove[cs_idx].add(p_idx)
            merged_log.append({
                "alias_page_slug": p["slug"],
                "merged_into_canonical": canonical,
                "merge_strategy": strategy,
            })
            used_aliases.append((_normalize_slug(p["slug"]), canonical))

    # Apply replacements + removals in one walk per source.
    for cs_idx, cs in enumerate(cr.get("compiled_sources", [])):
        remove_set = pages_to_remove.get(cs_idx, set())
        new_pages: list[dict] = []
        for p_idx, page in enumerate(cs.get("pages", [])):
            if p_idx in remove_set:
                continue
            new_pages.append(pages_to_replace.get((cs_idx, p_idx), page))
        cs["pages"] = new_pages

    return merged_log, used_aliases


def _remap_outgoing_and_slug_lists(
    cr: dict, resolve: dict[str, str]
) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """Pass 3: remap `outgoing_links` plus per-source `summary_slug`,
    `concept_slugs`, `article_slugs` lists.

    Returns:
        - link_remaps: list of `(from, to)` pairs for canonical_meta.outgoing_link_remaps
          (outgoing_links only; slug-list renames are not "link" remaps)
        - used_aliases: same `(normalized_alias, canonical)` shape as
          Pass 2 — for aliases_emitted
    """
    link_remaps: list[tuple[str, str]] = []
    used_aliases: list[tuple[str, str]] = []

    for cs in cr.get("compiled_sources", []):
        # summary_slug — usually starts with "summary-", but defensive
        # in case the ledger ever points one elsewhere.
        old = cs.get("summary_slug")
        if old:
            new = _canonical_of(old, resolve)
            if new != _normalize_slug(old) and new:
                cs["summary_slug"] = new
                used_aliases.append((_normalize_slug(old), new))

        # concept_slugs / article_slugs — remap + dedupe (collisions
        # arise when two aliases in the same list resolve to one canonical)
        for key in ("concept_slugs", "article_slugs"):
            if key in cs:
                new_list: list[str] = []
                for slug in cs[key]:
                    canonical = _canonical_of(slug, resolve)
                    if canonical != _normalize_slug(slug) and canonical:
                        used_aliases.append((_normalize_slug(slug), canonical))
                    new_list.append(canonical)
                cs[key] = _dedupe(new_list)

        # Page outgoing_links — these are link remaps that feed into
        # canonical_meta.outgoing_link_remaps.
        for page in cs.get("pages", []):
            if "outgoing_links" not in page:
                continue
            new_links: list[str] = []
            for link in page["outgoing_links"]:
                canonical = _canonical_of(link, resolve)
                if canonical != _normalize_slug(link) and canonical:
                    link_remaps.append((link, canonical))
                    used_aliases.append((_normalize_slug(link), canonical))
                new_links.append(canonical)
            page["outgoing_links"] = _dedupe(new_links)

    return link_remaps, used_aliases


def _remap_all_bodies(
    cr: dict, resolve: dict[str, str]
) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """Pass 4: rewrite `[[wikilink]]` tokens across every page body.

    Returns:
        - link_remaps: list of `(from, to)` pairs (one per replacement;
          caller deduplicates with Pass 3's link_remaps)
        - used_aliases: same as Pass 2/3
    """
    link_remaps: list[tuple[str, str]] = []
    used_aliases: list[tuple[str, str]] = []
    for cs in cr.get("compiled_sources", []):
        for page in cs.get("pages", []):
            body = page.get("body", "")
            new_body, remaps = _remap_body_wikilinks(body, resolve)
            page["body"] = new_body
            for old_target, canonical in remaps:
                link_remaps.append((old_target, canonical))
                used_aliases.append((_normalize_slug(old_target), canonical))
    return link_remaps, used_aliases


@dataclass(frozen=True)
class CanonicalizationResult:
    """What `canonicalize.run()` returns to the caller.

    `compile_result` is the same dict that was passed in — mutated in
    place to include the new `canonical_meta` top-level key plus the
    canonicalized `compiled_sources[]` (renamed slugs, merged pages,
    remapped links, remapped body wikilinks).

    `canonical_meta` is the dict that was written into the compile_result
    payload — also returned standalone for easy assertion in tests and
    for the caller to journal as it sees fit.

    `stats` is a counts summary for journal observability:
    `{aliases_emitted, pages_merged, outgoing_link_remaps}`.
    """
    compile_result: dict
    canonical_meta: dict
    stats: dict = field(default_factory=dict)


def run(
    cr: dict,
    ledger: AliasLedger,
    run_id: str,
    *,
    algorithm_version: str = "1.0",
) -> CanonicalizationResult:
    """Canonicalize the compile_result in place. Round 5 §8.2 +
    blueprint §6/§7.

    Steps:
        Pass 1 — build resolve map from ledger (chain-flatten, cycle-check)
        Pass 2 — page-intent canonicalization + OQ-F merging
        Pass 3 — outgoing_links + per-source slug list remap
        Pass 4 — body `[[wikilink]]` remap
        Pass 5 — emit `canonical_meta` into the cr payload

    Raises:
        CircularAliasError — if the ledger closure contains a cycle.

    The atomic write-back of the canonicalized `state/compile_result.json`
    is the caller's responsibility (see `write_canonicalized()`). Tests
    and library callers can use `run()` standalone; the kdb_compile.py
    Stage [6] wiring (Task #74.4) combines the two.
    """
    resolve = build_resolve_map(ledger)

    # Pass 2
    merged_log, used_aliases_2 = _merge_page_intents(cr, resolve)

    # Pass 3
    link_remaps_3, used_aliases_3 = _remap_outgoing_and_slug_lists(cr, resolve)

    # Pass 4
    link_remaps_4, used_aliases_4 = _remap_all_bodies(cr, resolve)

    # Combine link remaps with stable order: Pass 3 (metadata) then Pass 4
    # (body), each deduped separately first then combined dedup'd to give
    # metadata-first ordering on first-seen.
    all_link_remaps = _dedupe_tuples(list(link_remaps_3) + list(link_remaps_4))

    # Combine used aliases across all passes — same dedup discipline.
    all_used_aliases = _dedupe_tuples(
        list(used_aliases_2) + list(used_aliases_3) + list(used_aliases_4)
    )

    aliases_emitted = [
        {"alias_slug": alias, "canonical_slug": canonical, "algorithm": "ledger"}
        for (alias, canonical) in all_used_aliases
    ]

    canonical_meta = {
        "algorithm_version": algorithm_version,
        "ledger_snapshot_sha256": ledger.snapshot_sha256,
        "aliases_emitted": aliases_emitted,
        "outgoing_link_remaps": [
            {"from": frm, "to": to} for (frm, to) in all_link_remaps
        ],
        "merged_pages": merged_log,
    }
    cr["canonical_meta"] = canonical_meta

    stats = {
        "aliases_emitted": len(aliases_emitted),
        "pages_merged": len(merged_log),
        "outgoing_link_remaps": len(all_link_remaps),
    }

    return CanonicalizationResult(
        compile_result=cr,
        canonical_meta=canonical_meta,
        stats=stats,
    )


def write_canonicalized(cr: dict, target: Path | str) -> None:
    """Atomically write the canonicalized compile_result to `target`
    (typically `state/compile_result.json`). D-R5-10: subsequent stages
    and per-run sidecar archival read this file, so it must reflect the
    canonical (post-Stage 6) state — not the raw extraction.

    Uses `atomic_io.atomic_write_json` for crash-consistency (tmpfile +
    fsync + rename), matching the rest of the pipeline's persistence
    discipline.
    """
    atomic_io.atomic_write_json(Path(target), cr)

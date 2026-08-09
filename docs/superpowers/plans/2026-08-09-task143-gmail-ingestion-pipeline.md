# Task #143 — Gmail/Substack Ingestion Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first ingestion (feeder) pipeline — convert `Substack_raw` Gmail messages in joseph.ft.public@gmail.com into KDB raw sources under `KDB/raw/joseph-ft-public-gmail/` — plus migrate the pipeline registry to `pipelines.d/` (one config file per pipeline).

**Architecture:** Deterministic feeder (no LLM): shell out to the `gws gmail` CLI behind a subprocess seam, extract metadata + body from message payloads, write metadata-only frontmatter `.md` sources, then move each message `Substack_raw` → `Substack_ai_processed` (label = processed-state). Registry migration turns `pipelines.json` into `pipelines.d/<id>.json` so each pipeline is a plugin file.

**Tech Stack:** Python 3.10+, `gws` CLI (auth already verified for joseph.ft.public@gmail.com), `markdownify` (new dep — HTML→markdown), `pyyaml` (existing), pytest.

**Spec:** `docs/superpowers/specs/2026-08-09-task143-gmail-ingestion-pipeline-blueprint-v0.1.md` (ratified 2026-08-09). Decisions D1–D9 below refer to it.

## Global Constraints

- Python 3.10+, 4-space indent, modern type hints (`list[str]`, `str | None`).
- Layering (guard-tested by `tools/tests/test_package_boundaries.py`): `ingestion` may import `common` only. The feeder must NOT import compiler/kdb_graph/orchestrator.
- Only ONE new dependency: `markdownify>=0.13` (no HTML→markdown dep exists in `pyproject.toml` today — checked).
- Vault paths via `common.paths.kdb_root()` (honors `OBSIDIAN_VAULT_PATH`).
- Frontmatter contract (D2) — exactly these keys, nothing classificatory: `title`, `author`, `published_date`, `source_url`, `gmail_message_id`, `content_kind`, `feeder`, `ingested_at`.
- Gmail writes are confined to ONE operation (D3): `messages.modify` moving `Substack_raw` → `Substack_ai_processed`. Everything else read-only.
- The `vault-in-place` pipeline **id string must not change** — it is stamped in manifest/journal history (#91).
- Conventional commits with task refs: `feat(feeder): #143 — …`.
- The prod vault is NOT a git repo — vault-side steps have no commit step.

---

### Task 1: `pipelines.d/` registry loader

**Files:**
- Modify: `ingestion/config/pipeline_registry.py` (whole-file rewrite of the loading half; `_parse_entry` + `Pipeline` unchanged)
- Test: `ingestion/tests/test_pipeline_registry.py` (rewrite helpers + add cases)

**Interfaces:**
- Consumes: existing `Pipeline` dataclass + `PipelineRegistryError`.
- Produces: `load_pipelines(state_root) -> list[Pipeline]` — reads `<state_root>/pipelines.d/*.json` (sorted by filename); `list_pipelines(state_root) -> list[str]`; `get_pipeline(state_root, pipeline_id) -> Pipeline`. Signatures unchanged — the orchestrator (`orchestrator/kdb_orchestrate.py:685,1410`) needs no edits.

- [ ] **Step 1: Rewrite the failing tests**

Replace the `_write` helper and add new cases in `ingestion/tests/test_pipeline_registry.py`:

```python
"""Task #91 Plan 3 — pipeline registry tests; #143 pipelines.d layout."""
import json
from pathlib import Path

import pytest

from ingestion.config import pipeline_registry as pr


def _write(state_root: Path, pipelines: list[dict]) -> None:
    """One file per pipeline under pipelines.d/<id>.json (#143)."""
    ddir = state_root / "pipelines.d"
    ddir.mkdir(parents=True, exist_ok=True)
    for entry in pipelines:
        (ddir / f"{entry['id']}.json").write_text(
            json.dumps(entry), encoding="utf-8")


def _entry(tmp_path: Path, pid: str, sub: str = "src") -> dict:
    root = tmp_path / sub
    root.mkdir(parents=True, exist_ok=True)
    return {"id": pid, "type": "in-place", "root": str(root),
            "force_noise": ["Daily Notes/"]}


# ---------- load_pipelines (#143 pipelines.d) ----------

def test_load_pipelines_parses_entry(tmp_path):
    state = tmp_path / "state"
    _write(state, [_entry(tmp_path, "vault-in-place")])
    pipes = pr.load_pipelines(state)
    assert len(pipes) == 1
    p = pipes[0]
    assert p.id == "vault-in-place"
    assert p.type == "in-place"
    assert p.force_noise == ["Daily Notes/"]
    assert p.file_types == [".md"]          # default
    assert p.excludes == [] and p.force_signal == [] and p.feeder is None


def test_load_pipelines_aggregates_sorted(tmp_path):
    state = tmp_path / "state"
    _write(state, [_entry(tmp_path, "vault-in-place", "a"),
                   _entry(tmp_path, "gmail-substack", "b")])
    assert [p.id for p in pr.load_pipelines(state)] == [
        "gmail-substack", "vault-in-place"]     # sorted by filename


def test_load_pipelines_rejects_filename_id_mismatch(tmp_path):
    state = tmp_path / "state"
    _write(state, [_entry(tmp_path, "real-id")])
    bad = state / "pipelines.d" / "real-id.json"
    bad.rename(state / "pipelines.d" / "other-name.json")
    with pytest.raises(pr.PipelineRegistryError, match="does not match filename"):
        pr.load_pipelines(state)


def test_load_pipelines_rejects_missing_root(tmp_path):
    state = tmp_path / "state"
    _write(state, [{"id": "x", "type": "raw", "root": str(tmp_path / "nope")}])
    with pytest.raises(pr.PipelineRegistryError, match="root"):
        pr.load_pipelines(state)


def test_load_pipelines_missing_dir_raises(tmp_path):
    with pytest.raises(pr.PipelineRegistryError, match="not found"):
        pr.load_pipelines(tmp_path / "state")


def test_load_pipelines_legacy_only_raises_migration_error(tmp_path):
    state = tmp_path / "state"
    state.mkdir(parents=True)
    (state / "pipelines.json").write_text(
        json.dumps({"pipelines": [_entry(tmp_path, "vault-in-place")]}),
        encoding="utf-8")
    with pytest.raises(pr.PipelineRegistryError, match="migrate"):
        pr.load_pipelines(state)


def test_load_pipelines_both_layouts_fail_closed(tmp_path):
    state = tmp_path / "state"
    _write(state, [_entry(tmp_path, "vault-in-place")])
    (state / "pipelines.json").write_text(
        json.dumps({"pipelines": [_entry(tmp_path, "vault-in-place")]}),
        encoding="utf-8")
    with pytest.raises(pr.PipelineRegistryError, match="remove pipelines.json"):
        pr.load_pipelines(state)


def test_load_pipelines_rejects_bundle_shape(tmp_path):
    state = tmp_path / "state"
    ddir = state / "pipelines.d"
    ddir.mkdir(parents=True)
    (ddir / "x.json").write_text(
        json.dumps({"pipelines": [_entry(tmp_path, "x")]}), encoding="utf-8")
    with pytest.raises(pr.PipelineRegistryError, match="single pipeline object"):
        pr.load_pipelines(state)


# ---------- list_pipelines + get_pipeline ----------

def test_list_pipelines_returns_ids(tmp_path):
    state = tmp_path / "state"
    _write(state, [_entry(tmp_path, "a", "ra"), _entry(tmp_path, "b", "rb")])
    assert pr.list_pipelines(state) == ["a", "b"]


def test_get_pipeline_by_id(tmp_path):
    state = tmp_path / "state"
    _write(state, [_entry(tmp_path, "a", "ra"), _entry(tmp_path, "b", "rb")])
    p = pr.get_pipeline(state, "b")
    assert p.id == "b"


def test_get_pipeline_unknown_raises(tmp_path):
    state = tmp_path / "state"
    _write(state, [_entry(tmp_path, "a", "ra")])
    with pytest.raises(pr.PipelineRegistryError, match="unknown pipeline"):
        pr.get_pipeline(state, "missing")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest ingestion/tests/test_pipeline_registry.py -x -q`
Expected: FAIL — most cases error with `PipelineRegistryError: pipeline registry not found at …/pipelines.d` (loader still reads legacy `pipelines.json`).

- [ ] **Step 3: Rewrite the loader**

Replace `load_pipelines` in `ingestion/config/pipeline_registry.py` (keep `Pipeline`, `PipelineRegistryError`, `_VALID_TYPES`, `_parse_entry`, `list_pipelines`, `get_pipeline`; update the module docstring):

```python
"""pipeline_registry — per-vault ingestion-pipeline registry (Tasks #91, #143).

#143: config moved from a single `<state_root>/pipelines.json` to one file
per pipeline under `<state_root>/pipelines.d/<id>.json` — pipelines become
plugins: a new feeder ships its own file, nothing else changes. The filename
stem must equal the entry's `id`. The orchestrator reads this at startup to
present the pipeline-selection list and to scope the scan.
"""
```

New loading code:

```python
def _load_entry_file(path: Path) -> Pipeline:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise PipelineRegistryError(
            f"malformed pipeline file at {path}: {e}") from e
    if not isinstance(payload, dict) or "pipelines" in payload:
        raise PipelineRegistryError(
            f"{path} must be a single pipeline object, "
            f"not a {{'pipelines': [...]}} bundle")
    entry = _parse_entry(payload)
    if entry.id != path.stem:
        raise PipelineRegistryError(
            f"pipeline id {entry.id!r} does not match filename {path.name!r} "
            f"(expected pipelines.d/{entry.id}.json)")
    return entry


def load_pipelines(state_root: Path | str) -> list[Pipeline]:
    """Load + validate `<state_root>/pipelines.d/*.json` (#143). Validates:
    single-object files, filename==id, unique ids, roots exist.
    Raises PipelineRegistryError on any failure."""
    state_root = Path(state_root)
    ddir = state_root / "pipelines.d"
    legacy = state_root / "pipelines.json"
    if ddir.is_dir() and legacy.exists():
        raise PipelineRegistryError(
            f"both {ddir} and legacy {legacy} exist — remove pipelines.json "
            f"after migrating to pipelines.d/<id>.json (#143)")
    if legacy.exists():
        raise PipelineRegistryError(
            f"legacy {legacy} found — migrate to one file per pipeline under "
            f"{ddir}/<id>.json, then delete pipelines.json (#143)")
    if not ddir.is_dir():
        raise PipelineRegistryError(f"pipeline registry not found at {ddir}")

    pipelines = [_load_entry_file(p) for p in sorted(ddir.glob("*.json"))]
    if not pipelines:
        raise PipelineRegistryError(f"no pipeline files under {ddir}")

    seen: set[str] = set()
    for p in pipelines:
        if p.id in seen:
            raise PipelineRegistryError(f"duplicate pipeline id: {p.id!r}")
        seen.add(p.id)
        if not Path(p.root).exists():
            raise PipelineRegistryError(
                f"pipeline {p.id!r} root does not exist: {p.root}")
    return pipelines
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest ingestion/tests/test_pipeline_registry.py -q`
Expected: 11 passed. Then full non-live suite: `pytest -q` — expect all green (orchestrator consumes the same signatures).

- [ ] **Step 5: Commit**

```bash
git add ingestion/config/pipeline_registry.py ingestion/tests/test_pipeline_registry.py
git commit -m "feat(ingestion): #143 — pipelines.d per-pipeline registry loader (plugin model)"
```

---

### Task 2: Prod vault registry migration (operator, no commit — vault is not git)

**Files:**
- Create: `<vault>/KDB/state/pipelines.d/vault-in-place.json`
- Create: `<vault>/KDB/state/pipelines.d/gmail-substack.json`
- Create: `<vault>/KDB/raw/joseph-ft-public-gmail/` (empty dir)
- Delete: `<vault>/KDB/state/pipelines.json`

**Interfaces:**
- Consumes: Task 1's loader.
- Produces: the prod `gmail-substack` pipeline that Task 9's live gate and later `kdb-orchestrate --pipeline gmail-substack` rely on.

- [ ] **Step 1: Write the two pipeline files**

```bash
VAULT="/mnt/c/Users/fangq/Documents/Obsidian Vault"
mkdir -p "$VAULT/KDB/state/pipelines.d" "$VAULT/KDB/raw/joseph-ft-public-gmail"
cat > "$VAULT/KDB/state/pipelines.d/vault-in-place.json" <<'EOF'
{
  "id": "vault-in-place",
  "type": "in-place",
  "root": "/mnt/c/Users/fangq/Documents/Obsidian Vault",
  "excludes": ["KDB/", "Vault-in-place-test-run/", "__pycache__/", "prompt/"],
  "force_noise": ["Daily Notes/*"],
  "force_signal": [],
  "file_types": [".md"]
}
EOF
cat > "$VAULT/KDB/state/pipelines.d/gmail-substack.json" <<'EOF'
{
  "id": "gmail-substack",
  "type": "raw",
  "root": "/mnt/c/Users/fangq/Documents/Obsidian Vault/KDB/raw/joseph-ft-public-gmail",
  "excludes": [],
  "force_noise": [],
  "force_signal": [],
  "file_types": [".md"],
  "feeder": {"command": "kdb-gmail-fetch"}
}
EOF
```

- [ ] **Step 2: Remove the legacy file**

```bash
rm "$VAULT/KDB/state/pipelines.json"
```

- [ ] **Step 3: Verify the loader sees both pipelines**

Run (repo root, venv active):
```bash
python -c "from ingestion.config.pipeline_registry import list_pipelines; \
print(list_pipelines('/mnt/c/Users/fangq/Documents/Obsidian Vault/KDB/state'))"
```
Expected: `['gmail-substack', 'vault-in-place']`

(No commit — the vault is not under git.)

---

### Task 3: `GmailClient` — gws subprocess seam

**Files:**
- Create: `ingestion/feeder/gmail_client.py`
- Test: `ingestion/tests/test_gmail_client.py`

**Interfaces:**
- Consumes: the `gws` binary on PATH (auth already set up).
- Produces:
  - `GmailClientError(RuntimeError)`
  - `GmailClient(gws_bin: str = "gws", runner: Callable = subprocess.run)`
  - `GmailClient.resolve_label_ids() -> dict[str, str]` (label name → id)
  - `GmailClient.list_message_ids(label_name: str, *, max_messages: int | None = None) -> list[str]`
  - `GmailClient.get_message(message_id: str) -> dict` (format=full payload)
  - `GmailClient.modify_labels(message_id: str, *, add: list[str], remove: list[str]) -> None`

- [ ] **Step 1: Write the failing tests**

`ingestion/tests/test_gmail_client.py`:

```python
"""#143 — GmailClient seam tests (fake runner; no network)."""
import json
import subprocess

import pytest

from ingestion.feeder.gmail_client import GmailClient, GmailClientError


def _proc(payload: dict, rc: int = 0, stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=["gws"], returncode=rc, stdout=json.dumps(payload), stderr=stderr)


def _client(handler) -> GmailClient:
    def runner(cmd, **kwargs):
        return handler(cmd)
    return GmailClient(runner=runner)


def test_resolve_label_ids_maps_names():
    c = _client(lambda cmd: _proc({"labels": [
        {"id": "Label_1", "name": "Substack_raw", "type": "user"},
        {"id": "Label_2", "name": "Substack_ai_processed", "type": "user"}]}))
    assert c.resolve_label_ids() == {
        "Substack_raw": "Label_1", "Substack_ai_processed": "Label_2"}


def test_list_message_ids_paginates_until_no_token():
    pages = iter([
        {"messages": [{"id": "a"}, {"id": "b"}], "nextPageToken": "t2"},
        {"messages": [{"id": "c"}]},
    ])
    c = _client(lambda cmd: _proc(next(pages)))
    assert c.list_message_ids("Substack_raw") == ["a", "b", "c"]


def test_list_message_ids_caps_at_max():
    pages = iter([
        {"messages": [{"id": "a"}, {"id": "b"}], "nextPageToken": "t2"},
        {"messages": [{"id": "c"}]},
    ])
    c = _client(lambda cmd: _proc(next(pages)))
    assert c.list_message_ids("Substack_raw", max_messages=2) == ["a", "b"]


def test_list_message_ids_empty_label():
    c = _client(lambda cmd: _proc({"resultSizeEstimate": 0}))
    assert c.list_message_ids("Substack_raw") == []


def test_get_message_returns_payload():
    c = _client(lambda cmd: _proc({"id": "m1", "payload": {"headers": []}}))
    assert c.get_message("m1")["id"] == "m1"


def test_modify_labels_sends_add_and_remove():
    seen = {}

    def handler(cmd):
        seen["cmd"] = cmd
        return _proc({"id": "m1", "labelIds": ["Label_2"]})

    c = _client(handler)
    c.modify_labels("m1", add=["Label_2"], remove=["Label_1"])
    body = json.loads(seen["cmd"][seen["cmd"].index("--json") + 1])
    assert body == {"addLabelIds": ["Label_2"], "removeLabelIds": ["Label_1"]}


def test_nonzero_rc_raises():
    c = _client(lambda cmd: _proc({}, rc=1, stderr="auth expired"))
    with pytest.raises(GmailClientError, match="auth expired"):
        c.resolve_label_ids()


def test_unparseable_output_raises():
    def runner(cmd, **kwargs):
        return subprocess.CompletedProcess(args=cmd, returncode=0,
                                           stdout="not json", stderr="")
    with pytest.raises(GmailClientError, match="unparseable"):
        GmailClient(runner=runner).resolve_label_ids()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest ingestion/tests/test_gmail_client.py -q`
Expected: FAIL — `ModuleNotFoundError: ingestion.feeder.gmail_client`.

- [ ] **Step 3: Implement the seam**

`ingestion/feeder/gmail_client.py`:

```python
"""gmail_client — thin subprocess seam over the `gws gmail` CLI (#143).

Single responsibility: run gws, parse its JSON stdout. Extraction, dedup,
and label policy live elsewhere so tests inject a fake runner and never
touch the network. gws writes its keyring notice to stderr; stdout is JSON.
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import Callable

Runner = Callable[..., subprocess.CompletedProcess]


class GmailClientError(RuntimeError):
    """Raised on gws invocation failure or unparseable output."""


@dataclass
class GmailClient:
    gws_bin: str = "gws"
    runner: Runner = subprocess.run

    def _run_json(self, args: list[str]) -> dict:
        proc = self.runner([self.gws_bin, *args, "--format", "json"],
                           capture_output=True, text=True, timeout=120)
        if proc.returncode != 0:
            raise GmailClientError(
                f"gws {' '.join(args[:3])} failed (rc={proc.returncode}): "
                f"{proc.stderr.strip()[:300]}")
        try:
            return json.loads(proc.stdout)
        except json.JSONDecodeError as e:
            raise GmailClientError(
                f"unparseable gws output for {' '.join(args[:3])}: {e}") from e

    def resolve_label_ids(self) -> dict[str, str]:
        """Label name -> label id (all labels; caller picks the ones it needs)."""
        data = self._run_json(["gmail", "users", "labels", "list",
                               "--params", '{"userId": "me"}'])
        return {l["name"]: l["id"] for l in data.get("labels", [])}

    def list_message_ids(self, label_name: str,
                         *, max_messages: int | None = None) -> list[str]:
        """All message ids under `label_name` (paginated), capped at
        `max_messages` when given."""
        ids: list[str] = []
        token: str | None = None
        while True:
            params: dict = {"userId": "me", "q": f"label:{label_name}",
                            "maxResults": 500}
            if token:
                params["pageToken"] = token
            data = self._run_json(["gmail", "users", "messages", "list",
                                   "--params", json.dumps(params)])
            ids.extend(m["id"] for m in data.get("messages", []))
            if max_messages is not None and len(ids) >= max_messages:
                return ids[:max_messages]
            token = data.get("nextPageToken")
            if not token:
                return ids

    def get_message(self, message_id: str) -> dict:
        """format=full payload (headers + mime parts)."""
        return self._run_json(["gmail", "users", "messages", "get", "--params",
                               json.dumps({"userId": "me", "id": message_id,
                                           "format": "full"})])

    def modify_labels(self, message_id: str, *,
                      add: list[str], remove: list[str]) -> None:
        """The feeder's only Gmail write (D3): label move on success."""
        self._run_json([
            "gmail", "users", "messages", "modify",
            "--params", json.dumps({"userId": "me", "id": message_id}),
            "--json", json.dumps({"addLabelIds": add, "removeLabelIds": remove})])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest ingestion/tests/test_gmail_client.py -q`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add ingestion/feeder/gmail_client.py ingestion/tests/test_gmail_client.py
git commit -m "feat(feeder): #143 — GmailClient gws subprocess seam"
```

---

### Task 4: `gmail_extract` — payload → source parts

**Files:**
- Modify: `pyproject.toml` (add `markdownify` dep)
- Create: `ingestion/feeder/gmail_extract.py`
- Test: `ingestion/tests/test_gmail_extract.py`

**Interfaces:**
- Consumes: `markdownify` (new dep), `common.paths.slugify` (used by Task 6, not here).
- Produces:
  - `SourceParts` dataclass (frozen): `title: str`, `author: str`, `published_date: str` (ISO YYYY-MM-DD), `source_url: str | None`, `content_kind: str` (`"article" | "video" | "podcast"`), `body_markdown: str`
  - `extract(payload: dict) -> SourceParts` — the single entry Task 6 uses.

- [ ] **Step 1: Add the dependency and install**

In `pyproject.toml` `dependencies`, append after `"python-louvain>=0.16",`:
```toml
    "markdownify>=0.13",
```
Run: `pip install -e ".[dev]"` (venv active) — expected: markdownify installed.

- [ ] **Step 2: Write the failing tests**

`ingestion/tests/test_gmail_extract.py`:

```python
"""#143 — gmail_extract tests (synthetic format=full payloads)."""
import base64

from ingestion.feeder.gmail_extract import (
    author_of, canonical_url, content_kind, extract, headers_of,
    html_body, html_to_markdown, published_date_of, title_of)


def _b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


def _payload(html: str, *, subject="Test Post", sender="Jane Doe <jane@x.substack.com>",
             date="Sat, 09 Aug 2026 10:30:00 -0400") -> dict:
    return {
        "id": "m1",
        "payload": {
            "mimeType": "multipart/alternative",
            "headers": [
                {"name": "Subject", "value": subject},
                {"name": "From", "value": sender},
                {"name": "Date", "value": date},
            ],
            "parts": [
                {"mimeType": "text/plain", "body": {"data": _b64("plain")}},
                {"mimeType": "text/html", "body": {"data": _b64(html)}},
            ],
        },
    }


ARTICLE_HTML = (
    '<div><p>Hello <a href="https://janedoe.substack.com/p/my-big-thesis?'
    'utm_source=email&token=abc">read on the web</a></p>'
    '<p>Thesis body.</p>'
    '<p><a href="https://janedoe.substack.com/unsubscribe">Unsubscribe</a></p>'
    '<img src="https://track.example.com/pixel.gif"></div>')

VIDEO_HTML = (
    '<div><p>New episode</p>'
    '<a href="https://janedoe.substack.com/p/market-video">'
    '<img src="https://substackcdn.com/api/video/thumb.jpg"></a>'
    '<span>Watch on Substack</span></div>')


def test_headers_of_lowercases_names():
    h = headers_of(_payload(ARTICLE_HTML))
    assert h["subject"] == "Test Post" and "from" in h and "date" in h


def test_html_body_prefers_html_part():
    assert "Thesis body" in html_body(_payload(ARTICLE_HTML))


def test_canonical_url_strips_tracking():
    assert canonical_url(ARTICLE_HTML) == "https://janedoe.substack.com/p/my-big-thesis"


def test_canonical_url_none_when_absent():
    assert canonical_url("<p>no links here</p>") is None


def test_content_kind_video_detected():
    assert content_kind(VIDEO_HTML) == "video"


def test_content_kind_article_default():
    assert content_kind(ARTICLE_HTML) == "article"


def test_html_to_markdown_strips_footer_and_images():
    md = html_to_markdown(ARTICLE_HTML)
    assert "Thesis body" in md
    assert "unsubscribe" not in md.lower()
    assert "pixel.gif" not in md


def test_author_prefers_display_name():
    assert author_of(headers_of(_payload(ARTICLE_HTML))) == "Jane Doe"


def test_published_date_iso():
    assert published_date_of(headers_of(_payload(ARTICLE_HTML))) == "2026-08-09"


def test_title_strips_re_fwd():
    h = headers_of(_payload(ARTICLE_HTML, subject="Fwd: Re: Real Title"))
    assert title_of(h) == "Real Title"


def test_extract_full_article():
    parts = extract(_payload(ARTICLE_HTML))
    assert parts.title == "Test Post"
    assert parts.author == "Jane Doe"
    assert parts.published_date == "2026-08-09"
    assert parts.source_url == "https://janedoe.substack.com/p/my-big-thesis"
    assert parts.content_kind == "article"
    assert "Thesis body" in parts.body_markdown
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest ingestion/tests/test_gmail_extract.py -q`
Expected: FAIL — `ModuleNotFoundError: ingestion.feeder.gmail_extract`.

- [ ] **Step 4: Implement extraction**

`ingestion/feeder/gmail_extract.py`:

```python
"""gmail_extract — Gmail format=full payload -> source-doc parts (#143).

Deterministic: headers, HTML->markdown, canonical Substack URL, content_kind.
No LLM, no network. D2: nothing classificatory beyond best-effort
`content_kind` (article | video | podcast) — pass-1 enrich remains the single
classification authority.
"""
from __future__ import annotations

import base64
import email.utils
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from markdownify import markdownify


@dataclass(frozen=True)
class SourceParts:
    title: str
    author: str
    published_date: str          # ISO YYYY-MM-DD
    source_url: str | None       # canonical Substack post URL, else None
    content_kind: str            # "article" | "video" | "podcast"
    body_markdown: str


_SUBSTACK_POST_RE = re.compile(
    r"https://[a-z0-9][a-z0-9-]*\.substack\.com/p/[a-z0-9][a-z0-9-]*", re.I)
_FOOTER_MARKERS = ("unsubscribe", "manage your subscription",
                   "you're receiving this", "you are receiving this",
                   "view in browser", "read in browser")
_VIDEO_MARKERS = ("substack.com/api/video", "/api/v1/video",
                  "video-player", "watch on substack")
_PODCAST_MARKERS = ("substack podcast", "audio-player",
                    "listen on substack", "podcast.apple.com",
                    "open.spotify.com/episode")


def headers_of(payload: dict) -> dict[str, str]:
    raw = payload.get("payload", {}).get("headers", []) or []
    return {h.get("name", "").lower(): h.get("value", "") for h in raw}


def _decode_part(part: dict) -> str:
    data = part.get("body", {}).get("data")
    if not data:
        return ""
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded).decode("utf-8", errors="replace")


def html_body(payload: dict) -> str:
    """Prefer the first text/html part; fall back to text/plain; walk nested
    mime parts."""
    best_html, best_text = "", ""
    stack = [payload.get("payload", {})]
    while stack:
        part = stack.pop()
        mime = part.get("mimeType", "")
        if mime == "text/html" and not best_html:
            best_html = _decode_part(part)
        elif mime == "text/plain" and not best_text:
            best_text = _decode_part(part)
        stack.extend(part.get("parts", []) or [])
    return best_html or best_text


def canonical_url(html: str) -> str | None:
    """First substack /p/ link, tracking query stripped (regex never matches
    the query string)."""
    m = _SUBSTACK_POST_RE.search(html)
    return m.group(0) if m else None


def content_kind(html: str) -> str:
    low = html.lower()
    if any(m in low for m in _VIDEO_MARKERS):
        return "video"
    if any(m in low for m in _PODCAST_MARKERS):
        return "podcast"
    return "article"


def html_to_markdown(html: str) -> str:
    """markdownify, drop images (tracking pixels/button chrome), drop footer
    lines, collapse blank runs."""
    md = markdownify(html, strip=["img"])
    kept = [ln.rstrip() for ln in md.splitlines()
            if not any(m in ln.lower() for m in _FOOTER_MARKERS)]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()


def author_of(headers: dict[str, str]) -> str:
    name, addr = email.utils.parseaddr(headers.get("from", ""))
    return name.strip() or addr


def published_date_of(headers: dict[str, str]) -> str:
    try:
        dt = email.utils.parsedate_to_datetime(headers.get("date", ""))
    except (TypeError, ValueError):
        dt = None
    if dt is None:
        return datetime.now(timezone.utc).date().isoformat()
    return dt.date().isoformat()


def title_of(headers: dict[str, str]) -> str:
    return re.sub(r"^(?:(?:re|fwd?):\s*)+", "",
                  headers.get("subject", "").strip(), flags=re.I)


def extract(payload: dict) -> SourceParts:
    headers = headers_of(payload)
    html = html_body(payload)
    return SourceParts(
        title=title_of(headers),
        author=author_of(headers),
        published_date=published_date_of(headers),
        source_url=canonical_url(html),
        content_kind=content_kind(html),
        body_markdown=html_to_markdown(html),
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest ingestion/tests/test_gmail_extract.py -q`
Expected: 11 passed.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml ingestion/feeder/gmail_extract.py ingestion/tests/test_gmail_extract.py
git commit -m "feat(feeder): #143 — gmail_extract payload→source parts (+markdownify dep)"
```

---

### Task 5: Conversion journal

**Files:**
- Create: `ingestion/feeder/journal.py`
- Test: `ingestion/tests/test_feeder_journal.py`

**Interfaces:**
- Consumes: `common.atomic_io.atomic_write_text`.
- Produces:
  - `load_journal(path: Path | str) -> list[dict]` (missing file → `[]`)
  - `append_journal(path: Path | str, record: dict) -> None`
  - `seen_message_ids(records: list[dict]) -> set[str]`
  - `seen_urls(records: list[dict]) -> dict[str, str]` (source_url → filename; skips records without both)

- [ ] **Step 1: Write the failing tests**

`ingestion/tests/test_feeder_journal.py`:

```python
"""#143 — feeder conversion journal tests."""
from ingestion.feeder.journal import (
    append_journal, load_journal, seen_message_ids, seen_urls)


def test_load_missing_returns_empty(tmp_path):
    assert load_journal(tmp_path / "gmail.jsonl") == []


def test_append_then_load_roundtrip(tmp_path):
    p = tmp_path / "gmail.jsonl"
    append_journal(p, {"message_id": "m1", "source_url": "https://a.substack.com/p/x",
                       "filename": "x.md", "outcome": "converted"})
    append_journal(p, {"message_id": "m2", "source_url": None, "filename": None,
                       "outcome": "dedup", "dedup_of": "x.md"})
    records = load_journal(p)
    assert len(records) == 2
    assert records[0]["message_id"] == "m1"
    assert records[1]["dedup_of"] == "x.md"


def test_append_preserves_prior_lines(tmp_path):
    p = tmp_path / "gmail.jsonl"
    append_journal(p, {"message_id": "m1"})
    append_journal(p, {"message_id": "m2"})
    assert [r["message_id"] for r in load_journal(p)] == ["m1", "m2"]


def test_seen_message_ids(tmp_path):
    records = [{"message_id": "m1"}, {"message_id": "m2"}]
    assert seen_message_ids(records) == {"m1", "m2"}


def test_seen_urls_skips_incomplete_records():
    records = [
        {"source_url": "https://a.substack.com/p/x", "filename": "x.md"},
        {"source_url": None, "filename": None},
        {"source_url": "https://a.substack.com/p/y"},
    ]
    assert seen_urls(records) == {"https://a.substack.com/p/x": "x.md"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest ingestion/tests/test_feeder_journal.py -q`
Expected: FAIL — `ModuleNotFoundError: ingestion.feeder.journal`.

- [ ] **Step 3: Implement the journal**

`ingestion/feeder/journal.py`:

```python
"""journal — append-only feeder conversion journal (#143 D4).

One JSONL line per processed message at
`<vault>/KDB/state/feeders/gmail.jsonl`. Small file, single process (D22):
read-all + atomic rewrite on append. Audit + dedup-by-canonical-URL only —
this is not an ingestion ledger (the Gmail label is the processed-state).
"""
from __future__ import annotations

import json
from pathlib import Path

from common.atomic_io import atomic_write_text


def load_journal(path: Path | str) -> list[dict]:
    p = Path(path)
    if not p.exists():
        return []
    return [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines()
            if ln.strip()]


def append_journal(path: Path | str, record: dict) -> None:
    p = Path(path)
    prior = p.read_text(encoding="utf-8") if p.exists() else ""
    atomic_write_text(p, prior + json.dumps(record, ensure_ascii=False) + "\n")


def seen_message_ids(records: list[dict]) -> set[str]:
    return {r["message_id"] for r in records if "message_id" in r}


def seen_urls(records: list[dict]) -> dict[str, str]:
    """source_url -> filename for converted records (dedup-by-canonical-URL)."""
    return {r["source_url"]: r["filename"] for r in records
            if r.get("source_url") and r.get("filename")}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest ingestion/tests/test_feeder_journal.py -q`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add ingestion/feeder/journal.py ingestion/tests/test_feeder_journal.py
git commit -m "feat(feeder): #143 — append-only conversion journal"
```

---

### Task 6: Feeder core — `fetch()` flow

**Files:**
- Create: `ingestion/feeder/gmail.py`
- Test: `ingestion/tests/test_feeder_gmail.py`

**Interfaces:**
- Consumes: Task 3 (`GmailClient`, `GmailClientError`), Task 4 (`extract`, `SourceParts`), Task 5 (`journal` module), `common.atomic_io.atomic_write_text`, `common.paths.slugify`/`kdb_root`.
- Produces:
  - Constants: `DEFAULT_LABEL = "Substack_raw"`, `PROCESSED_LABEL = "Substack_ai_processed"`, `RAW_SUBDIR = Path("raw") / "joseph-ft-public-gmail"`, `JOURNAL_REL = Path("state") / "feeders" / "gmail.jsonl"`
  - `FetchSummary` dataclass: `converted/skipped/dedup/failed: int`, `failures: list[tuple[str, str]]`
  - `fetch(*, client, raw_dir, journal_path, label=DEFAULT_LABEL, processed_label=PROCESSED_LABEL, max_messages=None, dry_run=False, out=sys.stdout) -> FetchSummary`
  - `main(argv: list[str] | None = None) -> int` (Task 7 wires the entry point)

- [ ] **Step 1: Write the failing tests**

`ingestion/tests/test_feeder_gmail.py`:

```python
"""#143 — feeder fetch() flow tests (fake client; tmp dirs)."""
import base64

import pytest
import yaml

from ingestion.feeder.gmail import DEFAULT_LABEL, fetch
from ingestion.feeder.gmail_client import GmailClientError


def _b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


def _payload(mid: str, url: str, *, subject: str | None = None) -> dict:
    html = f'<p>Body for {mid} <a href="{url}">web</a></p>'
    return {"id": mid, "payload": {
        "headers": [
            {"name": "Subject", "value": subject or f"Post {mid}"},
            {"name": "From", "value": "Jane Doe <jane@x.substack.com>"},
            {"name": "Date", "value": "Sat, 09 Aug 2026 10:30:00 -0400"},
        ],
        "parts": [{"mimeType": "text/html", "body": {"data": _b64(html)}}],
    }}


class FakeClient:
    def __init__(self, payloads: dict, fail_on: set = ()):  # mid -> payload
        self.payloads = payloads
        self.fail_on = fail_on
        self.moved: list[tuple[str, list, list]] = []

    def resolve_label_ids(self):
        return {DEFAULT_LABEL: "LR", "Substack_ai_processed": "LP"}

    def list_message_ids(self, label, *, max_messages=None):
        ids = list(self.payloads)
        return ids[:max_messages] if max_messages else ids

    def get_message(self, mid):
        if mid in self.fail_on:
            raise GmailClientError(f"boom {mid}")
        return self.payloads[mid]

    def modify_labels(self, mid, *, add, remove):
        self.moved.append((mid, add, remove))


def _run(client, tmp_path, **kwargs):
    return fetch(client=client, raw_dir=tmp_path / "raw",
                 journal_path=tmp_path / "state" / "feeders" / "gmail.jsonl",
                 **kwargs)


def test_converts_writes_source_moves_label_journals(tmp_path):
    c = FakeClient({"m1": _payload("m1", "https://a.substack.com/p/x")})
    s = _run(c, tmp_path)
    assert (s.converted, s.failed) == (1, 0)
    files = list((tmp_path / "raw").glob("*.md"))
    assert len(files) == 1
    text = files[0].read_text(encoding="utf-8")
    fm = yaml.safe_load(text.split("---\n")[1])
    assert fm["gmail_message_id"] == "m1"
    assert fm["source_url"] == "https://a.substack.com/p/x"
    assert fm["feeder"] == "gmail-substack"
    assert fm["content_kind"] == "article"
    assert "domain" not in fm and "source_type" not in fm   # D2
    assert c.moved == [("m1", ["LP"], ["LR"])]
    assert (tmp_path / "state" / "feeders" / "gmail.jsonl").exists()


def test_rerun_skips_journaled_messages(tmp_path):
    payloads = {"m1": _payload("m1", "https://a.substack.com/p/x")}
    _run(FakeClient(payloads), tmp_path)
    c2 = FakeClient(payloads)
    s = _run(c2, tmp_path)
    assert (s.converted, s.skipped) == (0, 1)
    assert c2.moved == []


def test_dedup_by_canonical_url_no_second_file_but_labels_move(tmp_path):
    payloads = {"m1": _payload("m1", "https://a.substack.com/p/x"),
                "m2": _payload("m2", "https://a.substack.com/p/x")}
    c = FakeClient(payloads)
    s = _run(c, tmp_path)
    assert (s.converted, s.dedup) == (1, 1)
    assert len(list((tmp_path / "raw").glob("*.md"))) == 1
    assert sorted(m[0] for m in c.moved) == ["m1", "m2"]


def test_per_message_failure_isolated_and_stays_unlabeled(tmp_path):
    payloads = {"m1": _payload("m1", "https://a.substack.com/p/x"),
                "m2": _payload("m2", "https://a.substack.com/p/y")}
    c = FakeClient(payloads, fail_on={"m2"})
    s = _run(c, tmp_path)
    assert (s.converted, s.failed) == (1, 1)
    assert s.failures[0][0] == "m2"
    assert [m[0] for m in c.moved] == ["m1"]


def test_dry_run_zero_side_effects(tmp_path):
    c = FakeClient({"m1": _payload("m1", "https://a.substack.com/p/x")})
    _run(c, tmp_path, dry_run=True)
    assert not (tmp_path / "raw").exists() or not list((tmp_path / "raw").glob("*.md"))
    assert not (tmp_path / "state").exists()
    assert c.moved == []


def test_max_messages_caps(tmp_path):
    payloads = {f"m{i}": _payload(f"m{i}", f"https://a.substack.com/p/{i}")
                for i in range(5)}
    s = _run(FakeClient(payloads), tmp_path, max_messages=2)
    assert s.converted == 2


def test_missing_label_raises(tmp_path):
    class NoLabels(FakeClient):
        def resolve_label_ids(self):
            return {}
    with pytest.raises(GmailClientError, match="label not found"):
        _run(NoLabels({}), tmp_path)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest ingestion/tests/test_feeder_gmail.py -q`
Expected: FAIL — `ModuleNotFoundError: ingestion.feeder.gmail`.

- [ ] **Step 3: Implement the feeder core**

`ingestion/feeder/gmail.py`:

```python
"""gmail — the gmail-substack feeder: Gmail label -> KDB raw sources (#143).

Flow (spec §3.2): list -> journal-skip -> get -> extract -> dedup -> write
-> label move -> journal append. Deterministic (D1): no LLM anywhere.
Per-message failures are isolated: the message stays in the raw label and
lands in the summary, the batch continues.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TextIO

import yaml

from common.atomic_io import atomic_write_text
from common.paths import kdb_root, slugify

from ingestion.feeder import journal as jrnl
from ingestion.feeder.gmail_client import GmailClient, GmailClientError
from ingestion.feeder.gmail_extract import extract

DEFAULT_LABEL = "Substack_raw"
PROCESSED_LABEL = "Substack_ai_processed"
RAW_SUBDIR = Path("raw") / "joseph-ft-public-gmail"
JOURNAL_REL = Path("state") / "feeders" / "gmail.jsonl"


@dataclass
class FetchSummary:
    converted: int = 0
    skipped: int = 0
    dedup: int = 0
    failed: int = 0
    failures: list[tuple[str, str]] = field(default_factory=list)


def _render_source(parts, *, message_id: str, ingested_at: str) -> str:
    """D2 frontmatter contract + extracted body."""
    fm = yaml.safe_dump(
        {"title": parts.title,
         "author": parts.author,
         "published_date": parts.published_date,
         "source_url": parts.source_url,
         "gmail_message_id": message_id,
         "content_kind": parts.content_kind,
         "feeder": "gmail-substack",
         "ingested_at": ingested_at},
        sort_keys=False, allow_unicode=True)
    return f"---\n{fm}---\n\n{parts.body_markdown}\n"


def _target_path(raw_dir: Path, title: str, message_id: str) -> Path:
    base = slugify(title)
    path = raw_dir / f"{base}.md"
    if path.exists():
        path = raw_dir / f"{base}-{message_id[:8]}.md"
    return path


def fetch(*, client: GmailClient, raw_dir: Path, journal_path: Path,
          label: str = DEFAULT_LABEL, processed_label: str = PROCESSED_LABEL,
          max_messages: int | None = None, dry_run: bool = False,
          out: TextIO = sys.stdout) -> FetchSummary:
    summary = FetchSummary()
    records = jrnl.load_journal(journal_path)
    seen_ids = jrnl.seen_message_ids(records)
    seen_urls = jrnl.seen_urls(records)

    label_ids = client.resolve_label_ids()
    for name in (label, processed_label):
        if name not in label_ids:
            raise GmailClientError(f"Gmail label not found: {name!r}")

    for mid in client.list_message_ids(label, max_messages=max_messages):
        if mid in seen_ids:
            summary.skipped += 1
            continue
        try:
            parts = extract(client.get_message(mid))
            now = datetime.now(timezone.utc).isoformat(timespec="seconds")
            dedup_of = (seen_urls.get(parts.source_url)
                        if parts.source_url else None)
            if dry_run:
                tag = "dedup" if dedup_of else "convert"
                print(f"[dry-run] {tag}: {parts.title!r} "
                      f"<{parts.source_url}> ({parts.content_kind})", file=out)
                continue
            if dedup_of:
                record = {"message_id": mid, "source_url": parts.source_url,
                          "filename": None, "dedup_of": dedup_of,
                          "ingested_at": now, "outcome": "dedup"}
                summary.dedup += 1
            else:
                target = _target_path(raw_dir, parts.title, mid)
                atomic_write_text(target, _render_source(
                    parts, message_id=mid, ingested_at=now))
                record = {"message_id": mid, "source_url": parts.source_url,
                          "filename": target.name, "ingested_at": now,
                          "outcome": "converted"}
                if parts.source_url:
                    seen_urls[parts.source_url] = target.name
                summary.converted += 1
            # D3: the feeder's only Gmail write — move out of the raw queue.
            client.modify_labels(mid, add=[label_ids[processed_label]],
                                 remove=[label_ids[label]])
            jrnl.append_journal(journal_path, record)
        except Exception as e:      # per-message isolation; stays in raw label
            summary.failed += 1
            summary.failures.append((mid, str(e)))
            print(f"failed: {mid}: {e}", file=out)
    return summary


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="kdb-gmail-fetch",
        description="#143 gmail-substack feeder: convert Substack_raw emails "
                    "to KDB raw sources, move them to Substack_ai_processed.")
    p.add_argument("--max", type=int, default=None, dest="max_messages",
                   help="cap messages processed (slice-first backlog, D8)")
    p.add_argument("--dry-run", action="store_true",
                   help="print planned conversions; no writes/labels/journal")
    p.add_argument("--label", default=DEFAULT_LABEL)
    p.add_argument("--processed-label", default=PROCESSED_LABEL)
    p.add_argument("--raw-dir", type=Path, default=kdb_root() / RAW_SUBDIR)
    p.add_argument("--journal", type=Path, default=kdb_root() / JOURNAL_REL)
    args = p.parse_args(argv)
    try:
        summary = fetch(client=GmailClient(), raw_dir=args.raw_dir,
                        journal_path=args.journal, label=args.label,
                        processed_label=args.processed_label,
                        max_messages=args.max_messages, dry_run=args.dry_run)
    except GmailClientError as e:
        print(f"kdb-gmail-fetch: {e}", file=sys.stderr)
        return 2
    print(f"converted {summary.converted} · dedup {summary.dedup} · "
          f"skipped {summary.skipped} · failed {summary.failed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest ingestion/tests/test_feeder_gmail.py -q`
Expected: 7 passed. Then full suite: `pytest -q` (boundary guard included) — all green.

- [ ] **Step 5: Commit**

```bash
git add ingestion/feeder/gmail.py ingestion/tests/test_feeder_gmail.py
git commit -m "feat(feeder): #143 — fetch flow (extract→dedup→write→label-move→journal)"
```

---

### Task 7: `kdb-gmail-fetch` entry point

**Files:**
- Modify: `pyproject.toml` ([project.scripts])
- Test: `ingestion/tests/test_feeder_gmail.py` (append CLI smoke test)

**Interfaces:**
- Consumes: Task 6 `main`.
- Produces: shell command `kdb-gmail-fetch`.

- [ ] **Step 1: Write the failing test**

Append to `ingestion/tests/test_feeder_gmail.py`:

```python
def test_cli_dry_run_smoke(tmp_path, capsys, monkeypatch):
    from ingestion.feeder import gmail as feeder

    class StubClient:
        def resolve_label_ids(self):
            return {DEFAULT_LABEL: "LR", "Substack_ai_processed": "LP"}

        def list_message_ids(self, label, *, max_messages=None):
            return []

        def get_message(self, mid):
            raise AssertionError("no messages expected")

        def modify_labels(self, mid, *, add, remove):
            raise AssertionError("no writes expected")

    monkeypatch.setattr(feeder, "GmailClient", lambda: StubClient())
    rc = feeder.main(["--dry-run", "--raw-dir", str(tmp_path / "raw"),
                      "--journal", str(tmp_path / "j" / "gmail.jsonl")])
    assert rc == 0
    assert "converted 0" in capsys.readouterr().out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest ingestion/tests/test_feeder_gmail.py::test_cli_dry_run_smoke -q`
Expected: FAIL — `main` exists but the `GmailClient` symbol is imported as the class; the monkeypatch target works only after Step 3 adds the entry point (test actually passes already) — the real FAIL gate is the shell smoke in Step 4: `kdb-gmail-fetch: command not found`.

- [ ] **Step 3: Add the entry point**

In `pyproject.toml` `[project.scripts]`, after `kdb-enrich` line:
```toml
kdb-gmail-fetch       = "ingestion.feeder.gmail:main"
```
Run: `pip install -e ".[dev]"`

- [ ] **Step 4: Verify**

Run: `pytest ingestion/tests/test_feeder_gmail.py -q` — 8 passed.
Run: `kdb-gmail-fetch --help` — prints usage with `--max`, `--dry-run`, `--label`.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml ingestion/tests/test_feeder_gmail.py
git commit -m "feat(feeder): #143 — kdb-gmail-fetch entry point"
```

---

### Task 8: Docs (North Star + AGENTS.md + ledger note)

**Files:**
- Modify: `docs/CODEBASE_OVERVIEW.md` (structure section — feeder + pipelines.d)
- Modify: `AGENTS.md` (entry points list + ingestion/feeder comment + pipelines.d config note)
- Modify: `docs/TASKS.md` (#143 row: progress note)

**Interfaces:** none (docs only).

- [ ] **Step 1: Update `AGENTS.md`**

- Project Structure, `ingestion/` block: change the `feeder/` comment to
  `# Gmail/Substack feeder (#143): gmail_client (gws seam) / gmail_extract / journal / gmail flow`.
- Entry points: add `kdb-gmail-fetch        # Feeder: Substack_raw Gmail label → KDB/raw sources, label-move to processed`.
- Environment & Configuration: after the Paths bullet, add one line: `Pipeline registry: one file per pipeline under <vault>/KDB/state/pipelines.d/<id>.json (#143; legacy pipelines.json removed).`

- [ ] **Step 2: Update `docs/CODEBASE_OVERVIEW.md`**

In the structure section, mirror the same two lines (feeder package contents; pipelines.d registry layout). Milestone Changelog entry lands at task closure (per convention), not in this task.

- [ ] **Step 3: Update `docs/TASKS.md`**

Append to the #143 row's notes: `**Implementation 2026-08-09:** plan `docs/superpowers/plans/2026-08-09-task143-gmail-ingestion-pipeline.md` executed Tasks 1–7 (registry loader, prod migration, GmailClient seam, extraction, journal, fetch flow, CLI) — live gate (Task 9) pending.`

- [ ] **Step 4: Commit**

```bash
git add AGENTS.md docs/CODEBASE_OVERVIEW.md docs/TASKS.md
git commit -m "docs: #143 — feeder + pipelines.d in North Star/AGENTS; ledger progress note"
```

---

### Task 9: Live gate — slice-first validation (operator, Joseph-visible)

**Files:** none (operator runbook; results reported to Joseph).

**Interfaces:**
- Consumes: Tasks 1–7 + prod migration (Task 2).
- Produces: Joseph's go/no-go for the chunked backlog.

- [ ] **Step 1: Dry-run preview of 5**

Run: `kdb-gmail-fetch --max 5 --dry-run`
Expected: five `[dry-run] convert: '<title>' <url> (article)` lines (or `dedup`); zero side effects.

- [ ] **Step 2: Real slice of 5**

Run: `kdb-gmail-fetch --max 5`
Expected: `converted 5 · dedup 0 · skipped 0 · failed 0` (dedup/skipped may be non-zero on repeats — that's correct behavior).

- [ ] **Step 3: Eyeball gate (Joseph)**

```bash
ls "/mnt/c/Users/fangq/Documents/Obsidian Vault/KDB/raw/joseph-ft-public-gmail"
```
- Open 1–2 sources: frontmatter D2-complete, body readable, no boilerplate stink.
- Gmail UI: the 5 messages moved `Substack_raw` → `Substack_ai_processed`.
- Journal: `cat "/mnt/c/Users/fangq/Documents/Obsidian Vault/KDB/state/feeders/gmail.jsonl"`.

- [ ] **Step 4: Queue-drain check (not a no-op check)**

Run: `kdb-gmail-fetch --max 5 --dry-run`
Expected: five **new** `[dry-run] convert` lines (the next slice of the self-draining queue) — NOT repeats of the first five. Combined with the Step-3 Gmail UI check, this proves the label-move state works. (Journal id-skip is the belt for re-processing the same id; covered by unit tests — the label is the primary state.)

- [ ] **Step 5: Slice of 25, then STOP for Joseph's backlog decision**

Run: `kdb-gmail-fetch --max 25`
Report extraction quality to Joseph. The full ~3.9k backlog proceeds chunked (e.g. `--max 100` per run) only at his go. Compiling the new sources (`kdb-orchestrate --pipeline gmail-substack`) is likewise a separate, gated decision.

---

## Self-review record

- **Spec coverage:** D1→Tasks 3–7 (code module, no LLM); D2→Task 6 `_render_source` + `test_converts_…` (no domain/source_type asserted); D3→Tasks 3/6 (modify-labels move); D4→Task 5 + dedup path; D5→Task 2 (raw dir + pipeline entry); D6→Tasks 1–2; D7→Task 4 `content_kind` (+ compile-pipeline noise path per spec §3.3, no code); D8→Task 9 (slice-first); D9→single plan, both workstreams.
- **Placeholders:** none — every code step carries complete code.
- **Type consistency:** `GmailClient` methods match Task 3's interface block and Task 6's usage; `SourceParts` fields match `_render_source`; journal helpers match Task 6's call sites (`jrnl.load_journal/seen_message_ids/seen_urls/append_journal`).

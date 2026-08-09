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

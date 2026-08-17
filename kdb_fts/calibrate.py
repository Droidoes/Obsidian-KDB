"""calibrate — gate precision/recall against Joseph's labels (§9 Phase-1 gate).

Label-relevant = latest bucket in {strong, interesting}; gate-relevant =
latest verdict topic in {investment, finance-econ}. Joseph sets the accept
threshold AFTER seeing this matrix — no invented number lives here.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from kdb_fts import feedback, ledger

RELEVANT_TOPICS = frozenset({"investment", "finance-econ"})
POSITIVE_ACTIONS = frozenset({"strong", "interesting"})
_BUCKET_ACTIONS = frozenset({"strong", "interesting", "weak", "noise"})


def report(conn: sqlite3.Connection, root: Path, batch_id: str) -> dict:
    latest_label: dict[str, str] = {}
    for e in feedback.load_events(root, batch_id=batch_id):
        if e["target_type"] == "article" and e["action"] in _BUCKET_ACTIONS:
            latest_label[e["target_id"]] = e["action"]  # file order = ts order
    verdicts = {v["article_id"]: v for v in ledger.latest_verdicts(conn)}
    confusion = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
    by_topic: dict[str, dict[str, int]] = {}
    for article_id, action in sorted(latest_label.items()):
        v = verdicts.get(article_id)
        if v is None:
            continue
        gate_pos = v["topic"] in RELEVANT_TOPICS
        label_pos = action in POSITIVE_ACTIONS
        key = ("tp" if gate_pos else "fn") if label_pos else ("fp" if gate_pos else "tn")
        confusion[key] += 1
        bucket = by_topic.setdefault(v["topic"], {"pos": 0, "neg": 0})
        bucket["pos" if label_pos else "neg"] += 1
    tp, fp, fn, tn = (confusion[k] for k in ("tp", "fp", "fn", "tn"))
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = (2 * precision * recall / (precision + recall)
          if precision and recall else (0.0 if precision == 0.0 or recall == 0.0 else None))
    return {"batch_id": batch_id, "labeled": len(latest_label),
            "confusion": confusion, "precision": precision,
            "recall": recall, "f1": f1, "by_topic": by_topic}

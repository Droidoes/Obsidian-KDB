# Session handoff — 2026-08-08

> Richest single catch-up artifact for the next session. Top-level so `session-catchup` finds it by mtime.

## ✅ POSTSCRIPT (2026-08-08, 15:45 EDT) — RUN COMPLETE; this handoff is now HISTORICAL

- **The maiden run completed 15:26 EDT** (`2026-08-08T14-39-10_EDT`, exit `completed_with_quarantines`) after 5 attempts / 4 VM crashes. Final: **1,149 sources in graph (== manifest, verified), 6,197 entities, 12,843 LINKS_TO, 450 noise, 2 quarantined** (auto-requeue next run).
- **§1a attempt-3 remediation: DECLINED by Joseph 2026-08-08 — mixed-model vault RATIFIED.** *"I wouldn't call deepseek process the files contaminated… we'll keep them as-is… there is no issue with future runs, it's unlikely we'll do another cold run again… there is no mandate that 'a run' has to be on one model."* The 103 deepseek-compiled `in_graph_db` sources (+ 91 noise classifications) are **treated as normal** — no remediation arises. Rationale on record: (1) deepseek output is not contamination; (2) no future-run issue — a full cold run is unlikely to recur, so mixed provenance never re-opens; (3) no single-model mandate for a run — per-source model provenance lives in the manifest (`last_run_id`) and is queryable, which is sufficient. **Supersedes the #118-era "mixed-model vault not acceptable" precedent** — that ruling scoped to benchmark-cohort comparability, not production-vault correctness. Also recorded in daily note 2026-08-08 → Decisions. The §1a procedure below is retained as reference only — **do not fire it**.
- **§2 WSL stabilization: EXECUTED 2026-08-08 ~15:42** — `.wslconfig` reverted (`networkingMode=mirrored` + `autoMemoryReclaim=Gradual` commented out → NAT + disabled defaults), `wsl --shutdown` fired. Now in the **observation period** (§2 step 3): watch `last -xF | head -30` for crash-reboot cycles over the next several days. If crashes recur, suspect is WSL 2.7.11-or-deeper (§2 step 4).
- **Open dispositions for the next run:** (a) `Sample-Prompt-Pass-1.md` quarantine → candidate for `force_noise` (synthetic project artifact, not knowledge content); (b) `Buffett_on_Stock_Ownership.md` quarantine → Pass-1 deterministically emits `source_type: 'quotes'`, not in the controlled vocabulary — vocab decision needed (`other` vs new type vs prompt guidance). Both auto-requeue.
- Everything below the line is the pre-completion record — kept for forensics, resume procedure no longer needed.

---

## ⏩ MAIDEN VAULT RUN IN FLIGHT — resumed 09:48 EDT after two WSL VM crash kills; expected to crash at least once more before completing. Resume procedure below — do NOT wipe, do NOT restart from zero.

The first full-vault `kdb-orchestrate` run (1,600 in-scope sources, pipeline `vault-in-place`)
has been killed twice by the host environment (not by the pipeline). It is resumable by design
and was resumed at 09:48 EDT with 468 sources remaining. The WSL VM is unstable (see §2) and
may kill it again. **Recovery is always the same: re-run the same command. Never `--wipe`.**

---

## 1. RUN STATE AT HANDOFF

- **Active process**: `kdb-orchestrate --vault-root "/mnt/c/Users/fangq/Documents/Obsidian Vault" --pipeline vault-in-place --model gpt-5.4-mini`,
  launched detached (`nohup` + `disown`) at 11:58 EDT (attempt 4, run id
  `2026-08-08T11-58-09_EDT`), log at **`/tmp/kdb-orchestrate-resume.log`**.
  **`--model gpt-5.4-mini` is REQUIRED** — the CLI default is deepseek-v4-flash, which is
  what contaminated attempt 3 (see §1a). Check liveness: `pgrep -f kdb-orchestrate`; check
  progress: `tail -5` the log (`[NNN/273]` lines).
  NOTE: `/tmp` dies with the WSL VM — after a VM crash the log is gone; use the manifest to
  re-derive state (§3).
- **A 30-min cron monitor** (id `01KZH1M91GD6GY1HCWF6CV7J53`) exists in the session that started
  this run — cron tasks do NOT survive into a new session; a future session should re-create one
  or check the log manually.
- **History**: wipe fired 2026-08-07 14:11 (`--wipe`, 52 run dirs archived to
  `state/pre-wipe-runs/2026-08-07T14-11-43_EDT`). Attempt 1 (run `2026-08-07T14-11-55_EDT`)
  committed 778 sources (564 graph + 214 noise), killed 18:37. Attempt 2 (`2026-08-07T19-12-17_EDT`)
  committed 354 (258 graph + 96 noise), killed 21:58. Both used **gpt-5.4-mini** for Pass-1,
  pass-1.5 selector, and Pass-2. Attempt 3 (run `2026-08-08T09-43-05_EDT`, 09:43–11:58) ran with
  the WRONG model — see §1a. Attempt 4 (resumed 11:58, gpt-5.4-mini verified in pass-1 artifacts)
  carries the remaining ~273.
- **Consistency is verified good**: graph `sources` == manifest `in_graph_db` count; per-source
  commit boundary (manifest write LAST) held across every kill. The one in-flight source at each
  kill was never committed and is simply recompiled as CHANGED.
- **Repo state**: `main` is clean of code changes; uncommitted benchmark leaderboard + docs
  modifications predate this session (score/docs residue — owner's call, unrelated to the run).

### 1a. ATTEMPT-3 WRONG-MODEL INCIDENT + REMEDIATION (**DECLINED 2026-08-08 — see POSTSCRIPT; kept as-is, procedure below is reference only**)

Attempt 3 (09:43–11:58) was launched with CLI defaults — **deepseek-v4-flash** for Pass-1,
pass-1.5 selector, and Pass-2 — instead of gpt-5.4-mini. Caught by the owner at ~184 sources in;
killed mid-pass-2 (commit boundary held). Contaminated batch
(`last_run_id == "2026-08-08T09-43-05_EDT"` in the manifest):

- **103 `in_graph_db`** — wiki pages + graph rows built by the wrong model. MUST be recompiled
  (project precedent: #118 declined split-model runs — a mixed-model vault is not acceptable).
- 91 `no_graph_db` — noise classifications; only artifact is the deepseek enrich frontmatter
  (`model:` field). No wiki/graph content derives from them; owner decides whether strict
  consistency is worth re-enriching.
- 1 `error_ingest` — pass-1 failure; `last_compiled_hash` never advanced, so it is re-queued
  automatically. No action needed.

**Remediation procedure (after attempt 4 completes — owner's call to fire):**
```bash
# backup first, then null last_compiled_hash for the 103 so the next scan sees CHANGED
cp ~/Obsidian/KDB/state/manifest.json ~/Obsidian/KDB/state/manifest.json.bak-pre-103-remediation
python3 - <<'EOF'
import json, pathlib
p = pathlib.home()/'Obsidian/KDB/state/manifest.json'
m = json.loads(p.read_text())
n = 0
for s in m['sources'].values():
    if s.get('last_run_id') == '2026-08-08T09-43-05_EDT' and s.get('run_state') == 'in_graph_db':
        s['last_compiled_hash'] = None
        n += 1
p.write_text(json.dumps(m, indent=1))
print('nulled', n)
EOF
# then re-run the same orchestrate command (with --model gpt-5.4-mini); the 103 recompile and
# their pages/graph rows are replaced via the normal per-source commit path.
```

## 2. ROOT CAUSE OF THE CRASHES (forensics summary)

**The WSL2 VM is kernel-panicking and instantly rebooting (`panic=-1` on the cmdline), killing
all terminal sessions without warning.** It is NOT Windows Terminal, NOT a Windows update/sleep,
NOT the pipeline:

- Windows event logs: no Terminal/app crashes, no reboots, no power events at either kill time;
  battery report proves no real sleep on 2026-08-07 evening.
- `/var/log/wtmp`: VM uptime was 6d21h stable (Jul 31 → Aug 7 18:42), then **crash-reboot
  loops every ~15 s** — 373+ cycles: 18:42–19:03, again 01:57–02:04, again 09:29–09:31 (this
  morning). Attempt 2's VM stayed up 19:03→23:06 while its process died 21:58 (unrecorded
  panic or in-VM process kill; journals of those boots are volatile and were destroyed by the
  crash loops).
- systemd at the current boot: `journal ... corrupted or uncleanly shut down` — confirms
  unclean VM deaths.
- Prime suspects: experimental `.wslconfig` options `networkingMode=mirrored` and
  `autoMemoryReclaim=Gradual` under the first sustained hours-long network + `/mnt/c` I/O load
  this box has run. Unproven — no panic stack survived.

**Post-run actions (owner, after the maiden run completes — full rationale in vault note
`PC-WSL-Ubuntu-Linux-Git/WSL2 VM crash-reboot loops kill terminal sessions (2026-08-07).md`):**
1. `wsl --update` first (current: WSL 2.7.11 / kernel 6.18.33.2, installed 2026-07-27 — 11 days
   before the first crash, co-suspect alongside config).
2. Revert `.wslconfig`: remove `networkingMode=mirrored` (back to NAT) and the whole
   `[experimental]` `autoMemoryReclaim` block; `wsl --shutdown`. Both at once — neither option
   is load-bearing, so skip one-at-a-time attribution.
3. Observe for several days (`last -xF | head -30` for boot-loop cycles after long sessions).
   Only re-add mirrored alone if its ergonomics are genuinely missed.
4. If crashes persist: config exonerated; suspect is WSL 2.7.11-or-deeper. Enable persistent
   WSL crash dumps and file a WSL GitHub issue with the wtmp boot-loop evidence.

## 3. RESUME PROCEDURE (after the next crash)

```bash
cd ~/Droidoes/Obsidian-KDB && source .venv/bin/activate
# 1. sanity: what does the scan think remains? (no API calls, no graph mutation)
kdb-orchestrate --vault-root "/mnt/c/Users/fangq/Documents/Obsidian Vault" \
  --pipeline vault-in-place --dry-run --quiet
# 2. resume, detached so a terminal/VM death doesn't kill it
#    (--model gpt-5.4-mini is REQUIRED — CLI default is deepseek-v4-flash, wrong for this vault)
nohup kdb-orchestrate --vault-root "/mnt/c/Users/fangq/Documents/Obsidian Vault" \
  --pipeline vault-in-place --model gpt-5.4-mini > /tmp/kdb-orchestrate-resume.log 2>&1 & disown
```

- Resume semantics (verified in code): compile eligibility is
  `current_hash != last_compiled_hash` (`ingestion/kdb_scan.py:375`). Committed sources skip;
  the mid-flight source at kill time shows CHANGED (pass-1 embed mutated its file, manifest
  never updated) and is recompiled whole. Noise sources (`run_state=no_graph_db`, 310 so far)
  are deliberately terminal — never reprocessed.
- Cross-check after a crash: `graphdb-kdb --graph-dir "<vault>/KDB/graph" stats` — `sources`
  must equal the manifest's `in_graph_db` count:
  ```bash
  python3 -c "
  import json; from collections import Counter
  m=json.load(open('$HOME/Obsidian/KDB/state/manifest.json'))
  print(Counter(s.get('run_state') for s in m['sources'].values()))"
  ```
- `~/Obsidian` is a symlink to `/mnt/c/Users/fangq/Documents/Obsidian Vault` — same vault.

## 4. WATCH-FORS FOR RUN COMPLETION

- Cold-start is still partially in effect (graph was rebuilt from zero this run): early
  `abstain_empty_space` / honestly-empty T2 is valid, not a failure.
- `thin fails ⇒ no fat` (D-123-G): two bad thin responses end a search; now visible at scale.
- Zero-key sources (#126): valid end-to-end, degenerate unresolved-expression metrics on them.
- DashScope content-filter false positives (`data_inspection_failed`) — standing provider risk.
- Reconciliation surfaces at finalize: `searches_attempted − searches_written` (measurement
  header) vs envelope files on disk (emit) — drift warns, never silently scores. NOTE: the
  finalize KPIs cover ONLY this run's 468 sources; attempts 1–2 envelopes live under their own
  run dirs (`state/runs/2026-08-07T14-11-55_EDT`, `…T19-12-17_EDT`) for cross-run assembly.
- On completion: the finalize tail archives the replay journal + flips frontmatter; verify
  `state/last_orchestrate.json` shows `exit_reason=success` and check the KPI emission.

## 5. WHERE THINGS LIVE (this episode)

- Active run log: `/tmp/kdb-orchestrate-resume.log` (volatile with the VM).
- Attempt-2 log (complete record of the 21:58 kill): `~/kdb-official-resume-2026-08-07.log`.
- Manifest/graph: `<vault>/KDB/state/manifest.json`, `<vault>/KDB/graph`.
- Forensic scripts used against Windows event logs: `/tmp/winevt*.ps1` (volatile; trivially
  re-derivable — read-only `Get-WinEvent` queries).
- Pipeline definition: `<vault>/KDB/state/pipelines.json` (`vault-in-place`, root = vault,
  excludes `KDB/`, `Vault-in-place-test-run/`, `__pycache__/`; `force_noise: Daily Notes/*`).

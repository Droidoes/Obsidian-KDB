"""types — typed dataclasses for pipeline payloads. Single source of truth for shapes.

M0.1 stub. Implementation in M1.

Every cross-module payload in the pipeline has a dataclass here. Modules
import from `types` instead of speaking in loose dicts. This prevents
schema drift between scan -> planner -> compiler -> patch_applier -> manifest_update.

Planned dataclasses:
    * ScanEntry            — one row in last_scan.json files[]
    * ScanResult           — the full last_scan.json payload
    * CompileJob           — one planner output (source + context snapshot)
    * JobBatch             — a chunk of CompileJob (10-20 per batch)
    * PageIntent           — LLM-authored page output (slug, title, body, links, ...)
    * CompiledSource       — one source's full compile output (summary + pages)
    * CompileResult        — the full compile_result.json payload
    * LogEntry             — one log.md entry the LLM emitted
    * SourceRecord         — one entry in manifest.sources{}
    * PageRecord           — one entry in manifest.pages{}
    * OrphanRecord         — one entry in manifest.orphans{}
    * TombstoneRecord      — one entry in manifest.tombstones{}
    * Manifest             — the full manifest.json payload
    * RunContext           — run_id, timestamps, compiler_version, dry_run

Serialization:
    * All dataclasses have `to_dict()` and `from_dict()` for JSON round-trip.
    * JSON schemas in kdb_compiler/schemas/ are the AUTHORITATIVE external contract;
      this module mirrors them in Python and is validated against them in tests.

Design note: we use plain dataclasses, not pydantic, to avoid a dep. The JSON
schemas do the external validation; dataclasses are for internal type discipline.
"""


def main() -> None:
    raise NotImplementedError("types — scheduled for M1")


if __name__ == "__main__":
    main()

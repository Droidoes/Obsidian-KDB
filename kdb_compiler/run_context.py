"""run_context — per-run metadata: run_id, timestamps, versions, dry-run flag.

M0.1 stub. Implementation in M1.

One RunContext object is created at the start of each compile run and
threaded through every stage. This is the ONLY place in the pipeline
where "now" is read, "run_id" is generated, and "compiler_version" is
stamped. Everything else receives the context as a parameter.

Why centralize this: `CLAUDE.md` forbids the LLM from emitting timestamps,
versions, or run IDs. Python owns all of them. Having one module own the
generation makes that boundary enforceable at review time.

Contents of RunContext:
    run_id             — "2026-04-18T21-44-00Z" (ISO-like, filename-safe)
    started_at         — ISO UTC string
    compiler_version   — "v1" (read from kdb_compiler.__version__)
    schema_version     — "1.0" (read from manifest.schema_version)
    dry_run            — bool; if True, patch_applier and manifest_update
                         print intended writes without executing
    vault_root         — Path to vault root (resolved via paths.py)
    log_entries        — accumulator for LogEntry objects emitted during the run

Factory:
    RunContext.new(dry_run: bool = False) -> RunContext

The frontmatter stamped on every LLM-authored page is built from this object
by patch_applier — the LLM never sees it.
"""


def main() -> None:
    raise NotImplementedError("run_context — scheduled for M1")


if __name__ == "__main__":
    main()

"""validate_compile_result — schema-validates compile_result.json before any writes.

M0 stub. Implementation in M1 ports Codex 5.3's reference implementation.

Pipeline position:
    kdb_scan -> planner -> compiler -> [validate] -> patch_applier -> manifest_update

Fail-fast gate: if the LLM output is malformed, nothing downstream runs.
No vault writes occur unless validation passes.

Exit codes:
    0 — valid
    1 — invalid (schema violations printed with JSONPath)
    2 — runtime/config error (missing schema or data file)

Inputs:
    KDB/state/compile_result.json
    KDB/state/compile_result.schema.json

Output:
    stdout — OK / INVALID with violation list
"""


def main() -> None:
    raise NotImplementedError("validate_compile_result.main — scheduled for M1")


if __name__ == "__main__":
    main()

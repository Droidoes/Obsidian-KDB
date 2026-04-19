"""prompt_builder — reserved split-point (Codex M0 review D21). Implementation in M2.

Split from compiler.py to keep prompt authorship separate from orchestration.

Responsibilities (when implemented):
    * Build the per-source compile prompt string.
    * Inject CLAUDE.md invariants.
    * Inject source content.
    * Inject relevant manifest snapshot (via context_loader.py).
    * Inject schema reminder so LLM self-checks output shape.
    * Inject self-check list from CLAUDE.md.

Kept as a separate module so prompts are versioned alongside code and
testable in isolation (snapshot tests of prompt text).
"""


def main() -> None:
    raise NotImplementedError("prompt_builder — scheduled for M2")


if __name__ == "__main__":
    main()

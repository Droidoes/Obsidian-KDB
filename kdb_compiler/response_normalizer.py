"""response_normalizer — reserved split-point (Codex M0 review D21). Implementation in M2.

Parses the LLM response text into a CompileResult dataclass. Separated from
compiler.py so parsing rules evolve independently of orchestration.

Responsibilities (when implemented):
    * Extract JSON from the LLM response (tolerate markdown fences, leading prose).
    * Parse into CompiledSource + PageIntent dataclasses (types.py).
    * Light normalization: trim whitespace, ensure slugs are slug-shaped,
      dedupe outgoing_links.
    * Do NOT validate schema here — that's validate_compile_result.py's job.
      This module produces a best-effort CompiledSource; validation runs after
      all sources are accumulated into compile_result.json.

Reason for separation: when prompts or models change, parsing quirks change.
Having this as its own module keeps drift localized.
"""


def main() -> None:
    raise NotImplementedError("response_normalizer — scheduled for M2")


if __name__ == "__main__":
    main()

"""paths — vault discovery, slug-to-path resolution, path policy.

M0.1 stub. Implementation in M1.

Single source of truth for everything path-related. Nothing else in the
codebase should construct a KDB path by string concatenation.

Responsibilities:
    * Discover the vault root (env var OBSIDIAN_VAULT_PATH, or $HOME/Obsidian).
    * Define the canonical KDB subtree layout (raw/, wiki/*, state/).
    * Resolve page-intent slugs to absolute filesystem paths:
        slug="attention-mechanism", page_type="concept"
          -> <vault>/KDB/wiki/concepts/attention-mechanism.md
    * Slugify titles: "Attention Is All You Need" -> "attention-is-all-you-need"
    * Classify an absolute path back into (page_type, slug) for reverse lookup.
    * Normalize relative paths against vault root (POSIX style in manifest).
    * Reject paths outside KDB/ as a safety invariant.

Slug policy (v1):
    * Lowercase, kebab-case, ASCII-only (NFKD strip).
    * Reserved slugs: "index", "log" (Python-owned pages; LLM cannot emit these).
    * Collisions are an error, not silent numeric suffix — user sees it in log.md.

This module has NO I/O. It is pure computation over strings and pathlib.Path.
"""


def main() -> None:
    raise NotImplementedError("paths — scheduled for M1")


if __name__ == "__main__":
    main()

"""call_model_retry — retry wrapper around call_model with provider-aware backoff.

M0 stub. Implementation in M1 ports Codex 5.3's reference implementation verbatim.

Responsibilities:
    * Classify exceptions as retryable / non-retryable per provider.
    * Respect Retry-After header when present.
    * Exponential backoff with jitter (default: 6 attempts, 0.5s -> 20s).
    * Pass timeout into req.extra so call_model implementations honor it.
    * Raise NonRetryableModelError for auth/bad-request/context-length.
    * Raise RetryableModelError after exhausting attempts.

Used by: compiler.py (one call per source per batch).
"""


def main() -> None:
    raise NotImplementedError("call_model_retry — scheduled for M1")


if __name__ == "__main__":
    main()

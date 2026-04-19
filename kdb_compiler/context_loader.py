"""context_loader — reserved split-point (Codex M0 review D21). Implementation in M2.

Builds the "manifest snapshot" given to the LLM for a compile job. This is
the model's only view of world state during compile. Shape matters a lot.

Responsibilities (when implemented):
    * Given a CompileJob, select which existing pages are relevant:
        - pages whose source_refs include this source_id
        - pages whose slug is mentioned in the source content
        - pages linked from the above (transitive, capped)
    * Emit a compact JSON snapshot with slug, title, existing body (truncated),
      outgoing_links, supports_page_existence.
    * Never leak paths, frontmatter, or timestamps into the snapshot.

Chunking-related: the snapshot is per-job (per-source), not per-batch. Each
source's prompt gets a scoped context slice, not the whole manifest.
"""


def main() -> None:
    raise NotImplementedError("context_loader — scheduled for M2")


if __name__ == "__main__":
    main()

# Task #89 NW-7 v0.1 Source Type Controlled Vocabulary Review — Gemini

## Convergence
This review recognizes the structural logic and alignment of the NW-7 v0.1 controlled vocabulary. The framework decisions establish a clean sibling relationship with the NW-4 domain list:
- **Flat Classification (D-NW7-1)**: Avoiding hierarchical sub-types prevents prompt bloat and leaves structural nesting to the query layer where it belongs.
- **Config-Driven Architecture (D-NW7-3)**: Consolidating scopes, displays, and aliases into a single JSON schema mirrors the successful `domains.json` precedent.
- **Strategic Drops**: The exclusion of `podcast` (without transcript) is highly defensible. When a podcast consists only of text show notes, the LLM should evaluate it by its literal prose shape (`post` or `article`) rather than its audio origins.
- **Authority Tagging Deferral (OQ-NW7-5)**: Deferring the complexity of subjective quality/authority ratings is correct. Telemetry on the baseline 20-entry list must be established first.

---

## Findings

### **Finding F-1: Precedence Contradiction in tiebreakers (D-NW7-4 vs §3.3)**
- **Reference**: D-NW7-4 and §3.3 (transcript-podcast ↔ transcript-video ↔ transcript-interview ↔ transcript-lecture)
- **Finding**: There is a direct logical contradiction between the tiebreaker rule in D-NW7-4 and the boundary rules in §3.3. D-NW7-4 states that when a tie occurs between a rhetorical format (e.g. interview) and the recording medium (e.g. video), the recording medium wins (e.g. classifying as `transcript-video` instead of `transcript-interview`). However, §3.3 states that if the Q&A structure dominates, it classifies as `transcript-interview` regardless of the recording medium. The algorithm and the text boundary descriptions must align.
- **Impact**: Left unresolved, this creates ambiguity in both prompt construction and prompt validation, leading to inconsistent classification of interview transcripts that happen to be recorded as videos or podcasts.

### **Finding F-2: Omission of Chat Logs (`chat-log`) as a First-Class Source Type**
- **Reference**: §4 (Explicit drops) and §2.3 (Primary-document cluster)
- **Finding**: The 20-entry list omits chat transcripts (Slack exports, Discord channel archives, or saved ChatGPT conversation logs). These represent a highly prevalent modern personal knowledge intake format. Classifying a saved ChatGPT conversation as `post`, `documentation`, or `other` is semantically inaccurate and loses the unique, multi-agent conversational structure of the source.
- **Impact**: Telemetry will show an elevated `other` classification rate for saved LLM chat logs and community chat exports, masking actual intake distributions.

### **Finding F-3: Boundary Ambiguity on Single Substantive Social Posts**
- **Reference**: §3.8 (`social-thread` ↔ `post`)
- **Finding**: §3.8 differentiates the two based purely on threaded structure (multi-tweet threads vs single comments). However, platforms like LinkedIn or Substack Notes frequently host long-form, substantive, single-post essays that have no nested comment threads. Under the current boundaries, these substantive essays would be forced into `post` (conflating them with casual Reddit comments) or `blog` (violating the platform-hosted original register of `social-thread`).
- **Impact**: Substantive single-post social essays will be misclassified as low-signal forum posts.

---

## Recommendations

### **Proposal: Rhetorical Format Priority in Transcript Tiebreaker (F-1 resolution)**
- **Recommendation**: Clarify that **rhetorical format always wins** over container medium when the format dominates. A user filtering for interviews wants all interviews, regardless of whether the source was originally a video file or an audio podcast. Medium-based classifications (`transcript-video` and `transcript-podcast`) should act strictly as fallbacks when the spoken structure is a generic monologue, conversational chatter, or lacks a dominant Q&A or lecture format.

### **Proposal: Introduce the `chat-log` Source Type (F-2 resolution)**
- **Recommendation**: Add a 21st canonical entry: `chat-log` (Display: "Chat Log / Conversation").
- **Scope**: *"Verbatim log of a conversational exchange between two or more parties in a messaging, chat, or LLM interface (Slack exports, Discord conversations, saved ChatGPT transcripts). Typically structured with rapid, alternating, multi-speaker conversational blocks. Distinguished from `transcript-interview` by the informal register and interactive, non-formal exchange shape."*

### **Proposal: Refine the `social-thread` Boundary (F-3 resolution)**
- **Recommendation**: Adjust the boundary in §3.8 to focus on **platform context and substantive length** rather than purely counting individual posts. If a single platform post (e.g. Twitter/X long-form post, LinkedIn article-post) is substantive and analytical, it should classify as `social-thread`. The `post` type should be restricted to conversational comments, forum replies (e.g. HN comments, Reddit comment blocks), or short, casual social sharing.

### **Observation O-1: Volume-Based Tiebreaker for Annotated Book Excerpts**
- **Reference**: §3.4 (`book-chapter` ↔ `book-summary`)
- **Proposal**: Explicitly state that when a user annotates a book chapter, the classification is volume-driven: if the file is predominantly verbatim book text interspersed with minor margin notes, it remains `book-chapter`. If the file primarily consists of user-authored summary, analysis, and conceptual restructuring interspersed with direct blockquotes, it belongs in `book-summary`.

### **Observation O-2: Clarifying the Register vs. Venue in Encyclopedic Writing**
- **Reference**: §3.7 (`wiki` ↔ `article`)
- **Proposal**: Emphasize that `wiki` is reserved for multi-author collaborative knowledge bases or reference documents with no individual authorial voice (Wikipedia pages), while highly authoritative, citation-heavy essays with single-author signatures (such as essays in the New York Review of Books) remain in `article`.

### **Observation O-3: Document the `documentation` ↔ `wiki` Reference Boundary**
- **Reference**: §3.7 and §2.1
- **Proposal**: Add a brief boundary section in §3 clarifying that `documentation` is product-focused instruction, API reference, or direct tutorials (manuals, READMEs, runbooks), whereas `wiki` represents descriptive history or conceptual entries about a product, entity, or topic.

---

## Concrete classification probes

The reviewer proposes the following concrete classifications under the NW-7 v0.1 list to test the boundaries:

1. **Warren Buffett's 2020 Annual Letter to Berkshire Shareholders**
   - *Classification*: `letter`
   - *Rationale*: A formally addressed, curated, public-facing annual letter to shareholders (satisfies §3.5).
2. **Auto-generated transcript of Andrew Ng's YouTube lecture on Deep Learning**
   - *Classification*: `transcript-lecture`
   - *Rationale*: A verbatim transcript of a one-way educational talk delivered via video medium (rhetorical format wins over video medium per §3.3).
3. **A saved copy of the official PyTorch API Reference README**
   - *Classification*: `documentation`
   - *Rationale*: Structured technical reference documentation for software libraries (satisfies §2.1).
4. **A comprehensive Wikipedia article on the Federal Reserve System**
   - *Classification*: `wiki`
   - *Rationale*: Encyclopedic reference entry written in third-person, neutral register (satisfies §3.7).
5. **A 15-tweet Twitter thread by an investor analyzing a semiconductor company's capital expenditures**
   - *Classification*: `social-thread`
   - *Rationale*: Multi-post platform-hosted thread carrying substantive structured content (satisfies §3.8).

---

## Open questions

### **OQ-1: The Curated Link List Category**
- **Description**: Users frequently create bookmark collections or curated link directories in their Obsidian vault (e.g. `Reading/Investing-Bookmarks.md` containing 50 links with brief descriptions).
- **Design Need**: Does the system need a dedicated `bookmarks` or `link-directory` source type, or should these classify under `wiki` (reference list) or `other`?

### **OQ-2: Written Q&A Interviews**
- **Description**: Some interviews are conducted entirely in writing (e.g., a journalist submitting written questions via email, and the subject replying in writing).
- **Design Need**: Since there is no spoken delivery to transcribe, does this belong in `letter`, `post`, or does `transcript-interview` remain the correct classification because the structural Q&A layout dominates? (The reviewer recommends `transcript-interview` to preserve rhetorical format mapping).

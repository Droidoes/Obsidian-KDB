"""call_model — provider abstraction for Anthropic / OpenAI / Gemini / Ollama.

M0 stub. Implementation in M1 ports from ~/Droidoes/Code-projects/youtube-comment-chat/src/llm.py.

Pipeline position: used by compiler.py (and anywhere else an LLM call is needed).

Contract (unified request/response):
    ModelRequest:
        provider: "anthropic" | "openai" | "gemini" | "ollama"
        model: str (e.g., "claude-opus-4-7", "gpt-5.4", "gemini-pro-3.1", "llama3")
        system: str | None
        prompt: str
        json_mode: bool = False
        temperature: float = 0.0
        max_tokens: int = 4096
        tools: list | None = None
        extra: dict = {}      (provider-specific kwargs incl. timeout)

    ModelResponse:
        text: str
        usage: dict           ({input_tokens, output_tokens, ...})
        raw: Any              (provider-native response for debugging)

Env-var credentials (resolved lazily, cached per-process):
    ANTHROPIC_API_KEY, OPENAI_API_KEY, GEMINI_API_KEY
    OLLAMA_HOST (default: http://localhost:11434)
"""


def main() -> None:
    raise NotImplementedError("call_model — scheduled for M1")


if __name__ == "__main__":
    main()

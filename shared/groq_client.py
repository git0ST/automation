"""
Free AI inference via Groq (Llama 3) and Google Gemini Flash.

Groq:   https://console.groq.com — free tier, 14,400 req/day
Gemini: https://aistudio.google.com — free tier, 1,500 req/day

Both are 10-100× faster than local Ollama on typical hardware.
Add GROQ_API_KEY or GOOGLE_API_KEY to your .env file.

Usage:
    from shared.groq_client import chat, chat_async
    summary = chat("Summarise this news: ...")
    summary = await chat_async("Summarise this news: ...")
"""

import os
import asyncio
from typing import Optional

# ── Model selection ───────────────────────────────────────────────────────────

GROQ_MODELS = {
    "fast":    "llama-3.1-8b-instant",   # ~200ms, free, 6k TPM
    "smart":   "llama-3.3-70b-versatile", # ~800ms, free, better reasoning
    "default": "llama-3.1-8b-instant",
}

GEMINI_MODELS = {
    "fast":    "gemini-1.5-flash-8b",    # free, very fast
    "smart":   "gemini-1.5-flash",       # free, smarter
    "default": "gemini-1.5-flash-8b",
}


def _detect_provider() -> str:
    """Return the best available free AI provider."""
    if os.getenv("GROQ_API_KEY"):
        return "groq"
    if os.getenv("GOOGLE_API_KEY"):
        return "gemini"
    return "none"


# ── Groq client ───────────────────────────────────────────────────────────────

_groq_client = None

def _get_groq():
    global _groq_client
    if _groq_client is not None:
        return _groq_client
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return None
    try:
        from groq import Groq
        _groq_client = Groq(api_key=api_key)
    except ImportError:
        pass
    return _groq_client


def _chat_groq(prompt: str, system: str = "", model: str = "fast", max_tokens: int = 512) -> Optional[str]:
    client = _get_groq()
    if not client:
        return None
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    try:
        resp = client.chat.completions.create(
            model      = GROQ_MODELS.get(model, model),
            messages   = messages,
            max_tokens = max_tokens,
            temperature= 0.3,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print(f"[groq] error: {e}")
        return None


# ── Gemini client ─────────────────────────────────────────────────────────────

_gemini_client = None

def _get_gemini():
    global _gemini_client
    if _gemini_client is not None:
        return _gemini_client
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return None
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        _gemini_client = genai
    except ImportError:
        pass
    return _gemini_client


def _chat_gemini(prompt: str, system: str = "", model: str = "fast", max_tokens: int = 512) -> Optional[str]:
    genai = _get_gemini()
    if not genai:
        return None
    full_prompt = f"{system}\n\n{prompt}" if system else prompt
    try:
        m = genai.GenerativeModel(GEMINI_MODELS.get(model, model))
        resp = m.generate_content(
            full_prompt,
            generation_config=genai.GenerationConfig(max_output_tokens=max_tokens, temperature=0.3),
        )
        return resp.text.strip()
    except Exception as e:
        print(f"[gemini] error: {e}")
        return None


# ── Fallback: rule-based (no API key) ─────────────────────────────────────────

def _fallback_summary(prompt: str, system: str = "") -> str:
    """Return first meaningful sentence when no AI is available."""
    lines = [l.strip() for l in prompt.split("\n") if l.strip() and len(l.strip()) > 20]
    return lines[0][:200] if lines else "No summary available."


# ── Public interface ──────────────────────────────────────────────────────────

def chat(
    prompt:     str,
    system:     str = "",
    model:      str = "fast",
    max_tokens: int = 512,
    provider:   Optional[str] = None,
) -> str:
    """
    Synchronous AI chat. Tries Groq → Gemini → rule-based fallback.

    Args:
        prompt:     The user prompt.
        system:     System / role instruction.
        model:      "fast" | "smart" | explicit model name.
        max_tokens: Max output tokens.
        provider:   Force "groq" | "gemini" | None (auto-detect).

    Returns:
        Generated text string.
    """
    prov = provider or _detect_provider()

    if prov == "groq":
        result = _chat_groq(prompt, system, model, max_tokens)
        if result:
            return result

    if prov == "gemini" or (prov == "groq" and not result):
        result = _chat_gemini(prompt, system, model, max_tokens)
        if result:
            return result

    return _fallback_summary(prompt, system)


async def chat_async(
    prompt:     str,
    system:     str = "",
    model:      str = "fast",
    max_tokens: int = 512,
) -> str:
    """
    Async wrapper around chat() — runs in thread pool to avoid blocking.
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, chat, prompt, system, model, max_tokens)


def is_ai_available() -> bool:
    """True if any free AI provider is configured."""
    return _detect_provider() != "none"


def ai_provider_name() -> str:
    """Returns the active provider name for display."""
    p = _detect_provider()
    if p == "groq":
        return f"Groq · {GROQ_MODELS['default']}"
    if p == "gemini":
        return f"Gemini · {GEMINI_MODELS['default']}"
    return "Rule-based (add GROQ_API_KEY for AI)"

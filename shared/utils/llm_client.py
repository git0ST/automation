"""
Unified LLM client — swap local (Ollama) ↔ cloud (Anthropic/OpenAI/Groq)
by changing LLM_PROVIDER in your .env file.

Usage:
    from shared.utils import chat, get_llm

    # Simple one-shot call
    reply = chat("Explain gradient descent in one sentence.")

    # Model object (LangChain-compatible interface)
    llm = get_llm()
    reply = llm.invoke("Hello")
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


@dataclass
class LLMConfig:
    provider: str = field(default_factory=lambda: os.getenv("LLM_PROVIDER", "local"))
    # Local
    ollama_model: str = field(default_factory=lambda: os.getenv("OLLAMA_MODEL", "phi3:mini"))
    ollama_base_url: str = field(default_factory=lambda: os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))
    # Cloud
    cloud_provider: str = field(default_factory=lambda: os.getenv("CLOUD_PROVIDER", "anthropic"))
    cloud_model: str = field(default_factory=lambda: os.getenv("CLOUD_MODEL", "claude-sonnet-4-6"))
    temperature: float = 0.0


class _OllamaAdapter:
    """Thin wrapper around the ollama library with invoke/stream matching LangChain's interface."""

    def __init__(self, model: str, host: str, temperature: float):
        self.model = model
        self.host = host
        self.temperature = temperature

    def _to_ollama_messages(self, messages) -> list[dict]:
        result = []
        for msg in messages:
            type_name = type(msg).__name__
            if "System" in type_name:
                role = "system"
            elif "AI" in type_name or "Assistant" in type_name:
                role = "assistant"
            else:
                role = "user"
            result.append({"role": role, "content": msg.content})
        return result

    def invoke(self, messages):
        import ollama
        client = ollama.Client(host=self.host)
        resp = client.chat(
            model=self.model,
            messages=self._to_ollama_messages(messages),
            options={"temperature": self.temperature},
        )
        return _Response(resp.message.content)

    def stream(self, messages):
        import ollama
        client = ollama.Client(host=self.host)
        for chunk in client.chat(
            model=self.model,
            messages=self._to_ollama_messages(messages),
            options={"temperature": self.temperature},
            stream=True,
        ):
            yield _Response(chunk.message.content)


class _Response:
    """Minimal response object matching LangChain's AIMessage interface."""
    def __init__(self, content: str):
        self.content = content


@lru_cache(maxsize=4)
def get_llm(provider: Optional[str] = None, model: Optional[str] = None):
    """Return a chat model with .invoke() and .stream() methods. Result is cached."""
    cfg = LLMConfig()
    provider = provider or cfg.provider

    if provider == "local":
        return _OllamaAdapter(
            model=model or cfg.ollama_model,
            host=cfg.ollama_base_url,
            temperature=cfg.temperature,
        )

    cloud = cfg.cloud_provider
    m = model or cfg.cloud_model

    if cloud == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model=m, temperature=cfg.temperature)

    if cloud == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=m, temperature=cfg.temperature)

    if cloud == "groq":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=m,
            base_url="https://api.groq.com/openai/v1",
            api_key=os.getenv("GROQ_API_KEY"),
            temperature=cfg.temperature,
        )

    raise ValueError(f"Unknown provider: {cloud!r}. Set CLOUD_PROVIDER=anthropic|openai|groq")


def chat(prompt: str, system: Optional[str] = None, **kwargs) -> str:
    """Minimal one-shot chat call. Returns the reply string."""
    from langchain_core.messages import HumanMessage, SystemMessage

    messages = []
    if system:
        messages.append(SystemMessage(content=system))
    messages.append(HumanMessage(content=prompt))

    llm = get_llm(**kwargs)
    response = llm.invoke(messages)
    return response.content

# Model Selection Guide

## Local Models (Ollama) — your Mac (8 GB RAM)

| Model | Size | RAM needed | Best for |
|-------|------|-----------|---------|
| `phi3:mini` | 2.3 GB | ~3 GB | General tasks, fast, good reasoning — **start here** |
| `llama3.2:3b` | 2.0 GB | ~3 GB | Balanced, good at instruction following |
| `nomic-embed-text` | 0.3 GB | ~1 GB | Embeddings / RAG (run alongside a chat model) |
| `llama3.1:8b` | 4.7 GB | ~6 GB | Better quality, still fits 8 GB but slower |

**Rule:** never pull a model where its size > 60% of your RAM.  
8 GB × 0.6 = 4.8 GB max. Stick to ≤4B params for smooth performance.

## Cloud Models — when to use

| Provider | Model | Cost | Best for |
|----------|-------|------|---------|
| Anthropic | `claude-sonnet-4-6` | ~$3/$15 per M tokens | Complex reasoning, long docs |
| Anthropic | `claude-haiku-4-5` | ~$0.25/$1.25 per M tokens | Fast, cheap, high volume |
| OpenAI | `gpt-4o-mini` | ~$0.15/$0.60 per M tokens | Good balance |
| Groq | `llama-3.1-70b` | Free tier | Fast inference on large model |

**Use cloud when:** the task needs long context, complex multi-step reasoning,
or you want to run without Ollama running.

## Switching providers

In your root `.env`:
```
LLM_PROVIDER=local    # uses OLLAMA_MODEL
LLM_PROVIDER=cloud    # uses CLOUD_PROVIDER + CLOUD_MODEL
```

Or per-call in Python:
```python
llm = get_llm(provider="cloud", model="claude-haiku-4-5-20251001")
```

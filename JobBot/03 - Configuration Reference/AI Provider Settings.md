---
tags:
  - configuration
  - reference
  - current
related_code: match_scorer.py
---

# AI Provider Settings

JobBot uses AI at three points in the pipeline. Each stage can use a different provider and model.

## The three AI stages

| Stage | Config key | Purpose | Recommended |
|---|---|---|---|
| Cheap screen | `cheap_stage_provider` | Fast bulk triage — runs on every job | `ollama_local` (free) or `openai` |
| Strong score | `strong_stage_provider` | High-confidence final scoring — runs on top candidates only | `anthropic` or `openai` |
| Document tailoring | `doc_stage_provider` | Writes tailored resume bullets and cover letter | `openai` or `anthropic` |

> [!tip] Cheapest useful setup
> - Cheap stage: `ollama_local` with `qwen2.5:7b` — completely free, runs on your machine
> - Strong stage: `openai` with `gpt-5-mini` — a few cents per run
> - Doc stage: `openai` with `gpt-5-mini` — a few cents per document

## Provider options

| Provider | Value | Notes |
|---|---|---|
| Ollama (local) | `ollama_local` | Free; requires Ollama installed and model pulled. Cheap stage only |
| OpenAI | `openai` | Requires `openai_api_key`. Works for all three stages |
| Anthropic | `anthropic` | Requires `anthropic_api_key`. Works for strong and doc stages |

## Known models and cost tier

| Provider | Model | Cost tier |
|---|---|---|
| Ollama | `qwen2.5:7b` | Free (local) |
| OpenAI | `gpt-5-nano` | Very cheap |
| OpenAI | `gpt-5-mini` | Cheap |
| OpenAI | `gpt-4o-mini` | Cheap |
| OpenAI | `gpt-4o` | Mid |
| Anthropic | `claude-haiku-4-5-20251001` | Cheap |
| Anthropic | `claude-sonnet-4-20250514` | Mid |

## Ollama configuration

| Setting | Default | Description |
|---|---|---|
| `ollama_base_url` | `http://localhost:11434` | URL of your Ollama server |

## API keys

Enter API keys in the Config Tab. They are stored in `config.yaml` in plain text — do not commit that file to a public repository.

## Related Notes

- [[Stage 4 — Cheap AI Stage]]
- [[Stage 5 — Strong AI Stage]]
- [[Stage 6 — Document Generation]]
- [[AI Cost Tracking]]
- [[Ollama Not Responding]]
- [[Decision — AI Provider Choice]]

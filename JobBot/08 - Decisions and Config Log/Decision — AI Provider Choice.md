---
tags:
  - decisions
  - decision
date: 2026-04-13
decision_status: active
related_notes:
  - "[[AI Provider Settings]]"
  - "[[Scoring Thresholds]]"
---

# Decision — AI Provider Choice

## Context

Three pipeline stages need AI: bulk cheap screening, final strong scoring, and document tailoring. Each has different quality and cost requirements.

## Decision

- **Cheap stage:** `ollama_local` with `qwen2.5:7b` — runs locally, zero cost
- **Strong stage:** `anthropic` with `claude-sonnet-4-20250514` (or `openai` with a GPT-4-class model)
- **Doc stage:** `openai` with `gpt-5-mini`

## Rationale

The cheap stage processes every job that passes the TF-IDF gate — potentially 15-20 jobs per run. At hosted API rates, that adds up. A local Ollama model eliminates that cost entirely with acceptable quality for a triage pass.

The strong stage runs on only 2-5 jobs per run. Using a more capable hosted model here gives better final decisions without significant cost.

Document tailoring requires creative writing quality. A mid-tier hosted model produces better cover letters than a small local model.

## Alternatives considered

- **All-hosted (OpenAI or Anthropic for all stages)** — works well but more expensive for bulk screening
- **All-local (Ollama for all stages)** — cheapest, but local models underperform on cover letter generation and strong scoring nuance

## Consequences

- Requires Ollama to be running for cheap-stage runs. Falls back to an error (not a silent skip) if Ollama is unavailable.
- API keys needed for strong and doc stages even when cheap stage is free.
- Update the strong and doc stage models when newer, cheaper options become available.

## Related Notes

- [[AI Provider Settings]]
- [[Stage 4 — Cheap AI Stage]]
- [[Stage 5 — Strong AI Stage]]
- [[Ollama Not Responding]]

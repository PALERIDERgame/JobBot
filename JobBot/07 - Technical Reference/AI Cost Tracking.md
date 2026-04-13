---
tags:
  - technical
  - reference
  - current
related_code: match_scorer.py
---

# AI Cost Tracking

How JobBot measures and displays AI API costs.

## How costs are calculated

After each AI API call, JobBot records the token counts returned by the API and applies a per-model price lookup:

| Provider | Model | Input (per 1M tokens) | Output (per 1M tokens) |
|---|---|---|---|
| OpenAI | gpt-4o-mini | $0.15 | $0.60 |
| OpenAI | gpt-4o | $2.50 | $10.00 |
| OpenAI | gpt-5-mini | $0.25 | $2.00 |
| Anthropic | claude-haiku-4-5-20251001 | $0.80 | $4.00 |
| Anthropic | claude-sonnet-4-20250514 | $3.00 | $15.00 |
| Ollama (local) | any | $0.00 | $0.00 |

Cost formula: `(input_tokens / 1,000,000 × input_price) + (output_tokens / 1,000,000 × output_price)`

## Where costs are stored

The `ai_evaluations` table stores `input_tokens`, `output_tokens`, and `estimated_cost_usd` for every AI call. The `cached` flag indicates if a result was reused from a previous run (cost is $0 for cached results).

## Run tab display

The Run tab shows a running cost total that updates as each AI stage completes. This is an estimate — actual billing depends on your API plan, any prompt caching discounts, and model pricing updates.

> [!note] These prices may be out of date
> Model pricing changes frequently. Check the provider's pricing page for current rates. The values in JobBot are estimates for rough budgeting, not billing-accurate figures.

## Keeping costs low

- Use Ollama for the cheap stage — eliminates the bulk of per-job API cost
- The strong stage only runs on a small fraction of jobs (those that escalate past cheap screening)
- Cached results are free — re-running on the same job batch costs almost nothing for scored jobs

## Related Notes

- [[AI Provider Settings]]
- [[Database Schema]]
- [[Stage 4 — Cheap AI Stage]]
- [[Stage 5 — Strong AI Stage]]

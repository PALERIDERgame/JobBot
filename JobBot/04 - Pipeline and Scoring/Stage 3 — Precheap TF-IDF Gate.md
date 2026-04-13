---
tags:
  - pipeline
  - reference
  - current
stage: 3
related_code: match_scorer.py
---

# Stage 3 — Precheap TF-IDF Gate

A fast, free screening step that catches obvious mismatches before spending any AI tokens.

## How it works

The gate computes a similarity score between the job description and your resume using two signals:

1. **TF-IDF cosine similarity** — vectorizes both texts using scikit-learn and measures vocabulary overlap (weighted 70%)
2. **Keyword overlap count** — counts matching terms after removing common English stopwords (weighted 30%)

Combined score formula: `0.7 × tfidf_score + 0.3 × keyword_overlap_score`

If the combined score is below `precheap_gate_reject_threshold`, the job is rejected without any AI call.

## Decision

| Score | Outcome |
|---|---|
| Below `precheap_gate_reject_threshold` (default 30) | `reject` — job filtered out |
| At or above threshold | `pass` — continue to cheap AI stage |

## Cost

Zero. TF-IDF runs locally using scikit-learn with no network calls.

## Enabling / disabling

Controlled by `precheap_gate_enabled` in config. Disabling it sends every deterministically-eligible job straight to the cheap AI stage, which increases API cost proportionally.

> [!tip] When to disable the gate
> If you find that real matches are being filtered by the TF-IDF gate (resume and job description use different terminology), disable it or lower the threshold. The AI stages are better at handling vocabulary mismatch.

## Related Notes

- [[Scoring Thresholds]]
- [[Stage 4 — Cheap AI Stage]]
- [[Pipeline Overview]]

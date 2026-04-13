---
tags:
  - configuration
  - reference
  - current
related_code: deterministic_filter.py
---

# Title Filters

Four lists that control how jobs are filtered before any AI scoring runs. These are free — no API calls.

## The four lists

### include_titles
Jobs whose title does **not** contain any of these substrings are filtered out.

```yaml
include_titles:
  - software engineer
  - python developer
  - backend developer
```

Matching is substring-based and case-insensitive. A title of "Senior Python Developer" matches `python developer`.

### exclude_titles
Jobs whose title **contains** any of these substrings are always rejected, even if they also match `include_titles`.

```yaml
exclude_titles:
  - principal
  - sales
  - designer
  - intern
```

### force_escalate_keywords
Jobs whose title **or** description contains any of these keywords skip all AI stages and land directly in the Review Queue.

```yaml
force_escalate_keywords:
  - python
  - automation
  - llm
  - agent
```

Use this for terms that are strong signals of a good fit — you want to always see them, regardless of AI scoring.

### target_titles
Used internally for scoring context. Keep it consistent with `include_titles`.

> [!note] Matching rules
> All matching is substring-based and case-insensitive. There is no regex or exact-match mode. A keyword of `sales` will also match `wholesale` — be specific.

## Related Notes

- [[Stage 2 — Deterministic Filter]]
- [[The Config Tab]]
- [[config.yaml Full Reference]]

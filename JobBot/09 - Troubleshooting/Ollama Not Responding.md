---
tags:
  - troubleshooting
  - reference
  - current
---

# Ollama Not Responding

What to check when the cheap AI stage fails because Ollama isn't available.

## Step 1 — Check if Ollama is running

Open a terminal and run:

```
ollama list
```

If you get a connection error, Ollama isn't running. Start it:

```
ollama serve
```

Or launch the Ollama desktop app if you installed it that way.

## Step 2 — Check that the model is pulled

```
ollama list
```

You should see `qwen2.5:7b` (or whichever model you configured) in the list. If not, pull it:

```
ollama pull qwen2.5:7b
```

## Step 3 — Check the base URL

The default is `http://localhost:11434`. If you changed this or run Ollama on a different port, update **Ollama base URL** in the Config Tab and save.

## Step 4 — Verify with a quick test

```
curl http://localhost:11434/api/tags
```

Should return a JSON list of your installed models.

> [!note] Temporary workaround
> If you need to run JobBot without Ollama right now, change **Cheap stage provider** in the Config Tab to `openai` or `anthropic` and enter the corresponding API key. This incurs per-call costs but works without a local Ollama instance.

## Related Notes

- [[AI Provider Settings]]
- [[Stage 4 — Cheap AI Stage]]
- [[Decision — AI Provider Choice]]

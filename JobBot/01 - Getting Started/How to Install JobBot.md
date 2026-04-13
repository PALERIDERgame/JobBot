---
tags:
  - getting-started
  - guide
  - current
---

# How to Install JobBot

Prerequisites and steps to get JobBot running on Windows.

## Prerequisites

- Python 3.11 or later
- Git (to clone the repo)
- Optional: [Ollama](https://ollama.com) for free local AI screening

## Steps

### 1. Install Python dependencies

```
pip install -r requirements.txt
```

### 2. (Optional) Install Ollama for free local screening

Download and install Ollama from [ollama.com](https://ollama.com), then pull the model JobBot uses by default:

```
ollama pull qwen2.5:7b
```

This lets the cheap AI stage run entirely on your machine at no cost.

> [!warning] Playwright for portal autofill
> If you want JobBot to auto-fill job application forms (Greenhouse, Lever, etc.), you also need to install Playwright browsers:
> ```
> playwright install chromium
> ```
> This is optional — JobBot works without it, falling back to opening the browser manually.

### 3. Configure API keys (if using hosted AI)

If you are not using Ollama, you need at least one of:
- An **Anthropic API key** (for Claude models)
- An **OpenAI API key** (for GPT models)

These are entered in the Config Tab of the dashboard, not in any file you commit to git.

### 4. Launch JobBot

Double-click `run_jobbot.bat` in the project folder.

## Related Notes

- [[First Run Setup]]
- [[AI Provider Settings]]
- [[Ollama Not Responding]]
- [[Launching JobBot]]

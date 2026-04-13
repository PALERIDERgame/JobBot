---
tags:
  - getting-started
  - guide
  - current
---

# First Run Setup

A guided walkthrough for your very first JobBot configuration. Follow these steps before clicking Start Run for the first time.

> [!tip] Recommended safe first-run settings
> - Automation mode: `semi_auto`
> - Cheap stage: `ollama_local` (free) or `openai` with `gpt-5-mini`
> - Results per page: `25` (smaller batch to verify everything works)
> - Skip AI scoring in semi_auto: enabled (fastest path to seeing results)

## Step 1 — Point to your resume

In the Config Tab, click **Choose Resume** and select your resume file. DOCX is recommended for the best tailoring quality; PDF also works.

## Step 2 — Set a job keyword

In the **Job keyword** field, enter a specific job title or skill phrase. The more specific, the better the initial results. Example: `python developer` rather than just `developer`.

## Step 3 — Choose a cheap AI provider

- If you have Ollama installed with `qwen2.5:7b`: set **Cheap stage provider** to `ollama_local`. Free.
- Otherwise: set it to `openai` and enter your **OpenAI API key**. Each run costs a few cents.

## Step 4 — Choose a strong AI provider

Set **Strong stage provider** to `anthropic` or `openai`. Enter the corresponding API key.

## Step 5 — Set automation mode

Leave **Automation mode** as `semi_auto`. This means every matched job lands in the Review Queue for you to inspect before anything is sent.

## Step 6 — Save and run

Click **Save**, then switch to the **Run Tab** and click **Start Run**.

After the run completes, go to the **Approval Tab** to see matched jobs.

## Related Notes

- [[The Config Tab]]
- [[Automation Modes]]
- [[Scoring Thresholds]]
- [[The Review Queue]]
- [[AI Provider Settings]]

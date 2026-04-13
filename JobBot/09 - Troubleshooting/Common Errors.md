---
tags:
  - troubleshooting
  - reference
  - current
---

# Common Errors

Symptoms, causes, and fixes for the most frequent JobBot problems.

## Startup errors

### App opens then immediately closes

**Cause:** A startup exception was caught by the launcher.
**Fix:** Check `%APPDATA%\JobBot\logs\jobbot.log` for the traceback. Common causes: missing Python package (run `pip install -r requirements.txt`), corrupted `config.yaml` (delete it — JobBot will recreate it with defaults).

### "Config validation failed" on startup

**Cause:** A config value is out of range or invalid.
**Fix:** Check `jobbot.log` for which field failed. Common mistakes:
- `cheap_reject_threshold` > `cheap_escalate_threshold` — swap the values
- Provider set to an unrecognized name — valid values are `ollama_local`, `openai`, `anthropic`
- Threshold outside 0–100

### Dashboard opens but shows blank config fields

**Cause:** `config.yaml` exists but couldn't be read, or was empty.
**Fix:** Delete `%APPDATA%\JobBot\config.yaml` and restart. The dashboard will create a new one with defaults.

## Scraping errors

### "Fetched 0 jobs"

**Cause:** The scraper returned no results.
**Fix:**
- For JobSpy: the keyword may be too narrow, or the site may be rate-limiting. Try a broader keyword.
- For USAJobs: verify `user_agent` (email) and `authorization_key` are set correctly.
- For Adzuna: verify `adzuna_app_id` and `adzuna_app_key` are correct.

### Scrape hangs for several minutes then fails

**Cause:** Network timeout or the job board blocked the request.
**Fix:** Try again later. If persistent with JobSpy, add LinkedIn to `jobspy_sites` as an alternative source.

## AI errors

### "AI evaluation error: client unavailable"

**Cause:** The configured AI provider can't be reached.
**Fix:** See [[Ollama Not Responding]] for Ollama errors. For hosted providers, check that the API key is correctly entered in the Config Tab.

### "Bad JSON response from AI"

**Cause:** The AI model returned malformed output.
**Fix:** Usually self-correcting — JobBot retries automatically. If it persists, try switching to a more capable model for the failing stage.

## Related Notes

- [[Gmail OAuth Problems]]
- [[Ollama Not Responding]]
- [[Jobs Not Appearing in Queue]]
- [[File Locations on Your Computer]]

# Security

JobBot handles sensitive local data: resumes, API keys, Gmail OAuth credentials, generated applications, and application history.

## What Should Stay Private

Do not commit:

- `config.yaml`
- `.env` files
- `client_secret_*.json` or `gmail_client_secret.json`
- `token.json`
- SQLite databases (`*.db`, `*.sqlite*`)
- resumes and generated application documents
- debug screenshots or generated document previews

The app stores runtime files under `%APPDATA%\JobBot\` by default so normal use does not require secrets or personal documents in the repository.

## If A Secret Was Exposed

Rotate it with the provider immediately. For Google OAuth client secrets, delete or reset the OAuth client in Google Cloud Console. For OpenAI, Anthropic, USAJobs, or Adzuna keys, revoke the old key and issue a new one.

If a secret was committed to git history, rotating it is still required even if a later commit deletes the file.

## Recommended Public-Repo Check

Before publishing:

```powershell
git status --short
git ls-files
```

Inspect the tracked file list for credentials, resumes, databases, generated previews, and local assistant notes.

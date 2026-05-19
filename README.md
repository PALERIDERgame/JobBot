# JobBot

JobBot is a Windows-first desktop assistant for running a semi-automated job search. It scrapes job sources, filters and scores postings against your resume, generates tailored application documents, and routes promising matches into a review queue before anything is sent.

The project is intentionally conservative: the default workflow is semi-auto, so a human reviews matches and approves delivery.

## Features

- Native Tkinter desktop dashboard
- Job discovery through JobSpy, USAJobs, and Adzuna adapters
- Deterministic title and keyword filtering before any model calls
- Optional AI scoring with OpenAI, Anthropic, or local Ollama models
- Resume and cover-letter generation from a source resume
- SQLite persistence for jobs, runs, match results, generated documents, and deliveries
- Optional Gmail delivery using Google OAuth
- Conservative portal autofill support with manual fallback

## Quick Start

1. Create and activate a Python 3.11+ virtual environment.

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

2. Install dependencies.

   ```powershell
   pip install -r requirements.txt
   ```

3. Launch the app.

   ```powershell
   .\run_jobbot.bat
   ```

4. In the Setup tab, choose a resume, job source, scoring providers, and any optional delivery settings.

Runtime data is stored outside the repo under `%APPDATA%\JobBot\`.

## Configuration

JobBot creates `%APPDATA%\JobBot\config.yaml` on first launch. Use `config.example.yaml` as a public-safe reference for available settings.

API keys can be entered in the app or supplied through environment variables:

- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`

Do not commit real API keys, Gmail OAuth client secrets, tokens, resumes, generated documents, or local SQLite databases.

## Gmail Delivery

Gmail delivery is optional. To use it, create a Google OAuth Desktop client, download the `client_secret_*.json` file, keep it outside git, and point JobBot at that file in the Setup tab.

The Gmail scope is limited to `https://www.googleapis.com/auth/gmail.send`.

## Tests

Run the default unit suite with:

```powershell
python -m unittest discover -s tests
```

Some integration behavior, such as Playwright browser startup and live provider calls, is intentionally mocked or opt-in for normal local runs.

## Public Repo Safety

Before making a fork public, run:

```powershell
git status --short
git ls-files
```

Confirm that personal resumes, OAuth JSON files, local databases, generated images, and temporary folders are not tracked. If secrets were ever committed, rotate them with the provider and rewrite history before publishing.

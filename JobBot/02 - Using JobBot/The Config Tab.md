---
tags:
  - using-jobbot
  - reference
  - current
---

# The Config Tab

Every field in the JobBot configuration screen, organized by section. Changes take effect after you click **Save**.

> [!note] Where settings are stored
> Clicking Save writes your settings to `%APPDATA%\JobBot\config.yaml`. You can also edit this file directly in a text editor if needed.

## Resume

| Field | What it does |
|---|---|
| Resume source | Path to your resume file. DOCX recommended for best tailoring; PDF and plain text also work. Click **Choose Resume** to browse. |

### Fit to Resume

The **Fit to Resume** button next to **Job keyword** analyzes the configured resume and opens a grouped suggestion dialog instead of silently overwriting one field.

It proposes:

- a **Combined query** for the main search phrase
- **Core titles** for direct-fit roles
- **Adjacent titles** for nearby/stretch roles
- **Domains**
- **Skills / tools**
- **Broadening terms**

When you click **Apply Suggestions**, JobBot writes the groups into the setup fields:

- **Job keyword** gets the combined query
- **Target titles** gets the core titles
- **Include titles** gets the adjacent titles

JobBot also tries to keep company names, locations, campaign names, and generic work-description phrases out of **Core titles** so the title-matching logic stays useful.

## Job Source

| Field | What it does |
|---|---|
| Source provider | Where jobs are discovered: `jobspy` (Indeed/Google), `usajobs` (federal jobs), or `adzuna` (global API) |
| Job keyword | Primary search phrase sent to the provider |
| Location | Optional location filter. Leave blank for broader results |
| JobSpy sites | Comma-separated sites for JobSpy: `indeed`, `google`, `linkedin` |
| Results per page | How many jobs to fetch per run. Start with 25 to test, then increase to 100 |
| Adzuna app id / key | Credentials from your Adzuna developer account (only needed for Adzuna provider) |
| USAJobs account email | Email registered with USAJobs API (only needed for USAJobs provider) |
| USAJobs authorization key | API key for USAJobs |

## AI Providers

| Field | What it does |
|---|---|
| Cheap stage provider | Model provider for the low-cost bulk screening pass |
| Cheap stage model | Specific model for cheap screening (e.g., `qwen2.5:7b` for Ollama) |
| Strong stage provider | Provider for the high-confidence final scoring pass |
| Strong stage model | Specific model for strong scoring (e.g., `claude-sonnet-4-20250514`) |
| Doc stage provider | Provider used to generate tailored document content |
| Doc stage model | Specific model for document tailoring |
| Ollama base URL | URL of your local Ollama server (default: `http://localhost:11434`) |
| Anthropic API key | API key for Claude models |
| OpenAI API key | API key for GPT models |

## Scoring

| Field | What it does |
|---|---|
| Cheap reject threshold | Jobs scoring below this in cheap stage are discarded (default: 25) |
| Cheap escalate threshold | Jobs scoring at or above this go to the strong stage (default: 35) |
| Final apply threshold | Strong-stage score required to mark a job as apply candidate (default: 80) |
| Pre-cheap reject threshold | TF-IDF gate score below this rejects jobs before any AI call (default: 30) |
| Enable pre-cheap gate | Toggle the TF-IDF gate on or off |
| Review threshold | Display cutoff in the dashboard (cosmetic only) |

## Title Filters

| Field | What it does |
|---|---|
| Target titles | Comma-separated direct-fit titles that strongly influence fast-rank title matching |
| Include titles | Comma-separated titles that are good fits (substring match, case-insensitive) |
| Exclude titles | Comma-separated titles to always skip |
| Force escalate keywords | Comma-separated keywords that push a job straight to the Review Queue, bypassing AI |
| Salary floor | Minimum annual salary. Use 0 to disable |

## Automation

| Field | What it does |
|---|---|
| Automation mode | `semi_auto`: all jobs land in the Review Queue. `auto`: qualifying jobs are sent automatically |
| Skip AI scoring in semi_auto | When on, semi-auto skips AI and queues deterministic matches immediately (faster reviews) |

## Gmail

| Field | What it does |
|---|---|
| Enable Gmail delivery | Turn on Gmail-based sending for approved jobs |
| Gmail sender | Your Gmail address used to send applications |
| Gmail recipient (fallback) | Optional fallback inbox for testing or non-employer delivery |
| Client secrets path | Path to the Google OAuth `client_secret_*.json` file |

## Related Notes

- [[config.yaml Full Reference]]
- [[AI Provider Settings]]
- [[Scoring Thresholds]]
- [[Title Filters]]
- [[Gmail Delivery Setup]]
- [[Automation Modes]]

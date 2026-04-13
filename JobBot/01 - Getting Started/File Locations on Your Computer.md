---
tags:
  - getting-started
  - reference
  - current
---

# File Locations on Your Computer

All JobBot runtime data lives under `%APPDATA%\JobBot\` on Windows. You can paste `%APPDATA%\JobBot` directly into Windows Explorer to open the folder.

## Runtime data files

| File | Path | Purpose |
|---|---|---|
| Config | `%APPDATA%\JobBot\config.yaml` | All your settings; edited via the dashboard |
| Database | `%APPDATA%\JobBot\jobbot.db` | SQLite database — jobs, scores, documents, delivery records |
| Resume cache | `%APPDATA%\JobBot\resume_data.json` | Parsed resume stored as JSON to avoid re-parsing on every run |
| Gmail token | `%APPDATA%\JobBot\token.json` | OAuth token for Gmail; created on first Gmail authorization |
| Log file | `%APPDATA%\JobBot\logs\jobbot.log` | All app activity; first place to look when something goes wrong |
| Output folder | `%APPDATA%\JobBot\output\` | Generated resumes and cover letters (one subfolder per job) |

> [!note] Custom output folder
> You can change the output folder location in the Config Tab under **Output dir**. An absolute path overrides the default; a relative path is resolved from `%APPDATA%\JobBot\`.

## Output folder structure

Each matched job gets its own subfolder named after the employer and job title:

```
%APPDATA%\JobBot\output\
└── Acme Corp — Python Developer\
    ├── resume.docx
    ├── resume.pdf
    ├── cover_letter.docx
    └── cover_letter.pdf
```

> [!tip] Resume cache refresh
> If you update your resume file, delete `resume_data.json` so the cache is refreshed on the next run. Otherwise JobBot will keep scoring against the old version.

## Related Notes

- [[Database Schema]]
- [[Output Files and Where to Find Them]]
- [[Gmail Delivery Setup]]
- [[Common Errors]]

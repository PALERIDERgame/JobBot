---
tags:
  - documents
  - reference
  - current
---

# Output Files and Where to Find Them

Where JobBot saves generated documents and how the folder structure is organized.

## Default output location

```
%APPDATA%\JobBot\output\
```

You can change this in the Config Tab under **Output dir**. An absolute path is used as-is; a relative path is resolved from `%APPDATA%\JobBot\`.

## Folder structure

Each matched job gets its own subfolder named `Employer — Job Title`:

```
output/
├── Acme Corp — Python Developer/
│   ├── resume.docx
│   ├── resume.pdf
│   ├── cover_letter.docx
│   └── cover_letter.pdf
└── Initech — Backend Engineer/
    ├── resume.docx
    ├── resume.pdf
    ├── cover_letter.docx
    └── cover_letter.pdf
```

## File descriptions

| File | Used for |
|---|---|
| `resume.docx` | Full-fidelity formatted resume; open in Word to review or edit |
| `resume.pdf` | Email attachment; also for portal upload |
| `cover_letter.docx` | Formatted cover letter; review and edit here |
| `cover_letter.pdf` | Email attachment |

> [!tip] Editing before sending
> If you want to tweak the cover letter before approving, open `cover_letter.docx`, make changes, save it, and then click **Approve and Send**. The approval flow uses whatever is currently on disk.

## Related Notes

- [[File Locations on Your Computer]]
- [[How Resume Tailoring Works]]
- [[Stage 6 — Document Generation]]

---
tags:
  - using-jobbot
  - guide
  - current
---

# Launching JobBot

Two ways to start the app, depending on what you need.

## Normal use — double-click the batch file

Double-click **`run_jobbot.bat`** in the project folder. This launches the GUI with no console window. Errors are caught and shown as a Windows dialog if startup fails.

## Debugging — run from a terminal

```
python main.py
```

Running from a terminal keeps the console window open so you can see startup messages and tracebacks in real time.

## If the app opens then immediately closes

The launcher catches startup exceptions and writes them to a log file before showing an error dialog. Check:

```
%APPDATA%\JobBot\logs\jobbot.log
```

for the full error message.

> [!note] The .pyw extension
> `launcher.pyw` uses the `.pyw` extension to suppress the console window on Windows. It is called by `run_jobbot.bat`. Do not run `launcher.pyw` directly unless you want the windowless version with no error output.

## Related Notes

- [[Common Errors]]
- [[File Locations on Your Computer]]
- [[The Config Tab]]

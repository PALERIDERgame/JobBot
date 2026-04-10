from __future__ import annotations

import traceback
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, Tk

from config import build_app_paths, ensure_app_dirs
from main import main


def _write_startup_error(exc: BaseException) -> Path | None:
    try:
        paths = build_app_paths()
        ensure_app_dirs(paths)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        error_file = paths.logs_dir / f"jobbot_startup_error_{stamp}.log"
        error_file.write_text("".join(traceback.format_exception(exc)), encoding="utf-8")
        return error_file
    except Exception:
        return None


def _show_startup_error(exc: BaseException) -> None:
    root = Tk()
    root.withdraw()
    error_file = _write_startup_error(exc)
    detail = f"{type(exc).__name__}: {exc}"
    if error_file is not None:
        detail += f"\n\nStartup log:\n{error_file}"
    messagebox.showerror("JobBot failed to start", detail)
    root.destroy()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # pragma: no cover - launcher-only path
        _show_startup_error(exc)
        raise

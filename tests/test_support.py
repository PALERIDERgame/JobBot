from __future__ import annotations

import shutil
import uuid
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def workspace_temp_dir():
    root = Path(__file__).resolve().parent / "_tmp"
    root.mkdir(parents=True, exist_ok=True)
    temp_dir = root / uuid.uuid4().hex
    temp_dir.mkdir(parents=True, exist_ok=True)
    try:
        yield temp_dir
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

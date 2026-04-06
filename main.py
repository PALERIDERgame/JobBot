from __future__ import annotations

from config import build_app_paths, configure_logging, ensure_app_dirs
from dashboard import launch_dashboard


def main() -> None:
    paths = build_app_paths()
    ensure_app_dirs(paths)
    configure_logging(paths.log_file)
    launch_dashboard(paths)


if __name__ == "__main__":
    main()

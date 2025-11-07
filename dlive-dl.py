"""Backward compatible entry point for the CLI downloader."""
from dlive_downloader.cli import main


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

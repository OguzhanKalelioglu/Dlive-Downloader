# Repository Guidelines

## Project Structure & Module Organization
- `dlive_downloader/`: Core package — `client.py` (API, playlists, download), `gui_modern.py` (CustomTkinter GUI entry), `cli.py` (CLI), `utils.py` (helpers).
- `packaging/macos/`: PyInstaller spec and macOS app assets.
- `scripts/`: Build helpers (`build_macos_dmg.sh`).
- `dist/`, `build/`: PyInstaller outputs (generated).
- `test_api.py`, `test_fields.py`: Small GraphQL probing scripts.

## Build, Test, and Development Commands
- Env setup: `python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt`.
- GUI run: `python -m dlive_downloader` (uses CustomTkinter).
- CLI run: `python -m dlive_downloader.cli <vod_url> --list` or `--quality 1 --outdir ~/Downloads`.
- macOS app build: `SKIP_CLEAN=1 ./scripts/build_macos_dmg.sh` (uses PyInstaller, writes to `dist/`; caches under `.pyinstaller_cache`).
- Cleanup cache if needed: `rm -rf .pyinstaller_cache .pyinstaller_config`.

## Coding Style & Naming Conventions
- Python 3.11+ style with type hints and dataclasses where appropriate.
- Prefer explicit logging (`logging.getLogger(__name__)`) over prints (GUI uses `messagebox` for user-facing errors).
- File/slug naming via `slugify` helpers; keep filenames ASCII-safe.
- UI strings currently Turkish; maintain consistency for new UI text.

## Testing Guidelines
- No formal test suite; quick checks:
  - `python test_api.py <permlink_or_url>` to inspect GraphQL responses.
  - `python test_fields.py` to probe available GraphQL fields.
- For downloader changes, run CLI with a sample VOD URL and verify variants list + download completes.

## Commit & Pull Request Guidelines
- Commits: concise, imperative subjects (e.g., “Handle missing playback URL”, “Bundle CustomTkinter data”).
- PRs: describe behavior change, testing done (commands/URLs used), and any packaging impact (`scripts/build_macos_dmg.sh`, PyInstaller outputs). Include screenshots/gifs for GUI updates when feasible.

## Security & Configuration Tips
- Network calls hit `https://graphigo.prd.dlive.tv/` and playback CDN; avoid hardcoding credentials.
- Ensure the Python interpreter has Tk support when working on GUI/packaging; Homebrew python-tk or python.org builds are recommended. Set `TKCONSOLE=0` is handled in `__main__`.

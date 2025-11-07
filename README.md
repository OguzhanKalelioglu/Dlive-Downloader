# DLive Downloader

DLive Downloader is a modernised fork of the original `dlive-dl.py` utility. It
allows you to fetch past broadcasts from [dlive.tv](https://dlive.tv) either from
the command line or through a graphical interface that works out of the box on
macOS, Windows and Linux.

## Highlights

- ✅ Robust download pipeline with retries and safer file handling
- ✅ Lists every available quality level before downloading
- ✅ Cleans file names so that saved videos work across operating systems
- ✅ Tkinter based desktop app where you can paste a URL, choose the download
  folder and follow the progress visually
- ✅ Instructions for packaging the GUI into a macOS `.app` bundle and `.dmg`
  installer

## Requirements

- Python 3.9 or later
- `pip install -r requirements.txt`
  - Installs `requests` and `tqdm`. Tkinter ships with the standard CPython
    distribution on macOS. If you are using a minimal Python installation make
    sure Tk is available.

## Installing the dependencies

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Command line usage

The legacy `dlive-dl.py` file is still available for backwards compatibility,
but the new CLI lives at `dlive_downloader.cli`.

```bash
python -m dlive_downloader.cli -h
```

Typical download workflow:

```bash
# List available qualities
python -m dlive_downloader.cli --list https://dlive.tv/p/user+vod_id

# Download the best quality (index 1)
python -m dlive_downloader.cli https://dlive.tv/p/user+vod_id

# Download a specific quality to a custom folder and file name
python -m dlive_downloader.cli \
    --quality 3 \
    --outdir "~/Movies/DLive" \
    --filename "awesome-stream.mp4" \
    https://dlive.tv/p/user+vod_id
```

## Graphical interface

Launch the Tkinter desktop experience with:

```bash
python -m dlive_downloader.gui
```

Steps:

1. Paste the VOD URL into the text box.
2. Press **Bilgileri Getir** to load the stream metadata and available quality
   levels.
3. Select the quality you want and choose the destination folder.
4. Click **İndir**. Progress and status updates are displayed at the bottom of
   the window.

The GUI is thread-safe and resilient to temporary network issues; you can cancel
and retry as many times as you like without leaving orphaned files behind.

## Building a macOS application bundle

The repository ships with a repeatable packaging recipe so you can turn the GUI
into both a `.app` bundle and a distributable `.dmg` file straight after
cloning. All commands below must be executed on macOS because they rely on
utilities that only ship there.

### One-shot build script

The `scripts/build_macos_dmg.sh` helper automates the full workflow:

```bash
# 1) Prepare your Python environment
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install pyinstaller

# 2) Run the packaging script (from the project root)
bash scripts/build_macos_dmg.sh
```

The script performs the following steps for you:

1. Runs PyInstaller using the included
   [`packaging/macos/dlive_downloader.spec`](packaging/macos/dlive_downloader.spec)
   file. This produces `dist/DLive Downloader.app`.
2. Looks for the community [`create-dmg`](https://github.com/create-dmg/create-dmg)
   utility. If it is installed, the script generates a disk image with it.
3. Falls back to the built-in `hdiutil` command if `create-dmg` is not present,
   producing `dist/DLive-Downloader.dmg`.

When the script finishes you will have:

- `dist/DLive Downloader.app`: ready to be copied into `/Applications`.
- `dist/DLive-Downloader.dmg`: drag-and-drop installer that you can share with
  other macOS users.

### Manual packaging (advanced)

If you prefer to execute each step yourself, the manual commands are:

1. Activate your virtual environment and install the requirements (see above).
2. Install PyInstaller: `pip install pyinstaller`.
3. Build the application bundle with the provided spec:

   ```bash
   pyinstaller packaging/macos/dlive_downloader.spec
   ```

4. Create the installer disk image:

   ```bash
   hdiutil create \
       -volname "DLive Downloader" \
       -srcfolder "dist/DLive Downloader.app" \
       -ov \
       -format UDZO \
       dist/DLive-Downloader.dmg
   ```

You can substitute the last command with any alternative `.dmg` generator such
as `create-dmg` if you need code signing or custom backgrounds. The resulting
`.dmg` file behaves like any native macOS installer: double-click it and drag
`DLive Downloader.app` into the Applications folder.

## Troubleshooting

- **API errors** – If the DLive GraphQL API rate limits you, the downloader
  automatically retries a handful of times. Persistent failures are shown in the
  UI or CLI output with the exact error message from the service.
- **Network hiccups** – Each video segment download is retried transparently.
  You can rerun the tool; partially downloaded temporary files are cleaned up
  automatically.
- **Tkinter not available** – Install the official CPython build from
  python.org, which includes Tk. Homebrew users can install
  `brew install python-tk@3.11` and recreate the virtual environment.

## License

This project remains under the original license of the upstream repository. See
[`LICENSE`](LICENSE) if available in your checkout.

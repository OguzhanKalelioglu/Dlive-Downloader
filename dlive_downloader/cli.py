"""Command line interface for the DLive downloader."""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Optional

from tqdm import tqdm

from .client import (
    Broadcast,
    DLiveAPIError,
    DLiveDownloader,
    PlaylistError,
    StreamVariant,
    slugify,
)
from .utils import extract_permlink


logger = logging.getLogger(__name__)


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="[%(levelname)s] %(message)s")


def list_variants(broadcast: Broadcast, variants: list[StreamVariant]) -> None:
    header = f"{broadcast.creator_name} - {broadcast.title}"
    if broadcast.duration_seconds:
        mins, secs = divmod(broadcast.duration_seconds, 60)
        hrs, mins = divmod(mins, 60)
        duration = f" ({int(hrs):02}:{int(mins):02}:{int(secs):02})"
    else:
        duration = ""
    print(header + duration)
    for variant in variants:
        print(f"{variant.index}. {variant.display_name()}")


def download_variant(
    downloader: DLiveDownloader,
    broadcast: Broadcast,
    variants: list[StreamVariant],
    index: int,
    output_dir: Path,
    filename: Optional[str] = None,
) -> Path:
    try:
        variant = variants[index - 1]
    except IndexError as exc:
        raise ValueError("Selected quality does not exist.") from exc

    progress_bar: Optional[tqdm] = None

    def update_progress(completed: int, total: int, stage: str) -> None:
        nonlocal progress_bar
        description = "Downloading segments" if stage == "segments" else "Merging segments"
        if progress_bar is None or progress_bar.desc != description or progress_bar.total != total:
            if progress_bar is not None:
                progress_bar.close()
            progress_bar = tqdm(total=total, unit="seg", desc=description)
        if total:
            progress_bar.update(completed - progress_bar.n)
        if completed >= total and progress_bar is not None:
            progress_bar.close()
            progress_bar = None

    output = downloader.download_variant(
        broadcast=broadcast,
        variant=variant,
        output_directory=output_dir,
        filename=filename,
        progress_callback=update_progress,
    )
    if progress_bar is not None:
        progress_bar.close()
    return output


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Download DLive past broadcasts")
    parser.add_argument("url", help="DLive VOD URL")
    parser.add_argument(
        "-l",
        "--list",
        action="store_true",
        help="Only list available qualities without downloading",
    )
    parser.add_argument(
        "-q",
        "--quality",
        type=int,
        default=1,
        metavar="INDEX",
        help="Quality index to download (1 = best)",
    )
    parser.add_argument(
        "-o",
        "--outdir",
        type=Path,
        default=Path.cwd(),
        help="Directory to save the video",
    )
    parser.add_argument(
        "-f",
        "--filename",
        type=str,
        help="Optional custom file name (without directories)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    _configure_logging(args.verbose)

    downloader = DLiveDownloader()
    try:
        permlink = extract_permlink(args.url)
        broadcast = downloader.fetch_broadcast(permlink)
        variants = downloader.list_variants(broadcast.playback_url)
    except (ValueError, DLiveAPIError, PlaylistError) as exc:  # type: ignore[name-defined]
        logger.error("%s", exc)
        return 1
    except Exception:  # pragma: no cover - fallback logging
        logger.exception("Beklenmeyen hata")
        return 1

    if args.list:
        list_variants(broadcast, variants)
        return 0

    output_dir = args.outdir.expanduser()
    filename = args.filename
    if filename:
        filename = slugify(filename)
        if not filename.lower().endswith(".mp4"):
            filename += ".mp4"

    try:
        output = download_variant(
            downloader=downloader,
            broadcast=broadcast,
            variants=variants,
            index=args.quality,
            output_dir=output_dir,
            filename=filename,
        )
    except ValueError as exc:
        logger.error("%s", exc)
        return 1
    except (DLiveAPIError, PlaylistError) as exc:
        logger.error("%s", exc)
        return 1
    except Exception:  # pragma: no cover
        logger.exception("İndirme sırasında beklenmeyen hata")
        return 1

    print(f"Video kaydedildi: {output}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

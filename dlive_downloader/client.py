"""Core client logic for interacting with the DLive APIs and media playlists."""
from __future__ import annotations

import dataclasses
import logging
import re
import shutil
import tempfile
from pathlib import Path
from typing import Callable, Iterable, List, Optional
from urllib.parse import urljoin

import requests
from requests import Response
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


logger = logging.getLogger(__name__)

GRAPHQL_ENDPOINT = "https://graphigo.prd.dlive.tv/"
GRAPHQL_QUERY = (
    "query PastBroadcastPage($permlink: String!) { "
    "pastBroadcast(permlink: $permlink) { "
    "id title duration playbackUrl createdAt thumbnailUrl "
    "creator { displayname username } } }"
)


class DLiveAPIError(RuntimeError):
    """Raised when the DLive GraphQL API returns an unexpected response."""


class PlaylistError(RuntimeError):
    """Raised when the playlist manifest could not be parsed."""


@dataclasses.dataclass(frozen=True)
class Broadcast:
    """Metadata about a past broadcast on DLive."""

    id: str
    permlink: str
    title: str
    creator_name: str
    playback_url: str
    duration_seconds: Optional[int] = None


@dataclasses.dataclass(frozen=True)
class StreamVariant:
    """A downloadable variant of a broadcast stream."""

    index: int
    playlist_url: str
    quality_label: str
    resolution: Optional[str]
    bandwidth: Optional[int]

    def display_name(self) -> str:
        resolution = self.resolution or "?"
        label = self.quality_label
        bitrate = f" @ {self.bandwidth // 1000} kbps" if self.bandwidth else ""
        return f"{label} ({resolution}){bitrate}"


ProgressCallback = Callable[[int, int, str], None]


def _create_retrying_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=5,
        connect=5,
        read=5,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET", "POST"),
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update(
        {
            "User-Agent": "dlive-downloader/2.0 (+https://github.com/)",
            "Accept": "application/json, text/plain, */*",
        }
    )
    return session


class DLiveDownloader:
    """High level facade that downloads DLive past broadcasts."""

    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or _create_retrying_session()

    # ------------------------------------------------------------------
    # API helpers
    # ------------------------------------------------------------------
    def fetch_broadcast(self, permlink: str) -> Broadcast:
        response = self._post_graphql(permlink)
        try:
            payload = response.json()
        except ValueError as exc:
            raise DLiveAPIError("API yanıtı çözümlenemedi") from exc
        logger.debug("GraphQL response: %s", payload)

        if "errors" in payload:
            message = "\n".join(error.get("message", "Unknown error") for error in payload["errors"])
            raise DLiveAPIError(message)

        data = payload.get("data", {})
        broadcast = data.get("pastBroadcast")
        if not broadcast:
            raise DLiveAPIError("Broadcast not found or not accessible.")

        duration = broadcast.get("duration")
        if isinstance(duration, dict):  # Some responses wrap the duration
            duration = duration.get("sec") or duration.get("seconds")
        if duration is not None:
            try:
                duration = int(float(duration))
            except (TypeError, ValueError):
                duration = None

        creator = broadcast.get("creator") or {}
        creator_name = creator.get("displayname") or creator.get("username") or "unknown"

        broadcast_id = broadcast.get("id") or permlink

        playback_url = broadcast.get("playbackUrl")
        if not playback_url:
            raise DLiveAPIError("Broadcast is missing a playback URL.")

        return Broadcast(
            id=str(broadcast_id),
            permlink=permlink,
            title=broadcast.get("title") or permlink,
            creator_name=creator_name,
            playback_url=playback_url,
            duration_seconds=int(duration) if duration is not None else None,
        )

    def list_variants(self, playback_url: str) -> List[StreamVariant]:
        master_playlist = self._fetch_text(playback_url)
        return self._parse_master_playlist(master_playlist, playback_url)

    # ------------------------------------------------------------------
    # Download helpers
    # ------------------------------------------------------------------
    def download_variant(
        self,
        broadcast: Broadcast,
        variant: StreamVariant,
        output_directory: Path,
        progress_callback: Optional[ProgressCallback] = None,
        filename: Optional[str] = None,
    ) -> Path:
        output_directory = Path(output_directory)
        output_directory.mkdir(parents=True, exist_ok=True)

        final_name = filename or self._build_filename(broadcast, variant)
        output_path = output_directory / final_name

        playlist_text = self._fetch_text(variant.playlist_url)
        segment_urls = list(self._parse_media_playlist(playlist_text, variant.playlist_url))
        total_segments = len(segment_urls)
        if total_segments == 0:
            raise PlaylistError("Media playlist did not contain any segments.")

        tmp_dir = Path(tempfile.mkdtemp(prefix="dlive_segments_"))
        logger.debug("Created temporary directory %s", tmp_dir)
        try:
            downloaded_files = []
            for idx, segment_url in enumerate(segment_urls, start=1):
                segment_path = tmp_dir / f"{idx:05d}.ts"
                self._download_to_file(segment_url, segment_path)
                downloaded_files.append(segment_path)
                if progress_callback:
                    progress_callback(idx, total_segments, "segments")

            self._merge_segments(downloaded_files, output_path, progress_callback)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            logger.debug("Cleaned up temporary directory %s", tmp_dir)

        return output_path

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _post_graphql(self, permlink: str) -> Response:
        response = self.session.post(
            GRAPHQL_ENDPOINT,
            json={
                "operationName": "PastBroadcastPage",
                "variables": {"permlink": permlink},
                "query": GRAPHQL_QUERY,
            },
            timeout=20,
        )
        response.raise_for_status()
        return response

    def _fetch_text(self, url: str) -> str:
        response = self.session.get(url, timeout=20)
        response.raise_for_status()
        response.encoding = response.encoding or "utf-8"
        return response.text

    def _parse_master_playlist(self, playlist_text: str, base_url: str) -> List[StreamVariant]:
        variants: List[StreamVariant] = []
        lines = [line.strip() for line in playlist_text.splitlines() if line.strip()]
        index = 0
        for i, line in enumerate(lines):
            if not line.startswith("#EXT-X-STREAM-INF"):
                continue
            attributes = self._parse_attributes(line)
            try:
                playlist_path = lines[i + 1]
            except IndexError as exc:  # pragma: no cover - defensive
                raise PlaylistError("Malformed master playlist: missing variant URL") from exc
            playlist_url = urljoin(base_url, playlist_path)
            resolution = attributes.get("RESOLUTION")
            quality = attributes.get("VIDEO") or attributes.get("NAME") or attributes.get("RESOLUTION")
            bandwidth = attributes.get("AVERAGE-BANDWIDTH") or attributes.get("BANDWIDTH")
            bandwidth_value = None
            if bandwidth:
                try:
                    bandwidth_value = int(float(bandwidth))
                except ValueError:
                    bandwidth_value = None

            variants.append(
                StreamVariant(
                    index=index + 1,
                    playlist_url=playlist_url,
                    quality_label=quality or f"Variant {index + 1}",
                    resolution=resolution,
                    bandwidth=bandwidth_value,
                )
            )
            index += 1

        if not variants:
            raise PlaylistError("No variants found in master playlist.")
        return variants

    def _parse_media_playlist(self, playlist_text: str, base_url: str) -> Iterable[str]:
        for line in playlist_text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            yield urljoin(base_url, stripped)

    @staticmethod
    def _parse_attributes(line: str) -> dict:
        attributes: dict = {}
        pattern = re.compile(r"(?P<key>[A-Z0-9\-]+)=(?P<value>\"[^\"]*\"|[^,]*)")
        for match in pattern.finditer(line):
            key = match.group("key")
            value = match.group("value").strip('"')
            attributes[key] = value
        return attributes

    def _download_to_file(self, url: str, destination: Path) -> None:
        with self.session.get(url, stream=True, timeout=20) as response:
            response.raise_for_status()
            with open(destination, "wb") as output:
                for chunk in response.iter_content(chunk_size=512 * 1024):
                    if chunk:
                        output.write(chunk)

    def _merge_segments(
        self,
        segments: List[Path],
        output_path: Path,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> None:
        total_segments = len(segments)
        with open(output_path, "wb") as merged:
            for index, segment in enumerate(segments, start=1):
                with open(segment, "rb") as source:
                    shutil.copyfileobj(source, merged)
                if progress_callback:
                    progress_callback(index, total_segments, "merge")

    @staticmethod
    def _build_filename(broadcast: Broadcast, variant: StreamVariant) -> str:
        title_slug = slugify(broadcast.title)
        creator_slug = slugify(broadcast.creator_name)
        variant_slug = slugify(variant.quality_label or variant.resolution or "variant")
        return f"{creator_slug}_{title_slug}_{variant_slug}.mp4"


_slugify_pattern = re.compile(r"[^A-Za-z0-9._-]+")


def slugify(value: str) -> str:
    value = value or "video"
    sanitized = _slugify_pattern.sub("-", value.strip())
    sanitized = sanitized.strip("-_") or "video"
    return sanitized[:150]

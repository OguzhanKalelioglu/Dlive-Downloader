"""Core client logic for interacting with the DLive APIs and media playlists."""
from __future__ import annotations

import dataclasses
import logging
import re
import shutil
import subprocess
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
    "id title length playbackUrl createdAt thumbnailUrl viewCount "
    "creator { displayname username } } }"
)
GRAPHQL_RECENT_BROADCASTS = (
    "query PastBroadcastList($displayname: String!, $first: Int!) { "
    "userByDisplayName(displayname: $displayname) { "
    "displayname username "
    "pastBroadcastsV2(first: $first) { "
    "list { id permlink title length createdAt playbackUrl viewCount } } } }"
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
    created_at_ms: Optional[int] = None
    duration_seconds: Optional[int] = None


@dataclasses.dataclass(frozen=True)
class StreamVariant:
    """A downloadable variant of a broadcast stream."""

    index: int
    playlist_url: str
    quality_label: str
    resolution: Optional[str]
    bandwidth: Optional[int]

    def display_name(self, duration_seconds: Optional[int] = None) -> str:
        resolution = self.resolution or "?"
        label = self.quality_label
        bitrate = f" @ {self.bandwidth // 1000} kbps" if self.bandwidth else ""
        size_hint = ""
        if duration_seconds and self.bandwidth:
            estimated_bytes = (self.bandwidth * duration_seconds) / 8  # bits to bytes
            size_hint = f" · ~{_human_size(estimated_bytes)}"
        return f"{label} ({resolution}){bitrate}{size_hint}"


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


def _human_size(byte_count: float) -> str:
    """Return a human friendly size string for the given byte count."""
    units = ("B", "KB", "MB", "GB", "TB")
    size = float(byte_count)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.1f} {unit}"
        size /= 1024


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

        # API now uses "length" instead of "duration" (in seconds)
        duration = broadcast.get("length")
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
            created_at_ms=self._safe_int(broadcast.get("createdAt")),
            duration_seconds=int(duration) if duration is not None else None,
        )

    def list_variants(self, playback_url: str) -> List[StreamVariant]:
        master_playlist = self._fetch_text(playback_url)
        return self._parse_master_playlist(master_playlist, playback_url)

    def list_recent_broadcasts(self, displayname: str, first: int = 15) -> List[Broadcast]:
        payload = {
            "operationName": "PastBroadcastList",
            "variables": {"displayname": displayname, "first": int(first)},
            "query": GRAPHQL_RECENT_BROADCASTS,
        }
        logger.debug("Recent broadcasts request: %s", payload)
        response = self.session.post(GRAPHQL_ENDPOINT, json=payload, timeout=20)
        try:
            response.raise_for_status()
            data = response.json()
        except Exception as exc:
            raise DLiveAPIError("Yayın listesi alınamadı") from exc

        if "errors" in data:
            message = "\n".join(error.get("message", "Unknown error") for error in data["errors"])
            raise DLiveAPIError(message)

        user = (data.get("data") or {}).get("userByDisplayName")
        if not user:
            raise DLiveAPIError("Kullanıcı bulunamadı.")

        broadcasts = (((user.get("pastBroadcastsV2") or {}).get("list")) or [])
        results: List[Broadcast] = []
        for item in broadcasts:
            playback_url = item.get("playbackUrl")
            permlink = item.get("permlink")
            if not playback_url or not permlink:
                continue
            duration = self._safe_int(item.get("length"))
            created_at = self._safe_int(item.get("createdAt"))
            results.append(
                Broadcast(
                    id=str(item.get("id") or permlink),
                    permlink=permlink,
                    title=item.get("title") or permlink,
                    creator_name=user.get("displayname") or user.get("username") or displayname,
                    playback_url=playback_url,
                    created_at_ms=created_at,
                    duration_seconds=duration,
                )
            )
        if not results:
            raise DLiveAPIError("Bu kullanıcı için geçmiş yayın bulunamadı.")
        return results

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
        if not Path(final_name).suffix:
            final_name += ".mp4"
        final_path = output_directory / final_name

        playlist_text = self._fetch_text(variant.playlist_url)
        init_url, segment_urls = self._parse_media_playlist(playlist_text, variant.playlist_url)
        total_segments = len(segment_urls) + (1 if init_url else 0)
        if len(segment_urls) == 0 and not init_url:
            raise PlaylistError("Media playlist did not contain any segments.")

        is_ts_playlist = init_url is None
        needs_remux = is_ts_playlist and final_path.suffix.lower() == ".mp4"
        merge_target = final_path.with_suffix(".ts") if needs_remux else final_path
        output_path = merge_target

        tmp_dir = Path(tempfile.mkdtemp(prefix="dlive_segments_"))
        logger.debug("Created temporary directory %s", tmp_dir)
        try:
            downloaded_files = []
            part_index = 0

            if init_url:
                part_index += 1
                init_path = tmp_dir / f"{part_index:05d}_init.mp4"
                self._download_to_file(init_url, init_path)
                downloaded_files.append(init_path)
                if progress_callback:
                    progress_callback(part_index, total_segments, "segments")

            for segment_url in segment_urls:
                part_index += 1
                segment_path = tmp_dir / f"{part_index:05d}.ts"
                self._download_to_file(segment_url, segment_path)
                downloaded_files.append(segment_path)
                if progress_callback:
                    progress_callback(part_index, total_segments, "segments")

            self._merge_segments(downloaded_files, merge_target, progress_callback)
            if needs_remux:
                output_path = self._remux_ts_to_mp4(merge_target, final_path, progress_callback)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            logger.debug("Cleaned up temporary directory %s", tmp_dir)

        return output_path

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _post_graphql(self, permlink: str) -> Response:
        payload = {
            "operationName": "PastBroadcastPage",
            "variables": {"permlink": permlink},
            "query": GRAPHQL_QUERY,
        }
        logger.debug("GraphQL Request: %s", payload)
        
        response = self.session.post(
            GRAPHQL_ENDPOINT,
            json=payload,
            timeout=20,
        )
        
        # Log response details before raising error
        logger.debug("GraphQL Response Status: %d", response.status_code)
        logger.debug("GraphQL Response Body: %s", response.text[:500])
        
        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError as exc:
            # Try to parse error details
            try:
                error_data = response.json()
                error_msg = f"API Hatası ({response.status_code}): {error_data}"
            except:
                error_msg = f"API Hatası ({response.status_code}): {response.text[:200]}"
            raise DLiveAPIError(error_msg) from exc
        
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

    def _parse_media_playlist(self, playlist_text: str, base_url: str) -> tuple[Optional[str], List[str]]:
        """
        Parse media playlist and return (init_segment_url, segment_urls).

        Supports fMP4 playlists that include an #EXT-X-MAP init segment entry.
        """
        init_url: Optional[str] = None
        segments: List[str] = []

        for line in playlist_text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("#EXT-X-MAP"):
                attrs = self._parse_attributes(stripped)
                uri = attrs.get("URI")
                if uri:
                    init_url = urljoin(base_url, uri)
                continue
            if stripped.startswith("#"):
                continue
            segments.append(urljoin(base_url, stripped))

        return init_url, segments

    @staticmethod
    def _parse_attributes(line: str) -> dict:
        attributes: dict = {}
        pattern = re.compile(r"(?P<key>[A-Z0-9\\-]+)=(?P<value>\"[^\"]*\"|[^,]*)")
        for match in pattern.finditer(line):
            key = match.group("key")
            value = match.group("value").strip('"')
            attributes[key] = value
        return attributes

    @staticmethod
    def _safe_int(value) -> Optional[int]:
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None

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

    def _remux_ts_to_mp4(
        self,
        ts_path: Path,
        final_path: Path,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> Path:
        """Repackage a TS container into a real MP4 when ffmpeg is available."""
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            logger.warning("FFmpeg bulunamadı, TS dosyası kaydedildi: %s", ts_path)
            return ts_path

        if progress_callback:
            progress_callback(0, 1, "remux")

        command = [
            ffmpeg,
            "-y",
            "-i",
            str(ts_path),
            "-c",
            "copy",
            "-bsf:a",
            "aac_adtstoasc",
            str(final_path),
        ]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            stderr_line = (result.stderr or "").splitlines()[:1]
            logger.warning(
                "FFmpeg remux başarısız (exit %s): %s",
                result.returncode,
                stderr_line[0] if stderr_line else "bilinmeyen hata",
            )
            return ts_path

        ts_path.unlink(missing_ok=True)
        if progress_callback:
            progress_callback(1, 1, "remux")
        return final_path

    @staticmethod
    def _build_filename(
        broadcast: Broadcast,
        variant: StreamVariant,
        extension: str = ".mp4",
    ) -> str:
        title_slug = slugify(broadcast.title)
        creator_slug = slugify(broadcast.creator_name)
        variant_slug = slugify(variant.quality_label or variant.resolution or "variant")
        suffix = extension if extension.startswith(".") else f".{extension}"
        return f"{creator_slug}_{title_slug}_{variant_slug}{suffix}"


_slugify_pattern = re.compile(r"[^A-Za-z0-9._-]+")


def slugify(value: str) -> str:
    value = value or "video"
    sanitized = _slugify_pattern.sub("-", value.strip())
    sanitized = sanitized.strip("-_") or "video"
    return sanitized[:150]

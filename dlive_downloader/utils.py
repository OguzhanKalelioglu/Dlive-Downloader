"""Shared utility helpers for the downloader package."""
from __future__ import annotations

from urllib.parse import urlparse


def extract_permlink(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path or ""
    permlink = path.rstrip("/").split("/")[-1]
    if not permlink:
        raise ValueError("VOD bağlantısından permlink alınamadı")
    return permlink

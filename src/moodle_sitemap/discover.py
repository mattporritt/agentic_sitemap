# Copyright (c) Moodle Pty Ltd. All rights reserved.
# Licensed under the Moodle Community License v1.3.
# See LICENSE.md in the repository root for full terms.
# Commercial use requires a separate written agreement with Moodle.
from __future__ import annotations

from collections.abc import Iterable
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

TRACKING_QUERY_KEYS = {
    "utm_campaign",
    "utm_content",
    "utm_medium",
    "utm_source",
    "utm_term",
}

SECRET_QUERY_KEYS = {
    "password",
    "pass",
    "sesskey",
    "token",
    "auth",
    "key",
    "apikey",
    "api_key",
}

UNSAFE_PATH_PARTS = {
    "logout",
    "delete",
    "remove",
    "drop",
    "purge",
    "unsubscribe",
}

UNSAFE_QUERY_KEYS = {
    "delete",
    "remove",
    "confirm",
    "logout",
}

DOWNLOAD_FILE_EXTENSIONS = {
    ".csv",
    ".zip",
    ".gz",
    ".tgz",
    ".bz2",
    ".xz",
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".webp",
    ".mp3",
    ".mp4",
}


def normalize_url(url: str, *, base_url: str | None = None) -> str:
    absolute = urljoin(base_url, url) if base_url else url
    parsed = urlparse(absolute)
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    path = _normalize_path(parsed.path or "/")

    filtered_query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in TRACKING_QUERY_KEYS
    ]
    query = urlencode(sorted(filtered_query))

    return urlunparse((scheme, netloc, path, "", query, ""))


def _normalize_path(path: str) -> str:
    normalized = path or "/"
    if not normalized.startswith("/"):
        normalized = f"/{normalized}"
    if normalized != "/" and normalized.endswith("/"):
        normalized = normalized.rstrip("/")
    return normalized


def canonicalize_resolved_url(requested_url: str, final_url: str) -> str:
    del requested_url
    return normalize_url(final_url)


def same_origin(url: str, origin: str) -> bool:
    parsed = urlparse(url)
    site = urlparse(origin)
    return (parsed.scheme, parsed.netloc) == (site.scheme, site.netloc)


def is_safe_link(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme and parsed.scheme not in {"http", "https"}:
        return False

    lowered_path = parsed.path.lower()
    if any(lowered_path.endswith(extension) for extension in DOWNLOAD_FILE_EXTENSIONS):
        return False
    if any(part in lowered_path for part in UNSAFE_PATH_PARTS):
        return False

    query_keys = {key.lower() for key, _ in parse_qsl(parsed.query, keep_blank_values=True)}
    if query_keys & UNSAFE_QUERY_KEYS:
        return False

    if query_keys & SECRET_QUERY_KEYS:
        return False

    return True


def filter_discovered_links(
    links: Iterable[str],
    *,
    base_url: str,
    origin: str,
) -> list[str]:
    seen: set[str] = set()
    filtered: list[str] = []
    for link in links:
        if not link or link.startswith("#") or link.startswith("javascript:"):
            continue
        normalized = normalize_url(link, base_url=base_url)
        if not same_origin(normalized, origin):
            continue
        if not is_safe_link(normalized):
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        filtered.append(normalized)
    return filtered


def make_page_id(index: int, url: str) -> str:
    parsed = urlparse(url)
    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if parsed.query:
        parts.extend(f"{k}-{v}" for k, v in parse_qsl(parsed.query, keep_blank_values=True))
    slug = "-".join(parts) if parts else "root"
    safe_slug = "".join(ch if ch.isalnum() or ch == "-" else "-" for ch in slug).strip("-") or "root"
    return f"{index:04d}-{safe_slug[:80]}"

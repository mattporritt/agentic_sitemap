from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from moodle_sitemap.models import NetworkEvent

if TYPE_CHECKING:
    from playwright.sync_api import Page, Response

SECRET_KEYS = {
    "password",
    "pass",
    "cookie",
    "authorization",
    "token",
    "access_token",
    "refresh_token",
    "sesskey",
    "apikey",
    "api_key",
}


def _redact_value(key: str, value: str) -> str:
    return "[REDACTED]" if key.lower() in SECRET_KEYS else value


def redact_url(url: str) -> str:
    parsed = urlparse(url)
    query = urlencode(
        [(key, _redact_value(key, value)) for key, value in parse_qsl(parsed.query, keep_blank_values=True)]
    )
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, query, parsed.fragment))


def redact_header_mapping(headers: dict[str, str]) -> dict[str, str]:
    redacted: dict[str, str] = {}
    for key, value in headers.items():
        redacted[key] = _redact_value(key, value)
    return redacted


@dataclass
class NetworkRecorder:
    page: Page
    events: list[NetworkEvent] = field(default_factory=list)

    def attach(self) -> None:
        self.page.on("response", self._handle_response)

    def detach(self) -> None:
        self.page.remove_listener("response", self._handle_response)

    def reset(self) -> None:
        self.events.clear()

    def _handle_response(self, response: Response) -> None:
        request = response.request
        resource_type = request.resource_type
        if resource_type not in {"document", "fetch", "xhr"}:
            return

        content_type = response.headers.get("content-type")
        self.events.append(
            NetworkEvent(
                url=redact_url(response.url),
                method=request.method,
                resource_type=resource_type,
                status=response.status,
                content_type=content_type,
            )
        )

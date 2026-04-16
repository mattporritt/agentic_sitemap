# Copyright (c) Moodle Pty Ltd. All rights reserved.
# Licensed under the Moodle Community License v1.3.
# See LICENSE.md in the repository root for full terms.
# Commercial use requires a separate written agreement with Moodle.
from types import SimpleNamespace

from moodle_sitemap.extract.network import NetworkRecorder, redact_header_mapping, redact_url


class FakePage:
    def __init__(self) -> None:
        self.handlers: dict[str, object] = {}

    def on(self, event: str, handler: object) -> None:
        self.handlers[event] = handler

    def remove_listener(self, event: str, handler: object) -> None:
        if self.handlers.get(event) == handler:
            del self.handlers[event]


def test_redact_url_hides_sensitive_query_values() -> None:
    result = redact_url("https://example.com/lib/ajax/service.php?sesskey=abc&info=test")
    assert result.startswith("https://example.com/lib/ajax/service.php?")
    assert "info=test" in result
    assert "sesskey=%5BREDACTED%5D" in result


def test_redact_header_mapping_hides_sensitive_headers() -> None:
    result = redact_header_mapping({"Authorization": "Bearer 123", "Accept": "application/json"})
    assert result == {"Authorization": "[REDACTED]", "Accept": "application/json"}


def test_network_recorder_attach_handle_and_detach() -> None:
    page = FakePage()
    recorder = NetworkRecorder(page=page)

    recorder.attach()
    assert "response" in page.handlers

    response = SimpleNamespace(
        url="https://example.com/lib/ajax/service.php?sesskey=abc",
        status=200,
        headers={"content-type": "application/json"},
        request=SimpleNamespace(method="POST", resource_type="xhr"),
    )
    recorder._handle_response(response)
    assert recorder.events[0].url.endswith("sesskey=%5BREDACTED%5D")

    recorder.detach()
    assert "response" not in page.handlers

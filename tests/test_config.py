# Copyright (c) Moodle Pty Ltd. All rights reserved.
# Licensed under the Moodle Community License v1.3.
# See LICENSE.md in the repository root for full terms.
# Commercial use requires a separate written agreement with Moodle.
from pathlib import Path

import pytest

from moodle_sitemap.config import load_smoke_config, normalize_browser_engine
from moodle_sitemap.models import BrowserEngine


def write_config(tmp_path: Path, contents: str) -> Path:
    config_path = tmp_path / "config.toml"
    config_path.write_text(contents, encoding="utf-8")
    return config_path


def test_load_smoke_config_reads_expected_values(tmp_path: Path) -> None:
    config_path = write_config(
        tmp_path,
        """
        [site]
        url = "https://example.com"

        [auth]
        username = "admin"
        password = "secret"

        [browser]
        engine = "firefox"
        headless = false

        [run]
        role = "teacher"
        """,
    )

    config = load_smoke_config(config_path)

    assert str(config.site_url) == "https://example.com/"
    assert config.username == "admin"
    assert config.password == "secret"
    assert config.role_profile == "teacher"
    assert config.browser_engine == BrowserEngine.FIREFOX
    assert config.headless is False


def test_load_smoke_config_defaults_browser_values(tmp_path: Path) -> None:
    config_path = write_config(
        tmp_path,
        """
        [site]
        url = "https://example.com"

        [auth]
        username = "admin"
        password = "secret"
        """,
    )

    config = load_smoke_config(config_path)

    assert config.role_profile == "unlabeled"
    assert config.browser_engine == BrowserEngine.CHROMIUM
    assert config.headless is True


def test_load_smoke_config_rejects_missing_values(tmp_path: Path) -> None:
    config_path = write_config(
        tmp_path,
        """
        [site]
        url = "https://example.com"
        """,
    )

    with pytest.raises(ValueError, match="Missing required config value"):
        load_smoke_config(config_path)


def test_normalize_browser_engine_accepts_supported_values() -> None:
    assert normalize_browser_engine("chromium") == BrowserEngine.CHROMIUM
    assert normalize_browser_engine("FIREFOX") == BrowserEngine.FIREFOX


def test_normalize_browser_engine_rejects_unknown_values() -> None:
    with pytest.raises(ValueError, match="Unsupported browser engine"):
        normalize_browser_engine("webkit")

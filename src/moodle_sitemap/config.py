# Copyright (c) Moodle Pty Ltd. All rights reserved.
# Licensed under the Moodle Community License v1.3.
# See LICENSE.md in the repository root for full terms.
# Commercial use requires a separate written agreement with Moodle.
from __future__ import annotations

from pathlib import Path
import tomllib

from pydantic import ValidationError

from moodle_sitemap.models import BrowserEngine, SmokeTestConfig


def normalize_browser_engine(value: str) -> BrowserEngine:
    try:
        return BrowserEngine(value.strip().lower())
    except ValueError as exc:
        allowed = ", ".join(engine.value for engine in BrowserEngine)
        raise ValueError(f"Unsupported browser engine '{value}'. Expected one of: {allowed}.") from exc


def load_smoke_config(path: str | Path) -> SmokeTestConfig:
    config_path = Path(path)
    try:
        raw = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Config file not found: {config_path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"Invalid TOML in config file {config_path}: {exc}") from exc

    site = raw.get("site", {})
    auth = raw.get("auth", {})
    browser = raw.get("browser", {})
    run = raw.get("run", {})

    try:
        return SmokeTestConfig(
            site_url=site["url"],
            username=auth["username"],
            password=auth["password"],
            role_profile=run.get("role", "unlabeled"),
            browser_engine=normalize_browser_engine(browser.get("engine", BrowserEngine.CHROMIUM.value)),
            headless=browser.get("headless", True),
        )
    except KeyError as exc:
        raise ValueError(f"Missing required config value: {exc.args[0]}") from exc
    except ValidationError as exc:
        raise ValueError(f"Invalid config file {config_path}: {exc}") from exc

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from moodle_sitemap.auth import LoginResult, login_appears_successful, login_to_moodle
from moodle_sitemap.browser import open_browser
from moodle_sitemap.config import load_smoke_config
from moodle_sitemap.extract.dom import extract_page_features
from moodle_sitemap.models import PageFeatures, SmokeTestConfig, SmokeTestRecord


@dataclass(slots=True)
class SmokeRunResult:
    config: SmokeTestConfig
    artifact_path: Path
    record: SmokeTestRecord


def run_smoke_test(*, config_path: str | Path, output_dir: str | Path = "output") -> SmokeRunResult:
    config = load_smoke_config(config_path)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    with open_browser(headless=config.headless, engine=config.browser_engine) as session:
        initial_url = str(config.site_url)
        session.page.goto(initial_url, wait_until="domcontentloaded")
        login_result = login_to_moodle(
            page=session.page,
            site_url=initial_url,
            username=config.username,
            password=config.password,
        )
        features = extract_page_features(session.page)
        record = build_smoke_test_record(
            config=config,
            login_result=login_result,
            page_title=session.page.title(),
            features=features,
            login_succeeded=login_appears_successful(session.page),
        )

    artifact_path = output_path / "smoke-test.json"
    artifact_path.write_text(record.model_dump_json(indent=2), encoding="utf-8")
    return SmokeRunResult(config=config, artifact_path=artifact_path, record=record)


def build_smoke_test_record(
    *,
    config: SmokeTestConfig,
    login_result: LoginResult,
    page_title: str | None,
    features: PageFeatures,
    login_succeeded: bool,
) -> SmokeTestRecord:
    return SmokeTestRecord(
        site_url=config.site_url,
        role_profile=config.role_profile,
        browser=config.browser_engine,
        initial_url=str(config.site_url),
        final_url=login_result.final_url,
        page_title=page_title,
        http_status=login_result.response_status,
        body_id=features.body_id,
        body_classes=features.body_classes,
        breadcrumbs=features.breadcrumbs,
        login_succeeded=login_succeeded,
    )

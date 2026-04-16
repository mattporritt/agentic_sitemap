# Copyright (c) Moodle Pty Ltd. All rights reserved.
# Licensed under the Moodle Community License v1.3.
# See LICENSE.md in the repository root for full terms.
# Commercial use requires a separate written agreement with Moodle.
from __future__ import annotations

import json
from pathlib import Path

import typer

from moodle_sitemap.compare_runs import compare_runs
from moodle_sitemap.crawl import CrawlConfig, crawl_site, format_progress_line
from moodle_sitemap.discovery import run_discovery
from moodle_sitemap.models import RuntimeLookupMode
from moodle_sitemap.runtime_contract import (
    build_page_lookup_contract,
    build_path_lookup_contract,
    build_task_validation_contract,
)
from moodle_sitemap.smoke import run_smoke_test
from moodle_sitemap.task_validation import validate_tasks_for_run
from moodle_sitemap.verify import run_verification

app = typer.Typer(help="Moodle-aware authenticated sitemap crawler.")


def parse_bool(value: str) -> bool:
    lowered = value.strip().lower()
    if lowered in {"1", "true", "yes", "y", "on"}:
        return True
    if lowered in {"0", "false", "no", "n", "off"}:
        return False
    raise typer.BadParameter("Expected true or false.")


@app.callback()
def main() -> None:
    """CLI entrypoint."""


def emit_progress(page, current_count: int, max_pages: int) -> None:
    typer.echo(format_progress_line(page, current_count=current_count, max_pages=max_pages))


@app.command()
def crawl(
    site_url: str = typer.Option(..., help="Base Moodle site URL."),
    username: str = typer.Option(..., help="Moodle username."),
    password: str = typer.Option(..., help="Moodle password."),
    output: Path = typer.Option(..., help="Output directory for sitemap artifacts."),
    role_profile: str = typer.Option("unlabeled", help="Role/profile label for this crawl, for example admin or student."),
    max_pages: int = typer.Option(200, min=1, help="Maximum pages to crawl."),
    headless: str = typer.Option("true", help="Whether to run the browser headless."),
) -> None:
    manifest = crawl_site(
        CrawlConfig(
            site_url=site_url,
            username=username,
            password=password,
            output_dir=output,
            role_profile=role_profile,
            max_pages=max_pages,
            headless=parse_bool(headless),
        ),
        progress_callback=emit_progress,
    )
    typer.echo(f"Crawled {manifest.visited_pages} pages into {output}")


@app.command()
def smoke(
    config: Path = typer.Option(..., help="Path to the smoke test TOML config file."),
    output: Path = typer.Option(Path("output"), help="Output directory for the smoke test artifact."),
) -> None:
    try:
        result = run_smoke_test(config_path=config, output_dir=output)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    except RuntimeError as exc:
        typer.echo(f"Smoke test failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if not result.record.login_succeeded:
        typer.echo("Smoke test failed: login did not succeed.", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"Smoke test wrote {result.artifact_path}")


@app.command()
def verify(
    config: Path = typer.Option(..., help="Path to the TOML config file used for smoke and crawl verification."),
    max_pages: int = typer.Option(10, min=1, help="Maximum pages to crawl during verification."),
    output_root: Path = typer.Option(
        Path("verification-runs"),
        help="Root directory for timestamped verification runs.",
    ),
) -> None:
    try:
        result = run_verification(
            config_path=config,
            max_pages=max_pages,
            base_dir=output_root,
            progress_callback=emit_progress,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    except RuntimeError as exc:
        typer.echo(f"Verification failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(
        f"Verification run wrote {result.smoke.artifact_path} and crawled "
        f"{result.visited_pages} pages into {result.run_dir}"
    )


@app.command()
def discover(
    config: Path = typer.Option(..., help="Path to the TOML config file used for discovery crawling."),
    max_pages: int = typer.Option(200, min=1, help="Maximum pages to crawl during discovery."),
    max_depth: int = typer.Option(4, min=1, help="Maximum link depth for discovery crawling."),
    output_root: Path = typer.Option(
        Path("discovery-runs"),
        help="Root directory for timestamped discovery runs.",
    ),
) -> None:
    try:
        result = run_discovery(
            config_path=config,
            max_pages=max_pages,
            max_depth=max_depth,
            base_dir=output_root,
            progress_callback=emit_progress,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    except RuntimeError as exc:
        typer.echo(f"Discovery failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(
        f"Discovery run wrote {result.summary_path} and crawled "
        f"{result.manifest.visited_pages} pages into {result.run_dir}"
    )


@app.command("compare-runs")
def compare_runs_command(
    left: Path = typer.Option(..., help="Path to the left run directory."),
    right: Path = typer.Option(..., help="Path to the right run directory."),
    output_root: Path = typer.Option(
        Path("comparison-runs"),
        help="Root directory for timestamped run comparisons.",
    ),
) -> None:
    try:
        result = compare_runs(left_run_dir=left, right_run_dir=right, base_dir=output_root)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    except FileNotFoundError as exc:
        raise typer.BadParameter(str(exc)) from exc

    typer.echo(
        f"Run comparison wrote {result.json_path} and {result.markdown_path} into {result.output_dir}"
    )


@app.command("validate-tasks")
def validate_tasks_command(
    run: Path = typer.Option(..., help="Path to the saved discovery or crawl run directory."),
    tasks: Path = typer.Option(..., help="Path to the task-validation task spec JSON file."),
    output_root: Path = typer.Option(
        Path("task-validation-runs"),
        help="Root directory for timestamped task-validation results.",
    ),
    json_contract: bool = typer.Option(
        False,
        "--json-contract",
        help="Emit the stable runtime-facing JSON contract envelope.",
    ),
) -> None:
    try:
        result = validate_tasks_for_run(run_dir=run, tasks_path=tasks, base_dir=output_root)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    except FileNotFoundError as exc:
        raise typer.BadParameter(str(exc)) from exc

    if json_contract:
        typer.echo(json.dumps(build_task_validation_contract(result.summary).model_dump(), indent=2, sort_keys=True))
        return

    typer.echo(
        f"Task validation wrote {result.json_path} and {result.markdown_path} into {result.output_dir}"
    )


@app.command("runtime-query")
def runtime_query_command(
    run: Path = typer.Option(..., help="Path to the saved discovery or crawl run directory."),
    lookup_mode: RuntimeLookupMode = typer.Option(..., help="Lookup mode: page, page_type, or path."),
    query: str | None = typer.Option(None, help="Lookup query for page or page_type mode."),
    from_page: str | None = typer.Option(None, help="Source page selector for path mode."),
    to_page: str | None = typer.Option(None, help="Target page selector for path mode."),
    top_k: int = typer.Option(5, min=1, help="Maximum runtime results to return."),
    json_contract: bool = typer.Option(
        False,
        "--json-contract",
        help="Emit the stable runtime-facing JSON contract envelope.",
    ),
) -> None:
    """Query saved sitemap artifacts using the runtime-facing contract surface."""

    if lookup_mode in {RuntimeLookupMode.PAGE, RuntimeLookupMode.PAGE_TYPE}:
        if not query:
            raise typer.BadParameter("--query is required for page and page_type lookups.")
        envelope = build_page_lookup_contract(
            run_dir=run,
            query=query,
            lookup_mode=lookup_mode,
            top_k=top_k,
        )
    elif lookup_mode == RuntimeLookupMode.PATH:
        if not from_page or not to_page:
            raise typer.BadParameter("--from-page and --to-page are required for path lookups.")
        envelope = build_path_lookup_contract(
            run_dir=run,
            from_selector=from_page,
            to_selector=to_page,
            top_k=top_k,
        )
    else:
        raise typer.BadParameter(f"Unsupported runtime lookup mode: {lookup_mode.value}")

    if json_contract:
        typer.echo(json.dumps(envelope.model_dump(), indent=2, sort_keys=True))
        return

    typer.echo(f"Runtime query returned {len(envelope.results)} result(s) for {lookup_mode.value}")
    for result in envelope.results:
        typer.echo(f"[{result.rank}] {result.type} {result.source.canonical_url or result.source.path or '-'}")


if __name__ == "__main__":
    app()

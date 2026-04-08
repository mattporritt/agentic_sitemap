from __future__ import annotations

from pathlib import Path

import typer

from moodle_sitemap.crawl import CrawlConfig, crawl_site, format_progress_line
from moodle_sitemap.discovery import run_discovery
from moodle_sitemap.smoke import run_smoke_test
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
    max_pages: int = typer.Option(200, min=1, help="Maximum pages to crawl."),
    headless: str = typer.Option("true", help="Whether to run the browser headless."),
) -> None:
    manifest = crawl_site(
        CrawlConfig(
            site_url=site_url,
            username=username,
            password=password,
            output_dir=output,
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


if __name__ == "__main__":
    app()

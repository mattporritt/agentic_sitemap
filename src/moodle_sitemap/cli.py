from __future__ import annotations

from pathlib import Path

import typer

from moodle_sitemap.crawl import CrawlConfig, crawl_site
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
        )
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
        result = run_verification(config_path=config, max_pages=max_pages, base_dir=output_root)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    except RuntimeError as exc:
        typer.echo(f"Verification failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(
        f"Verification run wrote {result.smoke.artifact_path} and crawled "
        f"{result.visited_pages} pages into {result.run_dir}"
    )


if __name__ == "__main__":
    app()

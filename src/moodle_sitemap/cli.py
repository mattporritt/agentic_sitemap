from __future__ import annotations

from pathlib import Path

import typer

from moodle_sitemap.crawl import CrawlConfig, crawl_site

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


if __name__ == "__main__":
    app()

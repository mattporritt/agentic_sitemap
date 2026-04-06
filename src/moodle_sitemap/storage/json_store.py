from __future__ import annotations

import json
from pathlib import Path

from moodle_sitemap.models import PageRecord, SiteManifest


class JsonStore:
    def __init__(self, output_dir: str | Path) -> None:
        self.output_dir = Path(output_dir)
        self.pages_dir = self.output_dir / "pages"

    def prepare(self) -> None:
        self.pages_dir.mkdir(parents=True, exist_ok=True)

    def write_page(self, page: PageRecord) -> Path:
        page_path = self.pages_dir / f"{page.page_id}.json"
        page_path.write_text(page.model_dump_json(indent=2), encoding="utf-8")
        return page_path

    def write_manifest(self, manifest: SiteManifest) -> Path:
        manifest_path = self.output_dir / "sitemap.json"
        manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
        return manifest_path

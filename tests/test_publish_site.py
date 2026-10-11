"""Tests for static-site assembly and publication safeguards."""

import json
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

from publish_site import SitePublishingError, publish_site


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href)


class PublishSiteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.outputs = self.root / "outputs"
        self.site = self.root / "site"
        self.outputs.mkdir()
        for filename in (
            "priority_map.html",
            "top_priority_cells.csv",
            "action_report.md",
        ):
            (self.outputs / filename).write_text("synthetic fixture\n", encoding="utf-8")
        (self.outputs / "processing_metadata.json").write_text(
            json.dumps(
                {
                    "scoring": {
                        "city": "Nagpur",
                        "analysis_start_inclusive": "2026-03-01",
                        "analysis_end_inclusive": "2026-05-31",
                    },
                    "license_and_attribution_status": "Verification is pending.",
                }
            ),
            encoding="utf-8",
        )
        (self.outputs / ".env").write_text("SECRET=not-for-publishing", encoding="utf-8")
        (self.outputs / "raw_private_source.csv").write_text(
            "private source data", encoding="utf-8"
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_builds_site_pages_links_headers_and_excludes_unlisted_files(self) -> None:
        result = publish_site(self.outputs, self.site)

        for filename in (
            "index.html",
            "priority_map.html",
            "top_priority_cells.csv",
            "action_report.md",
            "processing_metadata.json",
            "privacy.html",
            "disclaimer.html",
            "404.html",
            "favicon.svg",
            "sitemap.xml",
            "robots.txt",
            "_headers",
        ):
            self.assertTrue((self.site / filename).is_file(), filename)
        self.assertFalse((self.site / ".env").exists())
        self.assertFalse((self.site / "raw_private_source.csv").exists())
        self.assertEqual(result.page_count, 6)

        index = (self.site / "index.html").read_text(encoding="utf-8")
        self.assertIn("Explore the priority map", index)
        self.assertIn('href="top_priority_cells.csv"', index)
        self.assertIn("Accessible text alternative", index)
        self.assertIn("Verification is pending.", index)
        headers = (self.site / "_headers").read_text(encoding="utf-8")
        self.assertIn("Content-Security-Policy:", headers)
        self.assertIn("X-Content-Type-Options: nosniff", headers)

        for page_name in ("index.html", "privacy.html", "disclaimer.html", "404.html"):
            parser = LinkParser()
            parser.feed((self.site / page_name).read_text(encoding="utf-8"))
            for href in parser.links:
                if href.startswith(("https://", "http://", "#", "mailto:")):
                    continue
                self.assertTrue((self.site / href).exists(), f"{page_name}: {href}")

    def test_https_site_url_populates_sitemap_and_robots(self) -> None:
        result = publish_site(
            self.outputs,
            self.site,
            site_url="https://maps.example.org/heat/",
        )
        sitemap = (self.site / "sitemap.xml").read_text(encoding="utf-8")
        robots = (self.site / "robots.txt").read_text(encoding="utf-8")

        self.assertEqual(result.public_url, "https://maps.example.org/heat/")
        self.assertIn("https://maps.example.org/heat/index.html", sitemap)
        self.assertIn("https://maps.example.org/heat/sitemap.xml", robots)

    def test_rejects_non_https_public_url(self) -> None:
        with self.assertRaisesRegex(SitePublishingError, "must be an HTTPS base URL"):
            publish_site(
                self.outputs,
                self.site,
                site_url="http://maps.example.org/",
            )

    def test_requires_phase5_artifacts(self) -> None:
        (self.outputs / "priority_map.html").unlink()
        with self.assertRaisesRegex(SitePublishingError, "missing or unsafe"):
            publish_site(self.outputs, self.site)

    def test_rejects_overlapping_output_and_site_directories(self) -> None:
        with self.assertRaisesRegex(SitePublishingError, "must be separate"):
            publish_site(self.outputs, self.outputs / "site")


if __name__ == "__main__":
    unittest.main()

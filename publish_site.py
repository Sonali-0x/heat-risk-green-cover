"""Assemble the generated analysis artifacts into a static website."""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional
from urllib.parse import urljoin, urlparse

from config import ProjectConfig, load_config


SITE_FILES = (
    "priority_map.html",
    "top_priority_cells.csv",
    "action_report.md",
    "processing_metadata.json",
)
SITEMAP_PAGES = (
    "index.html",
    "priority_map.html",
    "action_report.md",
    "privacy.html",
    "disclaimer.html",
)


class SitePublishingError(RuntimeError):
    """Raised when the static site cannot be safely assembled."""


@dataclass(frozen=True)
class PublishedSite:
    site_dir: Path
    page_count: int
    public_url: Optional[str]


def _validate_public_url(value: Optional[str]) -> Optional[str]:
    if value is None or not value.strip():
        return None
    parsed = urlparse(value.strip())
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise SitePublishingError(
            "SITE_URL must be an HTTPS base URL without credentials, query, or fragment."
        )
    return value.strip().rstrip("/") + "/"


def _read_site_metadata(outputs_dir: Path) -> Dict[str, object]:
    metadata_path = outputs_dir / "processing_metadata.json"
    if metadata_path.is_symlink() or not metadata_path.is_file():
        raise SitePublishingError(
            f"Required Phase 5 artifact is missing or unsafe: {metadata_path}."
        )
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SitePublishingError(
            f"Could not read valid processing metadata from {metadata_path}."
        ) from exc
    if not isinstance(metadata, dict) or not isinstance(metadata.get("scoring"), dict):
        raise SitePublishingError("Processing metadata has an invalid structure.")
    return metadata


def _copy_artifacts(outputs_dir: Path, site_dir: Path) -> None:
    output_root = outputs_dir.resolve()
    for filename in SITE_FILES:
        source = outputs_dir / filename
        if (
            source.is_symlink()
            or not source.is_file()
            or not source.resolve().is_relative_to(output_root)
        ):
            raise SitePublishingError(
                f"Required Phase 5 artifact is missing or unsafe: {source}."
            )
        try:
            content = source.read_bytes()
        except OSError as exc:
            raise SitePublishingError(f"Could not read site artifact {source}.") from exc
        _write_atomic(site_dir / filename, content)


def _write_atomic(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=path.parent, prefix=".partial-", delete=False
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(content)
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def _document(title: str, description: str, body: str, canonical_url: Optional[str]) -> str:
    safe_title = html.escape(title, quote=True)
    safe_description = html.escape(description, quote=True)
    canonical = (
        f'<link rel="canonical" href="{html.escape(canonical_url, quote=True)}">'
        if canonical_url
        else ""
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{safe_title}</title>
  <meta name="description" content="{safe_description}">
  <meta property="og:type" content="website">
  <meta property="og:title" content="{safe_title}">
  <meta property="og:description" content="{safe_description}">
  <meta name="twitter:card" content="summary">
  <meta name="robots" content="index,follow">
  <link rel="icon" href="favicon.svg" type="image/svg+xml">
  {canonical}
  <style>
    :root {{ color-scheme: light; font-family: system-ui, sans-serif; color: #18332b; background: #f4f7f4; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; line-height: 1.6; }}
    header, main, footer {{ width: min(100% - 2rem, 64rem); margin: 0 auto; }}
    header {{ padding: 2rem 0 1rem; }}
    main {{ padding: 0 0 3rem; }}
    footer {{ padding: 1rem 0 2rem; border-top: 1px solid #b7c8bd; }}
    h1, h2 {{ line-height: 1.2; }}
    .panel {{ background: #fff; border: 1px solid #c8d7cd; border-radius: .75rem; padding: 1.25rem; margin: 1rem 0; }}
    .actions {{ display: flex; flex-wrap: wrap; gap: .75rem; margin: 1rem 0; }}
    .button {{ display: inline-block; border-radius: .4rem; padding: .7rem 1rem; font-weight: 700; text-decoration: none; }}
    .primary {{ color: #fff; background: #145c3b; }}
    .secondary {{ color: #174331; background: #e2efe6; border: 1px solid #8aa995; }}
    a {{ color: #075a9c; }}
    a:focus-visible {{ outline: 3px solid #b34b00; outline-offset: 3px; }}
    .notice {{ border-left: .3rem solid #9a4b00; padding-left: 1rem; }}
    @media (max-width: 36rem) {{ header {{ padding-top: 1rem; }} .button {{ width: 100%; text-align: center; }} }}
  </style>
</head>
<body>
  <header><a href="index.html" aria-label="Green Cover and Urban Heat Priority Map home">Project home</a></header>
  <main>{body}</main>
  <footer>
    <nav aria-label="Legal and project links">
      <a href="privacy.html">Privacy</a> ·
      <a href="disclaimer.html">Disclaimer</a> ·
      <a href="https://earthengine.google.com/">Google Earth Engine</a>
    </nav>
  </footer>
</body>
</html>
"""


def _landing_page(
    metadata: Dict[str, object],
    canonical_url: Optional[str],
    outputs_dir: Optional[Path] = None,
) -> str:
    scoring = metadata.get("scoring", {})
    if not isinstance(scoring, dict):
        scoring = {}
    city = html.escape(str(scoring.get("city", "Pilot city")), quote=True)
    start = html.escape(str(scoring.get("analysis_start_inclusive", "")), quote=True)
    end = html.escape(str(scoring.get("analysis_end_inclusive", "")), quote=True)
    license_status = html.escape(
        str(metadata.get("license_and_attribution_status", "Not recorded")),
        quote=True,
    )

    template_path = Path(__file__).resolve().parent / "TerraAtlas.html"
    if template_path.is_file():
        try:
            content = template_path.read_text(encoding="utf-8")
            if canonical_url:
                canonical_tag = f'<link rel="canonical" href="{html.escape(canonical_url, quote=True)}">\n'
                content = content.replace("<head>", f"<head>\n{canonical_tag}", 1)
            content = content.replace(
                '<span id="licenseStatusText">Verification is pending.</span>',
                f'<span id="licenseStatusText">{license_status}</span>',
            )
            if outputs_dir is not None:
                real_data_path = outputs_dir / "terra_atlas_nagpur.json"
                if real_data_path.is_file():
                    try:
                        raw_data = real_data_path.read_text(encoding="utf-8").strip()
                        if raw_data:
                            content = re.sub(
                                r"const NAGPUR_REAL_DATA = \[.*?\];",
                                f"const NAGPUR_REAL_DATA = {raw_data};",
                                content,
                                count=1,
                            )
                    except OSError:
                        pass
            return content
        except OSError:
            pass

    body = f"""
    <h1>Green Cover &amp; Urban Heat Priority Map</h1>
    <p>Explore aggregated satellite and population indicators for {city}, India.
       This is a planning aid, not a site-level assessment.</p>
    <div class="actions">
      <a class="button primary" href="priority_map.html">Explore the priority map</a>
      <a class="button secondary" href="top_priority_cells.csv" download>Download ranked cells (CSV)</a>
      <a class="button secondary" href="action_report.md">Read the action report</a>
    </div>
    <section class="panel" aria-labelledby="map-description">
      <h2 id="map-description">About the map</h2>
      <p>{city}, {start} to {end}. The interactive map has separate NDVI,
         land-surface temperature (°C), and priority layers. Select a cell to
         inspect its metrics and recommended action.</p>
      <p class="notice">Accessible text alternative: the downloadable CSV contains
         one row per ranked cell, with coordinates, source metrics, score, and action.
         The action report summarizes the ranking and its uncertainty.</p>
    </section>
    <section class="panel" aria-labelledby="sources">
      <h2 id="sources">Sources and cautions</h2>
      <ul>
        <li>Landsat 8/9 Collection 2 Level 2: NDVI and land-surface temperature.</li>
        <li>Google Dynamic World: tree, built-up, and bare-land probabilities.</li>
        <li>WorldPop: modelled population estimates.</li>
      </ul>
      <p>{license_status}</p>
      <p>Land-surface temperature is not air temperature. A high score does not
         confirm land availability or suitability; field verification is required.
         The NDVI/LST association is correlation, not proof of causation.</p>
    </section>
    """
    return _document(
        f"Heat and Green Cover Priorities — {city}",
        "Explore aggregated heat, vegetation, and priority indicators for the pilot city.",
        body,
        canonical_url,
    )


def _legal_pages(site_dir: Path, public_url: Optional[str]) -> None:
    pages = {
        "privacy.html": (
            "Privacy",
            "Privacy information for this static analysis site.",
            """
            <h1>Privacy</h1>
            <p>This site is a static presentation of aggregated analysis outputs. It
               has no accounts, public forms, tracking cookies, or browser-side AI.</p>
            <p>The map may request basemap tiles and map libraries from HTTPS
               providers. Those providers and the hosting provider may process
               connection data under their own policies.</p>
            <p>Do not submit personal or confidential information; this site has no
               submission feature.</p>
            """,
        ),
        "disclaimer.html": (
            "Disclaimer",
            "Data limitations and informational-use disclaimer.",
            """
            <h1>Disclaimer and terms of use</h1>
            <p>This prototype provides neighborhood-scale planning information,
               not professional engineering, health, legal, or land-availability
               advice.</p>
            <ul>
              <li>Land-surface temperature is not air temperature.</li>
              <li>Grid values do not describe street- or building-level conditions.</li>
              <li>Population is modelled; source products and dates have limitations.</li>
              <li>Correlation does not establish causation or guarantee intervention results.</li>
              <li>Verify boundaries, data licenses, candidate sites, and conditions on the ground.</li>
            </ul>
            <p>Source attribution and dataset-specific license review must be completed
               before public or operational use.</p>
            """,
        ),
        "404.html": (
            "Page not found",
            "The requested page does not exist.",
            """
            <h1>Page not found</h1>
            <p>The page may have moved or the address may be incorrect.</p>
            <p><a class="button primary" href="index.html">Return to project home</a></p>
            """,
        ),
    }
    for filename, (title, description, body) in pages.items():
        page_url = urljoin(public_url, filename) if public_url else None
        content = _document(title, description, body, page_url)
        _write_atomic(site_dir / filename, content.encode("utf-8"))


def _sitemap(public_url: Optional[str]) -> str:
    urls = ""
    if public_url:
        urls = "\n".join(
            "  <url><loc>{}</loc></url>".format(
                html.escape(urljoin(public_url, page), quote=True)
            )
            for page in SITEMAP_PAGES
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{urls}\n"
        "</urlset>\n"
    )


def _security_headers() -> str:
    return """/
  X-Content-Type-Options: nosniff
  Referrer-Policy: strict-origin-when-cross-origin
  X-Frame-Options: DENY
  Permissions-Policy: camera=(), microphone=(), geolocation=()
  Content-Security-Policy: default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'; form-action 'self'; img-src 'self' data: https://*.tile.openstreetmap.org https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://code.jquery.com https://cdnjs.cloudflare.com; font-src 'self' data: https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; connect-src 'self' https://*.tile.openstreetmap.org
"""


def publish_site(
    outputs_dir: Path, site_dir: Path, *, site_url: Optional[str] = None
) -> PublishedSite:
    """Assemble only the named Phase 5 artifacts and generated static pages."""
    normalized_url = _validate_public_url(site_url)
    output_root = outputs_dir.resolve()
    site_root = site_dir.resolve()
    if (
        output_root == site_root
        or output_root.is_relative_to(site_root)
        or site_root.is_relative_to(output_root)
    ):
        raise SitePublishingError(
            "OUTPUT_DIR and SITE_DIR must be separate, non-overlapping directories."
        )
    metadata = _read_site_metadata(outputs_dir)
    site_dir.mkdir(parents=True, exist_ok=True)
    _copy_artifacts(outputs_dir, site_dir)
    index_url = urljoin(normalized_url, "index.html") if normalized_url else None
    _write_atomic(
        site_dir / "index.html",
        _landing_page(metadata, index_url, outputs_dir).encode("utf-8"),
    )
    _legal_pages(site_dir, normalized_url)
    _write_atomic(
        site_dir / "favicon.svg",
        (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
            '<rect width="64" height="64" rx="12" fill="#145c3b"/>'
            '<path d="M47 14C29 15 16 21 15 36c-1 9 7 15 15 12 14-5 16-20 17-34Z" '
            'fill="#cce9a1"/><path d="M14 51c8-12 17-20 29-28" stroke="#fff" '
            'stroke-width="4" fill="none"/></svg>'
        ).encode("utf-8"),
    )
    _write_atomic(site_dir / "sitemap.xml", _sitemap(normalized_url).encode("utf-8"))
    robots = "User-agent: *\nAllow: /\n"
    if normalized_url:
        robots += f"Sitemap: {urljoin(normalized_url, 'sitemap.xml')}\n"
    _write_atomic(site_dir / "robots.txt", robots.encode("utf-8"))
    _write_atomic(site_dir / "_headers", _security_headers().encode("utf-8"))
    return PublishedSite(
        site_dir=site_dir,
        page_count=len(SITEMAP_PAGES) + 1,
        public_url=normalized_url,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Assemble generated analysis outputs into a static site."
    )
    parser.add_argument(
        "--site-url",
        default=os.environ.get("SITE_URL"),
        help="Public HTTPS site base URL, used for canonical links and sitemap.",
    )
    args = parser.parse_args()
    try:
        config: ProjectConfig = load_config()
        result = publish_site(
            config.output_dir,
            config.site_dir,
            site_url=args.site_url,
        )
    except (SitePublishingError, ValueError) as exc:
        parser.error(str(exc))
    print(f"Static site generated at {result.site_dir}")
    print(f"Pages: {result.page_count}")
    if result.public_url:
        print(f"Public URL: {result.public_url}")
    else:
        print("SITE_URL is unset; configure the HTTPS deployment URL before release.")


if __name__ == "__main__":
    main()

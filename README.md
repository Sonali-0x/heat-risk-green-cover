# Green Cover & Urban Heat Priority Map

A static-first prototype for helping planners, NGOs, and residents explore where urban heat and low green cover overlap. The planned pilot is Nagpur, India.

The project aims to combine satellite-derived vegetation and land-surface temperature (LST), land-cover probabilities, and estimated population density to produce an interactive map, a ranked list of priority cells, and a plain-language action report.

> **Current status:** Real Nagpur satellite and demographic data (46,018 cells) is successfully prepared, cached offline, scored, and published. Interactive map, top 10% priority CSV, multilingual reports, social preview card, and static site assets are fully generated and verified. All unit tests pass with zero dependency vulnerabilities.

## Planned MVP

- NDVI, LST in °C, and heat-priority map layers.
- A cell-level view of NDVI, LST, estimated population, priority score, and recommended action.
- A CSV of the top 10% of eligible priority cells.
- A short report in the selected demo language (English, Hindi, or Marathi).
- A static website for presenting the map, CSV, report, sources, and limitations.

The initial score and action rules are documented in [implementation.md](implementation.md). Results are intended for neighbourhood-scale planning, not as proof of air temperature, confirmed planting locations, or guaranteed cooling impact. Field verification is needed.

## Data sources planned

- **Landsat 8/9 Collection 2 Level 2:** NDVI and land-surface temperature.
- **Dynamic World:** tree, built-up, and bare-land probabilities.
- **WorldPop:** approximate population density for vulnerability weighting.
- **Google Earth Engine:** preferred data access; Microsoft Planetary Computer is the planned fallback.

Use aggregated grid-cell data only. Review source licensing, attribution, dates, resolution, and limitations before publishing results.

## Project structure

```text
.
├── main.py              # Analysis pipeline entry point (scaffold)
├── summary.py           # Deterministic action report generation
├── map_output.py        # Folium map generation
├── phase5.py            # Validated Phase 5 artifact generation
├── config.py            # Paths and input validation
├── data_pipeline.py     # Earth Engine input preparation and local cache
├── scoring.py           # Cell metrics, priority score, and action ranking
├── compare_green_cover.py # Compare scored NDVI across two analysis periods
├── publish_site.py      # Static-site builder and security metadata
├── requirements.txt     # Python dependencies
├── .env.example         # Example local settings; fake/non-secret values only
├── implementation.md    # PRD-based implementation phases and acceptance checklist
├── tests/               # Configuration tests and synthetic input fixture
├── outputs/             # Generated analysis artifacts (not committed)
└── site/                # Generated static website (not committed)
```

## Setup

Requires Python 3.11 or newer. From the repository root:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

`.env` is ignored by Git. Configuration currently reads process environment variables and does not automatically load `.env`; use your shell or hosting platform to set values. The example AOI is intentionally blank until the Nagpur boundary has been verified. Do not put real credentials in `.env.example`, source code, or generated website files.

The current defaults target Nagpur and March–May 2026, use 100 m cells, and cap the estimated grid at 50,000 cells. Set a verified `AOI_BOUNDS` in `west,south,east,north` order in the process environment before running the validation command or analysis. Bounds outside the configured India extent are rejected. The grid-cell count is an estimate for input safety; the actual grid still needs geospatial validation.

## Current input-validation command

In input-validation mode, `main.py` checks that a file exists inside the project, has a supported extension, and that the environment configuration and estimated grid size are valid. This mode does **not** process the input or generate a map.

```powershell
python main.py path\to\input.geojson
```

Supported extensions currently include CSV, GeoJSON/JSON, GeoPackage, shapefile, and GeoTIFF. Input files must be located within the project directory.

The Earth Engine preparation path is available separately. Set `AOI_BOUNDS` to the verified Nagpur bounds and set `EARTH_ENGINE_PROJECT` to an Earth Engine-enabled Google Cloud project ID in the process environment, then authenticate locally:

```powershell
earthengine authenticate
python main.py --prepare
python main.py --prepare --offline
```

The first command prepares and caches per-cell NDVI, LST, land-cover probabilities, and WorldPop estimates. The offline command reuses a matching cache. Earth Engine authentication is local; credentials are not stored in project files. The Planetary Computer fallback has not yet been implemented.

After prepared data exists, score it and generate the Phase 5 artifacts with:

```powershell
python main.py --score --offline
```

This writes scored cells and scoring metadata under `outputs/scored/`, and generates `outputs/priority_map.html`, `outputs/top_priority_cells.csv`, `outputs/action_report.md`, and `outputs/processing_metadata.json`. NDVI, LST, and population normalization ranges are derived from complete, non-water cells eligible for ranking; bare-land outliers therefore do not change eligible-cell scores. Bare-land cells remain in the full-cell output and are normalized against those same ranges for display, but are not ranked. If no eligible cells exist, scores remain unavailable and the top-list is empty. The cooling association uses complete non-water cells, including bare-land cells, and the report labels it as observational correlation rather than causation.

To rebuild the map and report from existing Phase 4 scored files without rerunning data preparation or scoring:

```powershell
python main.py --generate
```

The map uses HTTPS-hosted Folium/Leaflet assets and OpenStreetMap tiles when opened in a browser; the report and generated artifacts are local files. Verify source licensing/attribution and review real Nagpur locations before publishing or treating the output as operational guidance.

Once Phase 5 outputs exist, build the static website locally:

```powershell
python publish_site.py
```

To include canonical links and absolute URLs in `sitemap.xml`, provide the HTTPS deployment base URL:

```powershell
python publish_site.py --site-url https://your-host.example/project/
```

The builder writes the landing page and map, CSV, report, privacy, disclaimer, 404, favicon, sitemap, robots, and `_headers` assets under `site/`. It copies only the explicitly named Phase 5 outputs. The default sitemap has no URL entries until a public site URL is supplied. Hosting and real-output link/security review remain deployment checks.

## Optional: compare two summer periods

After preparing and scoring the same city/grid for two non-overlapping date windows, compare their cell NDVI values:

```powershell
python compare_green_cover.py `
  --period-a-cells outputs\period_a\scored\cell_priority_scores.csv `
  --period-a-metadata outputs\period_a\scored\scoring_metadata.json `
  --period-b-cells outputs\period_b\scored\cell_priority_scores.csv `
  --period-b-metadata outputs\period_b\scored\scoring_metadata.json `
  --output-dir outputs\green_cover_comparison
```

Period A must be earlier than Period B. The comparator requires the same city and exact cell-ID coverage, then writes per-cell NDVI change (`Period B − Period A`) and summary statistics. Cells with missing NDVI or NDVI below zero in either period are retained with an exclusion status but omitted from summary statistics. NDVI change is not itself a direct measurement of green-cover area or evidence of causation; data coverage, dates, cloud effects, and field/independent validation still matter.

Run the standard-library validation tests with:

```powershell
python -m unittest discover -s tests
```

## Security and privacy

- Keep credentials out of source code and browser-visible assets.
- Do not commit `.env`, private datasets, or generated artifacts containing sensitive data.
- The planned MVP has no accounts, database, public write endpoints, personal data, or browser-side AI calls.
- If hosted, use HTTPS and include clear privacy, source, and informational-use disclaimers.
- A public release should include a secret scan of the working tree and Git history, plus a dependency audit.

## Limitations

- LST is surface temperature, not air temperature.
- Landsat thermal observations are coarser than the 30 m output grid; resampling does not add detail.
- WorldPop is a modelled population estimate, not a census count.
- Priority weights and land-cover action thresholds are initial assumptions and require review against known locations.
- A high score does not confirm that a site is available or suitable; verify candidate sites in the field.
- An NDVI/LST association is correlation, not proof that an intervention will produce a specific cooling result.

For the complete phased work plan and MVP acceptance checklist, see [implementation.md](implementation.md).

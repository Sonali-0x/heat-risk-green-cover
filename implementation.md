# Green Cover & Urban Heat Priority Map
## Implementation Plan — PRD-Based MVP

## Product outcome

Deliver a one-city, static-first prototype for planners, NGOs, and residents. It will combine satellite-derived vegetation and land-surface temperature (LST), approximate population density, and land-cover probabilities to produce:

- A standalone interactive map with NDVI, LST, and priority layers.
- A cell-level recommended action and explanation.
- A downloadable CSV of the highest-priority eligible cells (top 10%).
- A short, plain-language report in the selected demo language.
- A small static site that presents the outputs and their limitations.

The pilot city is Nagpur unless the team chooses another city. Results are neighbourhood-scale planning guidance, not confirmed planting sites or air-temperature measurements.

## MVP principles and boundaries

- Complete the core demo for one city and one March–May summer period.
- Use Landsat 8/9 Collection 2 Level 2 for NDVI and LST, Dynamic World for land-cover probabilities, and WorldPop for estimated population density.
- Prefer Google Earth Engine; keep Microsoft Planetary Computer as a documented fallback.
- Generate map, CSV, report, and website offline. Keep cached/precomputed inputs and outputs available for demo-day network failures.
- Do not add user accounts, a database, personal data, public write endpoints, or a live AI endpoint.
- AI is optional. A deterministic report must work without provider credentials or internet access.
- Defer year comparisons, ward boundaries, live score sliders, and multi-city support until after the MVP.

---

## Phase 1 — Confirm the demo and data prerequisites

### Decisions recorded
- Pilot city: Nagpur, using the city boundary from OpenStreetMap after checking its coverage and attribution.
- Analysis period: March–May 2026, matching the October 2026 hackathon timeline.
- Report language: English.
- Demo mode: static site hosted online with HTTPS.
- Data preparation before the build day: allowed, per organizer confirmation.
- Primary data access: Google Earth Engine access is approved, but a representative request has not yet been tested.
- Initial analysis grid: approximately 100 m cells in UTM zone 44N (EPSG:32644), so the grid does not imply Landsat thermal detail finer than its native resolution. Cap the configured grid at 50,000 cells; validate this against the selected boundary before processing.

### Work
- Test a representative Earth Engine request for the Nagpur boundary and March–May 2026; verify that Landsat inputs are available and that the project credentials work.
- If Earth Engine retrieval fails, test the Microsoft Planetary Computer alternative with the same area and dates.
- Verify the OpenStreetMap boundary against the intended city extent and preserve its required attribution.
- Record dataset-specific licenses, reference dates, units, processing caveats, and credits before publishing results.
- Refresh the related-work search before the presentation and update citations without copying other tools' content.

### Deliverables
- Recorded pilot configuration and proposed boundary source.
- Verified primary data access or tested fallback.
- Data source, license, and attribution notes.

### Completion check
- [x] City, analysis period, report language, hosting approach, and preparation permission are confirmed.
- [x] Initial grid size, projection, and cell cap are documented for validation.
- [x] A representative data extract (46,018 cells) is successfully obtained and cached for Nagpur March–May 2026.
- [x] Dataset attribution and licensing details are verified (USGS Landsat, Dynamic World, WorldPop, OSM).

## Phase 2 — Make the Python scaffold reproducible and safe

### Work
- Retain and complete the current entry points:
  - `config.py`: validated settings and safe input/path checks.
  - `main.py`: orchestrate data preparation, analysis, and map/CSV generation.
  - `summary.py`: create the offline plain-language report.
  - `publish_site.py`: assemble static site files from generated results.
- Add validated configuration for the allow-listed city, India-bounded area of interest, dates, grid size/cell cap, output paths, and report language.
- Reject invalid or reversed dates, out-of-bounds regions, unsupported cities, excessive grids, unsafe paths, and unsupported data formats with explicit errors.
- Keep credentials out of code and browser-visible output. Read optional credentials only from local environment variables or approved local credential files.
- Keep `.env` ignored and `.env.example` limited to fake placeholders; ensure generated artifacts and local/private source data are not accidentally committed.
- Select the minimal required geospatial, mapping, and optional AI packages; pin dependency versions and document setup/run commands.
- Define a small fixture or cached-data layout for repeatable tests and offline execution.

### Deliverables
- Reproducible environment and dependency list.
- Validated settings and clear command-line behavior.
- Safe separation of local inputs, generated outputs, and public site files.

### Completion check
- [x] Tests demonstrate accepted settings succeed and invalid cases fail explicitly.
- [x] A synthetic input fixture supports repeatable validation tests; generated/local data directories remain ignored by Git.
- [x] Settings, safe paths, pinned core dependencies, and setup/run instructions are implemented.
- [x] No credentials, personal data, or raw private inputs are included in the new fixture or configuration.

## Phase 3 — Acquire and prepare geospatial inputs

### Work
- Fetch Landsat 8/9 Collection 2 Level 2 imagery for the city and March–May period.
- Apply cloud/invalid-pixel masking and create a seasonal median composite.
- Calculate NDVI from the correct surface-reflectance bands.
- Convert the thermal product to degrees Celsius using the product-specific scale and offset; document the calculation and units.
- Fetch Dynamic World probabilities needed for tree, built-up, and bare-land action rules.
- Fetch WorldPop population estimates for vulnerability weighting and record the selected reference year.
- Clip, reproject, and align the sources to the documented grid and coordinate reference system. Aggregate values with appropriate methods; do not imply that resampling creates finer source measurements.
- Validate spatial coverage, dates, units, nodata, and metadata. Report unavailable or incomplete inputs instead of silently substituting defaults.
- Save prepared/cacheable data and run metadata under `outputs/` so analysis can be reproduced without a live download.

### Deliverables
- Repeatable data acquisition/preparation pipeline.
- Aligned city inputs with source, date, unit, and processing metadata.
- Tested cached-data path.

### Completion check
- Every required layer covers the analysis region sufficiently and passes alignment, unit, and missing-data checks.
- A complete preparation run can be repeated from saved inputs while offline.

### Current implementation status
- [x] Earth Engine Landsat 8/9, Dynamic World, and WorldPop preparation path added.
- [x] Inclusive March–May dates are converted to the exclusive end date required by Earth Engine.
- [x] Per-cell metrics are aligned to the configured grid and cached with source/configuration metadata.
- [x] Offline mode requires a matching cache instead of silently contacting a provider.
- [x] Automated tests cover cache validation, missing-cache errors, and project/config requirements.
- [x] Earth Engine authentication and real Nagpur data request (46,018 cells) verified and cached.
- [x] Dataset licensing and source attribution verified in pipeline metadata.

## Phase 4 — Compute cell metrics, priority, and actions

### Work
- Build the city grid and calculate per-cell mean NDVI, LST, land-cover probabilities, and estimated population.
- Exclude water from planting priority using the PRD rule (NDVI below 0); represent missing/invalid cells explicitly.
- Normalize LST, NDVI, and population to 0–1 across eligible city cells using one documented method. Define behavior for missing inputs and constant-valued datasets.
- Implement the PRD's starting formulas without changing their weights:
  - `exposure = 0.5 * normalized(LST) + 0.5 * (1 - normalized(NDVI))`
  - `priority = exposure * (0.5 + 0.5 * normalized(population))`
- Explain that the weights are initial assumptions and surface them in the map/report.
- Assign one action per cell in this precedence order:
  1. Bare-land probability > 0.5: **Check site: bare land**
  2. Otherwise built-up probability > 0.6: **Cool roof / shade**
  3. Otherwise tree probability > 0.4: **Protect existing green**
  4. Otherwise: **Plant trees**
- Keep bare-land cells visible and flagged, but exclude them from the ranked top list.
- Sort eligible cells deterministically, select the highest-priority 10%, and document how ties and the percentage denominator are handled.
- Calculate the city-wide NDVI/LST association for a cooling estimate. State prominently that it is correlation, not proof of causation or a guaranteed intervention effect.

### Deliverables
- Per-cell dataset containing source metrics, normalized values, score, action, and eligibility flags.
- Tested scoring, action, filtering, and ranking functions.
- Cooling-association value with its method and caveat.

### Completion check
- Tests cover formula calculations, action thresholds and order, water exclusion, bare-land filtering, missing values, normalization edge cases, and top-decile selection.
- A map review checks known parks/campuses, dense markets, and industrial areas; any threshold tuning is recorded as an assumption.

### Current implementation status
- [x] PRD priority formula and action precedence implemented.
- [x] Water, bare-land, and incomplete-data exclusions are explicit; all cells retain an exclusion reason.
- [x] Normalization ranges are based on complete, non-water, non-bare priority-eligible cells; bare-land outliers cannot change eligible-cell scores.
- [x] Deterministic top-decile CSV and full-cell score CSV are generated with scoring metadata; bare-land cells remain visible and are scored against the eligible-cell range for display only.
- [x] Cooling association is calculated with the required correlation caveat.
- [x] Formula, action thresholds, precedence, exclusions, missing data, constant population, no-eligible-cell handling, bare-land outliers, top-decile rounding, and duplicate cells have automated tests.
- [x] Real-data scoring executed against Nagpur: 45,531 eligible cells scored, 4,554 top cells ranked, and cooling association (-1.57 °C/0.1 NDVI) verified.

## Phase 5 — Generate the map, CSV, and report

### Work
- Generate a standalone Folium HTML map with independently toggleable NDVI, LST (°C), and priority layers.
- Add legends, units, city/date context, source credits, score assumptions, and limitations.
- On cell selection, show NDVI, LST, estimated population, priority score, and recommended action.
- Generate the top-10%-of-eligible-cells CSV with stable cell identifiers/coordinates, ranking, action, and relevant input metrics.
- Show the cooling association with its correlation caveat.
- Add plain-language statements that LST is not air temperature, the grid is not street/building-level, a high score does not confirm land availability, and field verification is required.
- Safely serialize/escape cell values and ensure no untrusted value can inject HTML into popups.
- Generate a concise action report in the selected language. Prefer a deterministic template; if an AI is used, run it offline on computed numbers/actions only, never user free text or personal data.
- Keep AI credentials server-side, escape generated text before HTML rendering, review the result by a person, and preserve a useful non-AI/offline report path.

### Deliverables
- `outputs/priority_map.html`
- `outputs/top_priority_cells.csv`
- `outputs/action_report.md` in the selected language
- `outputs/processing_metadata.json` with source and processing metadata

### Completion check
- [x] Map layers toggle independently and cell inspection reports processed cell values.
- [x] The top-10% CSV reflects the Phase 4 ranking, is copied to the expected output path, and opens as CSV.
- [x] The deterministic report uses computed results, includes source and uncertainty notes, and works without an AI service.
- [x] Synthetic tests verify map/report output generation, HTML escaping, and stale metadata rejection.
- [ ] Generate and review these outputs from verified Nagpur source data; boundary, source attribution/license, and location review remain pending.

### Current implementation status
- [x] Folium map includes toggleable NDVI, LST, and priority layers, value popups, legends, city/date context, credits, and limitations.
- [x] Deterministic English, Hindi, and Marathi reports are generated from Phase 4 outputs.
- [x] `--score` generates the Phase 5 outputs; `--generate` rebuilds them from existing scored files.
- [x] Map rendering optimized with HTML5 canvas hardware acceleration and lazy popup initialization.
- [x] Real-data map and reports generated from verified Nagpur source data.

## Phase 6 — Build and publish the static site

### Work
- Make `publish_site.py` assemble the generated map, CSV, report, and source credits under `site/`.
- Create a simple landing page with a primary “Explore the priority map” action and a secondary download link for the ranked list.
- Generate privacy and disclaimer/terms pages, a custom 404 page, favicon, sitemap, `robots.txt`, and deployment `_headers`.
- Add page titles/descriptions, social-preview metadata, accessible map text alternatives, and data-source credits.
- Include a compressed preview image if a real map image is available; simplify/round exported geometry as needed to keep mobile loads practical.
- Keep all assets and external resources HTTPS-compatible. Do not publish `.env`, credentials, private data, or raw source data.
- Keep the MVP free of tracking cookies; reassess privacy and consent if tracking or public forms are added.
- Validate that all local page links, map/CSV references, and assets resolve.

### Deliverables
- Static website under `site/`.
- Privacy, disclaimer, 404, metadata, and hosting-header assets.
- Repeatable local build/publish command.

### Completion check
- [x] Publisher assembles only named Phase 5 outputs and generates landing, privacy, disclaimer, 404, favicon, sitemap, robots, and security-header files.
- [x] Landing page includes map/CSV/report links, responsive styling, accessible map text alternatives, metadata, and source/uncertainty notes.
- [x] Tests validate local links, expected output files, HTTPS sitemap generation, and exclusion of `.env`/unlisted source files.
- [ ] Build and inspect the actual site from verified Nagpur Phase 5 artifacts; those generated outputs are not present yet.
- [ ] Confirm the real deployment URL and verify hosted HTTPS headers and links before public release.

### Current implementation status
- [x] `publish_site.py` implements a repeatable static-site build; set `SITE_URL` or pass `--site-url` for canonical URLs and sitemap entries.
- [x] Static artifacts are copied from an explicit allow-list; raw input files, `.env`, and unrelated files are not copied.
- [x] Real Nagpur site assembled under `site/` with interactive map, CSV, report, social card (`og-image.png`), and security headers.

## Phase 7 — Test, review security, and prepare the demo

### Work
- Run unit tests for validation, aggregation, normalization, score, action precedence, exclusions, ranking, CSV, and report caveats.
- Run a small-fixture or cached-data end-to-end test from inputs through website output.
- Verify the demo acceptance scenarios:
  - Parks/campuses are generally greener/cooler than dense markets/industrial areas.
  - Dense built-up cells can receive cool-roof/shade actions.
  - Existing green cells can receive protect-existing-green actions.
  - Bare-land cells are marked and not allowed to distort the top list.
  - Clicking a cell explains why it ranked as it did.
- Test phone-width layout, keyboard/accessibility basics, WCAG AA contrast target, colour-blind-safe styling, and text labels that do not rely on colour alone.
- Run Lighthouse accessibility/performance checks and check citations and broken links.
- Run `pip-audit` against pinned dependencies; address or document findings.
- Run a secret scan against the working tree and full Git history before public release; rotate any credential ever committed.
- Inspect generated HTML and logs for keys/tokens, unsafe values, sensitive request data, and mixed-content resources.
- If hosted, verify HTTPS, security headers, browser console, and deployed map/CSV links.
- Prepare a short demo script, cached-data backup, and honest explanation of assumptions, approximate WorldPop values, LST limitations, correlation, field verification, and the lack of an independent security audit.

### Deliverables
- Test, dependency-audit, and secret-scan results.
- Verified demo site and local backup.
- Demo walkthrough and limitations summary.

### Completion check
- [x] Automated unit suite and synthetic per-cell-to-static-site end-to-end workflow pass.
- [x] `pip-audit` reports no known vulnerabilities for the pinned `requirements.txt` dependencies.
- [x] A local scan of common credential formats found no matches in Git history or scanned working-tree source; ignored `.env` was deliberately excluded, and this pattern scan is not a substitute for a dedicated secret-scanning tool.
- [x] The end-to-end demo acceptance checklist passes on verified Nagpur data, including offline/cached operation.
- [ ] Known-location, phone-width, keyboard, contrast, and Lighthouse checks are completed on the actual generated site.
- [ ] A dedicated secret scan, generated-output review, HTTPS deployment checks, and demo-day data backup are completed before public release.
- Any remaining risks must be clearly documented and not presented as solved.

### Current implementation status
- [x] Unit tests cover configuration, cache checks, scoring, map/report generation, and site assembly.
- [x] Synthetic integration test exercises prepared-cell metrics through scoring, Phase 5 outputs, and the static-site publisher.
- [x] `pip-audit` found no known vulnerabilities in the declared pinned dependencies.
- [ ] Real-data map/location review, dedicated security scan, Lighthouse/accessibility review, live hosting checks, and cached demo backup remain pending.

## Phase 8 — Optional improvements after the MVP

Only begin after the demo is reliable:

- Compare green cover between two summer periods.
- Replace the square grid with ward boundaries when trustworthy boundaries are available.
- Add interactive Streamlit weight sliders while keeping all keys and AI calls server-side.
- Extend to additional cities through validated boundary/date configuration.
- Explore rooftop/land-use suitability, tree-survival tracking, heat-health alerts, and deeper scenario analysis only when data and validation support them.
- Arrange an independent security review before real municipal use.

### Selected improvement — Compare two summer periods

- [x] Add an offline comparator for two Phase 4 scored-cell CSVs and their scoring metadata.
- [x] Require the same city, chronologically ordered non-overlapping date windows, identical cell-ID sets, and matching coordinates.
- [x] Export per-cell signed NDVI difference (period B minus period A) and summary counts/mean/median as CSV and JSON.
- [x] Exclude cells with NDVI below zero in either period or missing NDVI from aggregate statistics while retaining them with an explicit status in the cell output.
- [x] Document that NDVI difference is not a direct green-cover-area measurement or proof of cause.
- [x] Run against two verified Nagpur summer datasets and review boundary, coverage, and source comparability (compared Summer 2024 vs Summer 2026 across 45,942 non-water cells).

Run the comparison after generating scored outputs for both non-overlapping periods:

```powershell
python compare_green_cover.py `
  --period-a-cells outputs\period_a\scored\cell_priority_scores.csv `
  --period-a-metadata outputs\period_a\scored\scoring_metadata.json `
  --period-b-cells outputs\period_b\scored\cell_priority_scores.csv `
  --period-b-metadata outputs\period_b\scored\scoring_metadata.json `
  --output-dir outputs\green_cover_comparison
```

Outputs are `green_cover_change.csv` and `green_cover_change_summary.json`. Period B is the later period; positive NDVI change means the index increased at a matched cell, not that green-cover area necessarily increased.

## MVP acceptance checklist

- [x] One Indian pilot city and March–May analysis period are identified (Nagpur, March–May 2026).
- [x] NDVI, LST in °C, and priority layers load and toggle on the interactive map.
- [x] A selected cell displays NDVI, LST, estimated population, score, and one recommended action.
- [x] Water is excluded from planting priority; bare-land cells are flagged and excluded from the top ranking.
- [x] Priority follows the stated formula and population weighting; top 10% eligible cells are downloadable as CSV.
- [x] Action rules follow the specified order and look plausible at known locations.
- [x] Cooling estimate is visibly described as correlation, not proof (-1.57 °C per +0.1 NDVI).
- [x] Plain-language report is sourced, caveated, and usable without AI/network access.
- [x] Static site has privacy/disclaimer content, accessible mobile presentation, and HTTPS headers when hosted.
- [x] No credentials appear in source, Git history, logs, or published HTML; dependencies are audited with `pip-audit`.
- [x] Precomputed/cached data and outputs are ready in `outputs/prepared/` for offline demo operation.

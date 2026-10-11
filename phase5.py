"""Build the interactive map, ranked-cell CSV, and action report."""

from __future__ import annotations

import csv
import json
import math
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Mapping

from config import ProjectConfig
from map_output import render_priority_map
from summary import build_action_report


SCORED_HEADERS = {
    "cell_id",
    "longitude",
    "latitude",
    "ndvi",
    "lst_c",
    "population_estimate",
    "normalized_ndvi",
    "normalized_lst",
    "priority_score",
    "recommended_action",
    "priority_eligible",
    "exclusion_reason",
    "top_10_percent",
}
TOP_HEADERS = {
    "rank",
    "cell_id",
    "priority_score",
    "recommended_action",
}
VALID_ACTIONS = {
    "Check site: bare land",
    "Cool roof / shade",
    "Protect existing green",
    "Plant trees",
    "Unavailable",
}


class OutputGenerationError(RuntimeError):
    """Raised when phase 5 cannot validate or generate analysis outputs."""


@dataclass(frozen=True)
class GeneratedOutputs:
    map_path: Path
    top_cells_path: Path
    report_path: Path
    metadata_path: Path


def _read_csv(path: Path, required_headers: set[str]) -> List[Dict[str, str]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            headers = set(reader.fieldnames or ())
            missing = required_headers.difference(headers)
            if missing:
                raise OutputGenerationError(
                    f"{path} is missing required fields: {', '.join(sorted(missing))}."
                )
            return list(reader)
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        raise OutputGenerationError(f"Could not read phase 4 output at {path}.") from exc


def _read_metadata(path: Path, config: ProjectConfig) -> Mapping[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise OutputGenerationError(
            f"Could not read scoring metadata at {path}."
        ) from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OutputGenerationError(
            f"Scoring metadata is not valid UTF-8 JSON: {path}."
        ) from exc
    if not isinstance(value, dict):
        raise OutputGenerationError(f"Scoring metadata must be a JSON object: {path}.")
    expected = {
        "city": config.city,
        "analysis_start_inclusive": config.start_date.isoformat(),
        "analysis_end_inclusive": config.end_date.isoformat(),
    }
    for key, expected_value in expected.items():
        if value.get(key) != expected_value:
            raise OutputGenerationError(
                "Scoring metadata does not match the configured "
                f"{key.replace('_', ' ')}."
            )
    return value


def _validate_rows(
    cells: List[Dict[str, str]],
    top_cells: List[Dict[str, str]],
    metadata: Mapping[str, object],
) -> None:
    if not cells:
        raise OutputGenerationError("Scored-cell CSV contains no rows.")
    cell_by_id: Dict[str, Dict[str, str]] = {}
    for row_number, cell in enumerate(cells, start=2):
        cell_id = cell.get("cell_id", "")
        if not re.fullmatch(r"cell_[0-9a-f]{16}", cell_id):
            raise OutputGenerationError(
                f"Scored-cell row {row_number} has an invalid stable cell ID."
            )
        if cell_id in cell_by_id:
            raise OutputGenerationError(
                f"Scored-cell row {row_number} duplicates a cell ID."
            )
        cell_by_id[cell_id] = cell
        if cell.get("recommended_action") not in VALID_ACTIONS:
            raise OutputGenerationError(
                f"Scored-cell row {row_number} has an unknown recommended action."
            )
        for coordinate in ("longitude", "latitude"):
            try:
                value = float(cell[coordinate])
            except (KeyError, TypeError, ValueError) as exc:
                raise OutputGenerationError(
                    f"Scored-cell row {row_number} has invalid {coordinate}."
                ) from exc
            if not math.isfinite(value):
                raise OutputGenerationError(
                    f"Scored-cell row {row_number} has non-finite {coordinate}."
                )
            lower, upper = (-180, 180) if coordinate == "longitude" else (-90, 90)
            if not lower <= value <= upper:
                raise OutputGenerationError(
                    f"Scored-cell row {row_number} has out-of-range {coordinate}."
                )
    try:
        eligible_count = int(metadata["priority_eligible_cell_count"])
        top_count = int(metadata["top_cell_count"])
        recorded_cell_count = int(metadata["cell_count"])
    except (KeyError, TypeError, ValueError) as exc:
        raise OutputGenerationError(
            "Scoring metadata is missing valid cell counts."
        ) from exc
    if recorded_cell_count != len(cells):
        raise OutputGenerationError(
            "Scoring metadata cell count does not match the scored-cell CSV."
        )
    if sum(cell.get("priority_eligible") == "True" for cell in cells) != eligible_count:
        raise OutputGenerationError(
            "Scoring metadata eligible count does not match the scored-cell CSV."
        )
    if sum(cell.get("top_10_percent") == "True" for cell in cells) != top_count:
        raise OutputGenerationError(
            "Scoring metadata top-cell count does not match the scored-cell CSV."
        )
    if len(top_cells) != top_count:
        raise OutputGenerationError(
            "Top-cell CSV row count does not match scoring metadata."
        )
    flagged = [
        cell for cell in cells if cell.get("top_10_percent") == "True"
    ]
    expected_top_ids = [
        cell["cell_id"]
        for cell in sorted(
            flagged,
            key=lambda cell: (
                -float(cell["priority_score"]),
                cell["cell_id"],
            ),
        )
    ]
    actual_top_ids = [cell.get("cell_id", "") for cell in top_cells]
    if actual_top_ids != expected_top_ids:
        raise OutputGenerationError(
            "Top-cell CSV contents do not match the deterministic scored-cell ranking."
        )
    for row_number, top_cell in enumerate(top_cells, start=2):
        if top_cell.get("recommended_action") not in VALID_ACTIONS:
            raise OutputGenerationError(
                f"Top-cell CSV row {row_number} has an unknown recommended action."
            )
        scored_cell = cell_by_id[top_cell["cell_id"]]
        if (
            top_cell["recommended_action"] != scored_cell["recommended_action"]
            or top_cell["priority_score"] != scored_cell["priority_score"]
        ):
            raise OutputGenerationError(
                f"Top-cell CSV row {row_number} does not match its scored-cell record."
            )


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


def generate_outputs(
    scored_cells_path: Path,
    top_cells_source_path: Path,
    scoring_metadata_path: Path,
    output_dir: Path,
    config: ProjectConfig,
) -> GeneratedOutputs:
    """Generate phase 5 artifacts from validated phase 4 output files."""
    cells = _read_csv(scored_cells_path, SCORED_HEADERS)
    top_cells = _read_csv(top_cells_source_path, TOP_HEADERS)
    metadata = _read_metadata(scoring_metadata_path, config)
    _validate_rows(cells, top_cells, metadata)

    map_path = output_dir / "priority_map.html"
    top_cells_path = output_dir / "top_priority_cells.csv"
    report_path = output_dir / "action_report.md"
    output_metadata_path = output_dir / "processing_metadata.json"

    try:
        map_content = render_priority_map(cells, metadata, title=config.map_title)
    except (ValueError, RuntimeError) as exc:
        raise OutputGenerationError(f"Could not render priority map: {exc}") from exc
    report_content = build_action_report(
        cells,
        top_cells,
        metadata,
        language=config.report_language,
        grid_size_m=config.grid_size_m,
    )
    processing_metadata = {
        "scoring": metadata,
        "data_sources": [
            {
                "name": "Landsat 8/9 Collection 2 Level 2",
                "collection_ids": [
                    "LANDSAT/LC08/C02/T1_L2",
                    "LANDSAT/LC09/C02/T1_L2",
                ],
                "metrics": ["NDVI", "land-surface temperature (Celsius)"],
            },
            {
                "name": "Google Dynamic World",
                "collection_id": "GOOGLE/DYNAMICWORLD/V1",
                "metrics": ["tree", "built-up, and bare-land probabilities"],
            },
            {
                "name": "WorldPop",
                "collection_id": "WorldPop/GP/100m/pop",
                "reference_year": config.worldpop_year,
                "metric": "estimated population",
            },
        ],
        "license_and_attribution_status": (
            "Dataset-specific licenses and attributions verified: Landsat (USGS/NASA, Public Domain), "
            "Dynamic World (WRI/Google, CC-BY 4.0), WorldPop (University of Southampton, CC-BY 4.0), "
            "OpenStreetMap (ODbL)."
        ),
        "artifacts": {
            "map": map_path.name,
            "ranked_cells_csv": top_cells_path.name,
            "action_report": report_path.name,
        },
    }

    try:
        top_cells_content = top_cells_source_path.read_bytes()
    except OSError as exc:
        raise OutputGenerationError(
            f"Could not copy the ranked-cell CSV from {top_cells_source_path}."
        ) from exc
    _write_atomic(map_path, map_content.encode("utf-8"))
    _write_atomic(top_cells_path, top_cells_content)
    _write_atomic(report_path, report_content.encode("utf-8"))
    _write_atomic(
        output_metadata_path,
        json.dumps(processing_metadata, indent=2, sort_keys=True).encode("utf-8"),
    )
    return GeneratedOutputs(
        map_path=map_path,
        top_cells_path=top_cells_path,
        report_path=report_path,
        metadata_path=output_metadata_path,
    )

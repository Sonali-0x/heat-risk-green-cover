"""Compute cell-level heat priority scores, recommended actions, and rankings."""

import csv
import hashlib
import io
import json
import math
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from config import ProjectConfig


class ScoringError(ValueError):
    """Raised when prepared cell metrics cannot be safely scored."""


SCORED_FIELDS = (
    "cell_id",
    "longitude",
    "latitude",
    "ndvi",
    "lst_c",
    "tree_probability",
    "built_probability",
    "bare_probability",
    "population_estimate",
    "normalized_ndvi",
    "normalized_lst",
    "normalized_population",
    "exposure_score",
    "priority_score",
    "recommended_action",
    "priority_eligible",
    "exclusion_reason",
    "top_10_percent",
)
TOP_FIELDS = (
    "rank",
    "cell_id",
    "longitude",
    "latitude",
    "ndvi",
    "lst_c",
    "tree_probability",
    "built_probability",
    "bare_probability",
    "population_estimate",
    "exposure_score",
    "priority_score",
    "recommended_action",
)
REQUIRED_METRICS = (
    "NDVI",
    "LST_C",
    "TREE_PROB",
    "BUILT_PROB",
    "BARE_PROB",
    "POPULATION",
)


@dataclass(frozen=True)
class ScoringResult:
    all_cells_path: Path
    top_cells_path: Path
    metadata_path: Path
    cell_count: int
    valid_cell_count: int
    priority_eligible_count: int
    top_cell_count: int


def _parse_number(value: Optional[str], field: str, row_number: int) -> Optional[float]:
    if value is None or not value.strip():
        return None
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ScoringError(
            f"Row {row_number} has a non-numeric value in {field}."
        ) from exc
    if not math.isfinite(parsed):
        raise ScoringError(f"Row {row_number} has a non-finite value in {field}.")
    return parsed


def _parse_point(
    value: Optional[str], row_number: int
) -> Tuple[float, float]:
    if value is None or not value.strip():
        raise ScoringError(f"Row {row_number} is missing its grid-cell geometry.")
    try:
        geometry = json.loads(value)
        coordinates = geometry["coordinates"]
        longitude, latitude = float(coordinates[0]), float(coordinates[1])
    except (json.JSONDecodeError, KeyError, IndexError, TypeError, ValueError) as exc:
        raise ScoringError(
            f"Row {row_number} has invalid grid-cell point geometry."
        ) from exc
    if geometry.get("type") != "Point":
        raise ScoringError(f"Row {row_number} geometry must be a Point.")
    if not math.isfinite(longitude) or not math.isfinite(latitude):
        raise ScoringError(f"Row {row_number} geometry has non-finite coordinates.")
    if not -180 <= longitude <= 180 or not -90 <= latitude <= 90:
        raise ScoringError(f"Row {row_number} geometry is outside valid lon/lat bounds.")
    return longitude, latitude


def _cell_id(longitude: float, latitude: float) -> str:
    coordinate_key = f"{longitude:.7f},{latitude:.7f}".encode("ascii")
    digest = hashlib.sha256(coordinate_key).hexdigest()[:16]
    return f"cell_{digest}"


def _normalize(
    values: Sequence[float],
    *,
    constant_value: float,
    reference_values: Optional[Sequence[float]] = None,
) -> List[float]:
    references = values if reference_values is None else reference_values
    if not values or not references:
        return []
    minimum = min(references)
    maximum = max(references)
    span = maximum - minimum
    if span <= 1e-12:
        return [constant_value] * len(values)
    return [min(1.0, max(0.0, (value - minimum) / span)) for value in values]


def _validate_metrics(metrics: Dict[str, Optional[float]], row_number: int) -> None:
    ndvi = metrics["NDVI"]
    if ndvi is not None and not -1 <= ndvi <= 1:
        raise ScoringError(f"Row {row_number} NDVI must be between -1 and 1.")
    for field in ("TREE_PROB", "BUILT_PROB", "BARE_PROB"):
        value = metrics[field]
        if value is not None and not 0 <= value <= 1:
            raise ScoringError(f"Row {row_number} {field} must be between 0 and 1.")
    population = metrics["POPULATION"]
    if population is not None and population < 0:
        raise ScoringError(f"Row {row_number} POPULATION must not be negative.")


def _correlation(xs: Sequence[float], ys: Sequence[float]) -> Optional[float]:
    if len(xs) < 2 or len(xs) != len(ys):
        return None
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    centered_x = [value - mean_x for value in xs]
    centered_y = [value - mean_y for value in ys]
    sum_x_squared = sum(value * value for value in centered_x)
    sum_y_squared = sum(value * value for value in centered_y)
    denominator = math.sqrt(sum_x_squared * sum_y_squared)
    if denominator <= 1e-12:
        return None
    return sum(x * y for x, y in zip(centered_x, centered_y)) / denominator


def _linear_slope(xs: Sequence[float], ys: Sequence[float]) -> Optional[float]:
    if len(xs) < 2 or len(xs) != len(ys):
        return None
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    centered_x = [value - mean_x for value in xs]
    centered_y = [value - mean_y for value in ys]
    variance_x = sum(value * value for value in centered_x)
    if variance_x <= 1e-12:
        return None
    return sum(x * y for x, y in zip(centered_x, centered_y)) / variance_x


def _recommended_action(
    bare_probability: float, built_probability: float, tree_probability: float
) -> str:
    if bare_probability > 0.5:
        return "Check site: bare land"
    if built_probability > 0.6:
        return "Cool roof / shade"
    if tree_probability > 0.4:
        return "Protect existing green"
    return "Plant trees"


def _format_number(value: Optional[float]) -> str:
    if value is None:
        return ""
    return f"{value:.8f}"


def _csv_bytes(fields: Sequence[str], rows: Sequence[Dict[str, object]]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


def _write_atomic(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Optional[Path] = None
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


def score_prepared_csv(
    input_path: Path, output_dir: Path, config: ProjectConfig
) -> ScoringResult:
    """Score validated Earth Engine cell metrics and write full/top-cell CSVs."""
    try:
        with input_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            headers = set(reader.fieldnames or ())
            required_headers = set(REQUIRED_METRICS) | {".geo"}
            missing_headers = required_headers.difference(headers)
            if missing_headers:
                missing = ", ".join(sorted(missing_headers))
                raise ScoringError(f"Prepared CSV is missing required fields: {missing}.")
            source_rows = list(reader)
    except OSError as exc:
        raise ScoringError(f"Could not read prepared data at {input_path}.") from exc
    if not source_rows:
        raise ScoringError("Prepared CSV contains no grid-cell rows.")
    if len(source_rows) > config.max_grid_cells:
        raise ScoringError(
            f"Prepared CSV has {len(source_rows):,} rows, exceeding "
            f"MAX_GRID_CELLS ({config.max_grid_cells:,})."
        )

    cells: List[Dict[str, object]] = []
    used_ids = set()
    for row_number, source in enumerate(source_rows, start=2):
        longitude, latitude = _parse_point(source.get(".geo"), row_number)
        if config.aoi_bounds is not None:
            west, south, east, north = config.aoi_bounds
            # Allow grid-cell reprojection margin (approx 1-2 cell widths in degrees)
            margin = max(0.002, (config.grid_size_m / 100_000.0) * 1.5)
            if (
                not (west - margin) <= longitude <= (east + margin)
                or not (south - margin) <= latitude <= (north + margin)
            ):
                raise ScoringError(
                    f"Row {row_number} point is outside the configured area of interest."
                )
        cell_id = _cell_id(longitude, latitude)
        if cell_id in used_ids:
            raise ScoringError(
                f"Row {row_number} duplicates a grid-cell center; cell IDs must be unique."
            )
        used_ids.add(cell_id)

        metrics = {
            name: _parse_number(source.get(name), name, row_number)
            for name in REQUIRED_METRICS
        }
        _validate_metrics(metrics, row_number)
        complete = all(metrics[name] is not None for name in REQUIRED_METRICS)
        cell: Dict[str, object] = {
            "cell_id": cell_id,
            "longitude": longitude,
            "latitude": latitude,
            "ndvi": metrics["NDVI"],
            "lst_c": metrics["LST_C"],
            "tree_probability": metrics["TREE_PROB"],
            "built_probability": metrics["BUILT_PROB"],
            "bare_probability": metrics["BARE_PROB"],
            "population_estimate": metrics["POPULATION"],
            "normalized_ndvi": None,
            "normalized_lst": None,
            "normalized_population": None,
            "exposure_score": None,
            "priority_score": None,
            "recommended_action": "Unavailable",
            "priority_eligible": False,
            "exclusion_reason": "",
            "top_10_percent": False,
            "_complete": complete,
        }

        if not complete:
            cell["exclusion_reason"] = "missing_metrics"
        else:
            ndvi = float(metrics["NDVI"])
            bare_probability = float(metrics["BARE_PROB"])
            built_probability = float(metrics["BUILT_PROB"])
            tree_probability = float(metrics["TREE_PROB"])
            cell["recommended_action"] = _recommended_action(
                bare_probability, built_probability, tree_probability
            )
            if ndvi < 0:
                cell["exclusion_reason"] = "water"
            else:
                cell["priority_eligible"] = bare_probability <= 0.5
                if bare_probability > 0.5:
                    cell["exclusion_reason"] = "bare_land"
        cells.append(cell)

    valid_cells = [
        cell for cell in cells if bool(cell["_complete"]) and cell["exclusion_reason"] != "water"
    ]
    if not valid_cells:
        raise ScoringError("No complete non-water cells are available for scoring.")

    eligible_cells = [
        cell for cell in valid_cells if bool(cell["priority_eligible"])
    ]
    if eligible_cells:
        eligible_populations = [
            float(cell["population_estimate"]) for cell in eligible_cells
        ]
        population_constant = (
            0.0 if max(eligible_populations) <= 1e-12 else 0.5
        )
        normalized_metrics = (
            _normalize(
                [float(cell["ndvi"]) for cell in valid_cells],
                constant_value=0.5,
                reference_values=[
                    float(cell["ndvi"]) for cell in eligible_cells
                ],
            ),
            _normalize(
                [float(cell["lst_c"]) for cell in valid_cells],
                constant_value=0.5,
                reference_values=[
                    float(cell["lst_c"]) for cell in eligible_cells
                ],
            ),
            _normalize(
                [float(cell["population_estimate"]) for cell in valid_cells],
                constant_value=population_constant,
                reference_values=eligible_populations,
            ),
        )

        for cell, ndvi_norm, lst_norm, population_norm in zip(
            valid_cells, *normalized_metrics
        ):
            exposure = 0.5 * lst_norm + 0.5 * (1 - ndvi_norm)
            priority = exposure * (0.5 + 0.5 * population_norm)
            cell["normalized_ndvi"] = ndvi_norm
            cell["normalized_lst"] = lst_norm
            cell["normalized_population"] = population_norm
            cell["exposure_score"] = exposure
            cell["priority_score"] = priority

    ranked_cells = sorted(
        eligible_cells,
        key=lambda cell: (
            -float(_format_number(float(cell["priority_score"]))),
            str(cell["cell_id"]),
        ),
    )
    top_count = math.ceil(len(ranked_cells) * 0.10) if ranked_cells else 0
    top_cells = ranked_cells[:top_count]
    for cell in top_cells:
        cell["top_10_percent"] = True

    for cell in cells:
        cell.pop("_complete")
    sorted_cells = sorted(cells, key=lambda cell: str(cell["cell_id"]))
    full_rows = [
        {
            key: _format_number(value) if isinstance(value, float) else value
            for key, value in cell.items()
        }
        for cell in sorted_cells
    ]
    top_rows = []
    for rank, cell in enumerate(top_cells, start=1):
        row = dict(cell)
        row["rank"] = rank
        top_rows.append(
            {
                key: _format_number(value) if isinstance(value, float) else value
                for key, value in row.items()
            }
        )

    all_cells_path = output_dir / "cell_priority_scores.csv"
    top_cells_path = output_dir / "top_priority_cells.csv"
    metadata_path = output_dir / "scoring_metadata.json"
    _write_atomic(all_cells_path, _csv_bytes(SCORED_FIELDS, full_rows))
    _write_atomic(top_cells_path, _csv_bytes(TOP_FIELDS, top_rows))

    lst_values = [float(cell["lst_c"]) for cell in valid_cells]
    ndvi_values = [float(cell["ndvi"]) for cell in valid_cells]
    lst_slope = _linear_slope(ndvi_values, lst_values)
    metadata = {
        "city": config.city,
        "analysis_start_inclusive": config.start_date.isoformat(),
        "analysis_end_inclusive": config.end_date.isoformat(),
        "score_formula": (
            "exposure = 0.5 * normalized(LST) + 0.5 * (1 - normalized(NDVI)); "
            "priority = exposure * (0.5 + 0.5 * normalized(population))"
        ),
        "normalization": (
            "min-max reference range across complete, non-water, non-bare "
            "priority-eligible cells; normalized values for bare-land cells are "
            "clamped to 0-1 and never affect eligible-cell scores; constant "
            "NDVI/LST uses 0.5; constant population uses 0 when all reference "
            "values are zero, otherwise 0.5; if no priority-eligible cells exist, "
            "normalized values and scores are unavailable"
        ),
        "action_thresholds": {
            "bare_probability_gt": 0.5,
            "built_probability_gt": 0.6,
            "tree_probability_gt": 0.4,
            "precedence": ["bare", "built-up", "trees", "plant trees"],
        },
        "water_rule": "NDVI < 0 is excluded from scoring and top-list ranking.",
        "normalization_population": (
            "Complete non-water cells with bare probability <= 0.5; bare-land "
            "cells are scored against these ranges for display only."
        ),
        "top_list_rule": (
            "ceil(10% of complete, non-water, non-bare cells); sorted by score "
            "descending, then stable cell ID ascending."
        ),
        "cooling_estimate": {
            "statistic": (
                "Pearson correlation and ordinary-least-squares association "
                "between cell NDVI and LST in Celsius"
            ),
            "correlation": _correlation(ndvi_values, lst_values),
            "slope_celsius_per_ndvi": lst_slope,
            "associated_lst_change_c_per_0_1_ndvi": (
                lst_slope * 0.1 if lst_slope is not None else None
            ),
            "caveat": (
                "Observational association only; it does not prove causation or "
                "guarantee that an intervention will cause this cooling."
            ),
            "cell_count": len(valid_cells),
            "included_bare_land_cells": True,
        },
        "cell_count": len(cells),
        "valid_non_water_cell_count": len(valid_cells),
        "priority_eligible_cell_count": len(eligible_cells),
        "top_cell_count": top_count,
        "missing_metric_cell_count": sum(
            cell["exclusion_reason"] == "missing_metrics" for cell in cells
        ),
        "water_cell_count": sum(cell["exclusion_reason"] == "water" for cell in cells),
        "bare_land_cell_count": sum(
            cell["exclusion_reason"] == "bare_land" for cell in cells
        ),
    }
    _write_atomic(
        metadata_path,
        json.dumps(metadata, indent=2, sort_keys=True).encode("utf-8"),
    )
    return ScoringResult(
        all_cells_path=all_cells_path,
        top_cells_path=top_cells_path,
        metadata_path=metadata_path,
        cell_count=len(cells),
        valid_cell_count=len(valid_cells),
        priority_eligible_count=len(eligible_cells),
        top_cell_count=top_count,
    )

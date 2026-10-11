"""Compare cell-level NDVI between two non-overlapping analysis periods."""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import os
import statistics
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Tuple


REQUIRED_CELL_FIELDS = {"cell_id", "longitude", "latitude", "ndvi"}
CELL_FIELDS = (
    "cell_id",
    "longitude",
    "latitude",
    "period_a_ndvi",
    "period_b_ndvi",
    "ndvi_change_b_minus_a",
    "status",
)


class GreenCoverComparisonError(ValueError):
    """Raised when two periods cannot be compared consistently."""


@dataclass(frozen=True)
class GreenCoverComparison:
    cells_path: Path
    summary_path: Path
    matched_cell_count: int
    comparable_cell_count: int


def _read_metadata(path: Path) -> Mapping[str, object]:
    try:
        metadata = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise GreenCoverComparisonError(
            f"Could not read scoring metadata at {path}."
        ) from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GreenCoverComparisonError(
            f"Scoring metadata is not valid UTF-8 JSON: {path}."
        ) from exc
    if not isinstance(metadata, dict):
        raise GreenCoverComparisonError(
            f"Scoring metadata must be a JSON object: {path}."
        )
    required = ("city", "analysis_start_inclusive", "analysis_end_inclusive")
    if any(not isinstance(metadata.get(key), str) for key in required):
        raise GreenCoverComparisonError(
            f"Scoring metadata is missing comparison fields: {path}."
        )
    return metadata


def _period(metadata: Mapping[str, object], label: str) -> Tuple[date, date]:
    try:
        start = date.fromisoformat(str(metadata["analysis_start_inclusive"]))
        end = date.fromisoformat(str(metadata["analysis_end_inclusive"]))
    except ValueError as exc:
        raise GreenCoverComparisonError(
            f"Period {label} has invalid analysis dates."
        ) from exc
    if start.isoformat() != metadata["analysis_start_inclusive"] or (
        end.isoformat() != metadata["analysis_end_inclusive"]
    ):
        raise GreenCoverComparisonError(
            f"Period {label} dates must use YYYY-MM-DD format."
        )
    if start > end:
        raise GreenCoverComparisonError(
            f"Period {label} start date must be on or before its end date."
        )
    return start, end


def _number(value: Optional[str], name: str, row_number: int) -> Optional[float]:
    if value is None or not value.strip():
        return None
    try:
        parsed = float(value)
    except ValueError as exc:
        raise GreenCoverComparisonError(
            f"Row {row_number} has a non-numeric {name}."
        ) from exc
    if not math.isfinite(parsed):
        raise GreenCoverComparisonError(
            f"Row {row_number} has a non-finite {name}."
        )
    return parsed


def _read_cells(path: Path) -> Dict[str, Dict[str, object]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            missing = REQUIRED_CELL_FIELDS.difference(reader.fieldnames or ())
            if missing:
                raise GreenCoverComparisonError(
                    f"{path} is missing fields: {', '.join(sorted(missing))}."
                )
            rows = list(reader)
    except OSError as exc:
        raise GreenCoverComparisonError(f"Could not read scored cells at {path}.") from exc
    except (UnicodeDecodeError, csv.Error) as exc:
        raise GreenCoverComparisonError(f"Scored cells are invalid at {path}.") from exc
    if not rows:
        raise GreenCoverComparisonError(f"Scored-cell CSV is empty: {path}.")

    cells: Dict[str, Dict[str, object]] = {}
    for row_number, row in enumerate(rows, start=2):
        cell_id = row.get("cell_id", "")
        if not cell_id or cell_id in cells:
            raise GreenCoverComparisonError(
                f"Row {row_number} has an empty or duplicate cell ID."
            )
        longitude = _number(row.get("longitude"), "longitude", row_number)
        latitude = _number(row.get("latitude"), "latitude", row_number)
        ndvi = _number(row.get("ndvi"), "NDVI", row_number)
        if longitude is None or latitude is None:
            raise GreenCoverComparisonError(
                f"Row {row_number} is missing cell coordinates."
            )
        if not -180 <= longitude <= 180 or not -90 <= latitude <= 90:
            raise GreenCoverComparisonError(
                f"Row {row_number} has coordinates outside valid longitude/latitude ranges."
            )
        if ndvi is not None and not -1 <= ndvi <= 1:
            raise GreenCoverComparisonError(f"Row {row_number} NDVI must be between -1 and 1.")
        cells[cell_id] = {
            "longitude": longitude,
            "latitude": latitude,
            "ndvi": ndvi,
        }
    return cells


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


def _csv_bytes(rows: List[Dict[str, object]]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=CELL_FIELDS)
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


def _format(value: Optional[float]) -> Optional[str]:
    return None if value is None else f"{value:.8f}"


def compare_scored_periods(
    period_a_cells_path: Path,
    period_a_metadata_path: Path,
    period_b_cells_path: Path,
    period_b_metadata_path: Path,
    output_dir: Path,
) -> GreenCoverComparison:
    """Compare NDVI at matching grid cells; change is period B minus period A."""
    metadata_a = _read_metadata(period_a_metadata_path)
    metadata_b = _read_metadata(period_b_metadata_path)
    if metadata_a["city"].casefold() != metadata_b["city"].casefold():
        raise GreenCoverComparisonError(
            "Both periods must use the same configured city."
        )
    start_a, end_a = _period(metadata_a, "A")
    start_b, end_b = _period(metadata_b, "B")
    if start_a > start_b or end_a >= start_b:
        raise GreenCoverComparisonError(
            "Period A must be earlier than and non-overlapping with period B."
        )

    cells_a = _read_cells(period_a_cells_path)
    cells_b = _read_cells(period_b_cells_path)
    if cells_a.keys() != cells_b.keys():
        missing_from_b = len(cells_a.keys() - cells_b.keys())
        missing_from_a = len(cells_b.keys() - cells_a.keys())
        raise GreenCoverComparisonError(
            "The periods must contain the same grid-cell IDs; "
            f"{missing_from_b} are missing from period B and "
            f"{missing_from_a} are missing from period A."
        )

    output_rows: List[Dict[str, object]] = []
    changes: List[float] = []
    water_excluded_count = 0
    missing_ndvi_count = 0
    for cell_id in sorted(cells_a):
        before = cells_a[cell_id]
        after = cells_b[cell_id]
        if (
            abs(float(before["longitude"]) - float(after["longitude"])) > 1e-7
            or abs(float(before["latitude"]) - float(after["latitude"])) > 1e-7
        ):
            raise GreenCoverComparisonError(
                f"Cell {cell_id} has different coordinates between periods."
            )
        ndvi_a = before["ndvi"]
        ndvi_b = after["ndvi"]
        status = "comparable"
        change: Optional[float] = None
        if ndvi_a is None or ndvi_b is None:
            status = "missing_ndvi"
            missing_ndvi_count += 1
        elif float(ndvi_a) < 0 or float(ndvi_b) < 0:
            status = "water_in_at_least_one_period"
            water_excluded_count += 1
        else:
            change = float(ndvi_b) - float(ndvi_a)
            changes.append(change)
        output_rows.append(
            {
                "cell_id": cell_id,
                "longitude": _format(float(before["longitude"])),
                "latitude": _format(float(before["latitude"])),
                "period_a_ndvi": _format(ndvi_a),
                "period_b_ndvi": _format(ndvi_b),
                "ndvi_change_b_minus_a": _format(change),
                "status": status,
            }
        )

    if not changes:
        raise GreenCoverComparisonError(
            "No matching non-water cells have complete NDVI in both periods."
        )

    comparable_count = len(changes)
    summary = {
        "city": metadata_a["city"],
        "period_a": {
            "start_inclusive": start_a.isoformat(),
            "end_inclusive": end_a.isoformat(),
        },
        "period_b": {
            "start_inclusive": start_b.isoformat(),
            "end_inclusive": end_b.isoformat(),
        },
        "change_definition": "period_b_ndvi - period_a_ndvi",
        "cell_alignment": (
            "Exact stable cell-ID set match and coordinate equality within "
            "1e-7 degrees."
        ),
        "included_cells": (
            "Cells with NDVI >= 0 in both periods; cells with missing NDVI or "
            "NDVI < 0 in either period are excluded from summary statistics."
        ),
        "matched_cell_count": len(output_rows),
        "comparable_cell_count": comparable_count,
        "water_excluded_cell_count": water_excluded_count,
        "missing_ndvi_cell_count": missing_ndvi_count,
        "mean_ndvi_change": statistics.fmean(changes),
        "median_ndvi_change": statistics.median(changes),
        "increased_ndvi_cell_count": sum(change > 0 for change in changes),
        "decreased_ndvi_cell_count": sum(change < 0 for change in changes),
        "unchanged_ndvi_cell_count": sum(change == 0 for change in changes),
        "interpretation_caveat": (
            "NDVI change is a vegetation-index difference, not a direct measure "
            "of green-cover area or proof of a cause. Seasonal weather, imagery "
            "availability, clouds, land-cover change, and sensor processing can "
            "affect comparisons. Review the matched data and validate findings "
            "with independent imagery or field observations."
        ),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    cells_path = output_dir / "green_cover_change.csv"
    summary_path = output_dir / "green_cover_change_summary.json"
    _write_atomic(cells_path, _csv_bytes(output_rows))
    _write_atomic(
        summary_path,
        json.dumps(summary, indent=2, sort_keys=True).encode("utf-8"),
    )
    return GreenCoverComparison(
        cells_path=cells_path,
        summary_path=summary_path,
        matched_cell_count=len(output_rows),
        comparable_cell_count=comparable_count,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Compare cell-level NDVI from two non-overlapping scoring periods."
        )
    )
    parser.add_argument("--period-a-cells", type=Path, required=True)
    parser.add_argument("--period-a-metadata", type=Path, required=True)
    parser.add_argument("--period-b-cells", type=Path, required=True)
    parser.add_argument("--period-b-metadata", type=Path, required=True)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs") / "green_cover_comparison",
    )
    args = parser.parse_args()
    try:
        result = compare_scored_periods(
            args.period_a_cells,
            args.period_a_metadata,
            args.period_b_cells,
            args.period_b_metadata,
            args.output_dir,
        )
    except GreenCoverComparisonError as exc:
        parser.error(str(exc))
    print(f"Compared {result.comparable_cell_count:,} non-water cells.")
    print(f"Cell changes: {result.cells_path}")
    print(f"Summary: {result.summary_path}")


if __name__ == "__main__":
    main()

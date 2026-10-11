"""Tests for comparing NDVI across two analysis periods."""

import csv
import json
import tempfile
import unittest
from pathlib import Path

from compare_green_cover import (
    GreenCoverComparisonError,
    compare_scored_periods,
)


class GreenCoverComparisonTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.period_a_cells = self.root / "period_a_cells.csv"
        self.period_b_cells = self.root / "period_b_cells.csv"
        self.period_a_metadata = self.root / "period_a_metadata.json"
        self.period_b_metadata = self.root / "period_b_metadata.json"
        self.output_dir = self.root / "comparison"
        self.rows_a = [
            ("cell_0000000000000001", 79.001, 21.001, "0.20"),
            ("cell_0000000000000002", 79.002, 21.002, "0.40"),
            ("cell_0000000000000003", 79.003, 21.003, "-0.02"),
            ("cell_0000000000000004", 79.004, 21.004, ""),
        ]
        self.rows_b = [
            ("cell_0000000000000001", 79.001, 21.001, "0.30"),
            ("cell_0000000000000002", 79.002, 21.002, "0.40"),
            ("cell_0000000000000003", 79.003, 21.003, "0.10"),
            ("cell_0000000000000004", 79.004, 21.004, "0.60"),
        ]
        self._write_cells(self.period_a_cells, self.rows_a)
        self._write_cells(self.period_b_cells, self.rows_b)
        self._write_metadata(
            self.period_a_metadata, "2024-03-01", "2024-05-31", "Nagpur"
        )
        self._write_metadata(
            self.period_b_metadata, "2025-03-01", "2025-05-31", "Nagpur"
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    @staticmethod
    def _write_cells(path: Path, rows: list[tuple[str, float, float, str]]) -> None:
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle, fieldnames=["cell_id", "longitude", "latitude", "ndvi"]
            )
            writer.writeheader()
            for cell_id, longitude, latitude, ndvi in rows:
                writer.writerow(
                    {
                        "cell_id": cell_id,
                        "longitude": longitude,
                        "latitude": latitude,
                        "ndvi": ndvi,
                    }
                )

    @staticmethod
    def _write_metadata(path: Path, start: str, end: str, city: str) -> None:
        path.write_text(
            json.dumps(
                {
                    "city": city,
                    "analysis_start_inclusive": start,
                    "analysis_end_inclusive": end,
                }
            ),
            encoding="utf-8",
        )

    def test_compares_matching_non_water_cells_and_writes_summary(self) -> None:
        result = compare_scored_periods(
            self.period_a_cells,
            self.period_a_metadata,
            self.period_b_cells,
            self.period_b_metadata,
            self.output_dir,
        )

        self.assertEqual(result.matched_cell_count, 4)
        self.assertEqual(result.comparable_cell_count, 2)
        with result.cells_path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        by_id = {row["cell_id"]: row for row in rows}
        self.assertEqual(by_id["cell_0000000000000001"]["ndvi_change_b_minus_a"], "0.10000000")
        self.assertEqual(by_id["cell_0000000000000002"]["ndvi_change_b_minus_a"], "0.00000000")
        self.assertEqual(
            by_id["cell_0000000000000003"]["status"],
            "water_in_at_least_one_period",
        )
        self.assertEqual(by_id["cell_0000000000000004"]["status"], "missing_ndvi")

        summary = json.loads(result.summary_path.read_text(encoding="utf-8"))
        self.assertEqual(summary["increased_ndvi_cell_count"], 1)
        self.assertEqual(summary["decreased_ndvi_cell_count"], 0)
        self.assertEqual(summary["unchanged_ndvi_cell_count"], 1)
        self.assertEqual(summary["water_excluded_cell_count"], 1)
        self.assertEqual(summary["missing_ndvi_cell_count"], 1)
        self.assertAlmostEqual(summary["mean_ndvi_change"], 0.05)
        self.assertIn("not a direct measure", summary["interpretation_caveat"])

    def test_rejects_different_grid_cell_sets(self) -> None:
        self._write_cells(
            self.period_b_cells,
            self.rows_b[:-1],
        )

        with self.assertRaisesRegex(
            GreenCoverComparisonError, "same grid-cell IDs"
        ):
            compare_scored_periods(
                self.period_a_cells,
                self.period_a_metadata,
                self.period_b_cells,
                self.period_b_metadata,
                self.output_dir,
            )

    def test_rejects_overlapping_periods(self) -> None:
        self._write_metadata(
            self.period_b_metadata, "2024-05-01", "2024-07-31", "Nagpur"
        )

        with self.assertRaisesRegex(
            GreenCoverComparisonError, "earlier than and non-overlapping"
        ):
            compare_scored_periods(
                self.period_a_cells,
                self.period_a_metadata,
                self.period_b_cells,
                self.period_b_metadata,
                self.output_dir,
            )

    def test_rejects_city_mismatch(self) -> None:
        self._write_metadata(
            self.period_b_metadata, "2025-03-01", "2025-05-31", "Pune"
        )

        with self.assertRaisesRegex(
            GreenCoverComparisonError, "same configured city"
        ):
            compare_scored_periods(
                self.period_a_cells,
                self.period_a_metadata,
                self.period_b_cells,
                self.period_b_metadata,
                self.output_dir,
            )

    def test_rejects_coordinate_mismatch(self) -> None:
        changed_rows = list(self.rows_b)
        changed_rows[0] = (
            changed_rows[0][0],
            changed_rows[0][1] + 0.01,
            changed_rows[0][2],
            changed_rows[0][3],
        )
        self._write_cells(self.period_b_cells, changed_rows)

        with self.assertRaisesRegex(
            GreenCoverComparisonError, "different coordinates"
        ):
            compare_scored_periods(
                self.period_a_cells,
                self.period_a_metadata,
                self.period_b_cells,
                self.period_b_metadata,
                self.output_dir,
            )


if __name__ == "__main__":
    unittest.main()

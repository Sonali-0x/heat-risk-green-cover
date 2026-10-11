"""Tests for priority scoring, action rules, eligibility, and export selection."""

import csv
import json
import math
import tempfile
import unittest
from pathlib import Path

from config import load_config
from scoring import ScoringError, score_prepared_csv


def _source_row(
    longitude: float,
    ndvi: str,
    lst: str,
    population: str,
    tree: str = "0.2",
    built: str = "0.2",
    bare: str = "0.1",
) -> dict[str, str]:
    geometry = json.dumps(
        {"type": "Point", "coordinates": [longitude, 21.0]},
        separators=(",", ":"),
    )
    return {
        "NDVI": ndvi,
        "LST_C": lst,
        "TREE_PROB": tree,
        "BUILT_PROB": built,
        "BARE_PROB": bare,
        "POPULATION": population,
        ".geo": geometry,
    }


class ScoringTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.config = load_config(
            {
                "AOI_BOUNDS": "79.0,21.0,79.1,21.1",
                "MAX_GRID_CELLS": "50000",
            }
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _run(self, rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], dict]:
        input_path = self.root / "prepared.csv"
        with input_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "NDVI",
                    "LST_C",
                    "TREE_PROB",
                    "BUILT_PROB",
                    "BARE_PROB",
                    "POPULATION",
                    ".geo",
                ],
            )
            writer.writeheader()
            writer.writerows(rows)

        result = score_prepared_csv(input_path, self.root / "scored", self.config)
        with result.all_cells_path.open(
            "r", encoding="utf-8", newline=""
        ) as handle:
            scored_rows = list(csv.DictReader(handle))
        metadata = json.loads(result.metadata_path.read_text(encoding="utf-8"))
        return scored_rows, metadata

    def test_priority_matches_prd_formula(self) -> None:
        rows, _ = self._run(
            [
                _source_row(79.001, "0.0", "30", "0"),
                _source_row(79.002, "1.0", "40", "100"),
            ]
        )

        low = next(row for row in rows if float(row["longitude"]) == 79.001)
        high = next(row for row in rows if float(row["longitude"]) == 79.002)
        self.assertAlmostEqual(float(low["exposure_score"]), 0.5)
        self.assertAlmostEqual(float(low["priority_score"]), 0.25)
        self.assertAlmostEqual(float(high["exposure_score"]), 0.5)
        self.assertAlmostEqual(float(high["priority_score"]), 0.5)

    def test_constant_metrics_use_documented_neutral_normalization(self) -> None:
        rows, _ = self._run(
            [
                _source_row(79.001, "0.3", "35", "0"),
                _source_row(79.002, "0.3", "35", "0"),
            ]
        )

        for row in rows:
            self.assertEqual(float(row["normalized_ndvi"]), 0.5)
            self.assertEqual(float(row["normalized_lst"]), 0.5)
            self.assertEqual(float(row["normalized_population"]), 0.0)
            self.assertEqual(float(row["exposure_score"]), 0.5)
            self.assertEqual(float(row["priority_score"]), 0.25)

    def test_action_precedence_and_strict_thresholds(self) -> None:
        rows, _ = self._run(
            [
                _source_row(79.001, "0.2", "30", "10", "0.9", "0.9", "0.51"),
                _source_row(79.002, "0.2", "31", "10", "0.9", "0.61", "0.5"),
                _source_row(79.003, "0.2", "32", "10", "0.41", "0.6", "0.5"),
                _source_row(79.004, "0.2", "33", "10", "0.4", "0.6", "0.5"),
            ]
        )
        by_longitude = {float(row["longitude"]): row for row in rows}

        self.assertEqual(
            by_longitude[79.001]["recommended_action"], "Check site: bare land"
        )
        self.assertEqual(
            by_longitude[79.002]["recommended_action"], "Cool roof / shade"
        )
        self.assertEqual(
            by_longitude[79.003]["recommended_action"], "Protect existing green"
        )
        self.assertEqual(by_longitude[79.004]["recommended_action"], "Plant trees")

    def test_water_and_bare_cells_are_not_ranked(self) -> None:
        rows, metadata = self._run(
            [
                _source_row(79.001, "-0.01", "40", "100"),
                _source_row(79.002, "0.2", "41", "100", bare="0.5001"),
                _source_row(79.003, "0.3", "42", "100"),
            ]
        )
        by_longitude = {float(row["longitude"]): row for row in rows}

        self.assertEqual(by_longitude[79.001]["exclusion_reason"], "water")
        self.assertEqual(by_longitude[79.002]["exclusion_reason"], "bare_land")
        self.assertEqual(by_longitude[79.003]["priority_eligible"], "True")
        self.assertEqual(metadata["water_cell_count"], 1)
        self.assertEqual(metadata["bare_land_cell_count"], 1)
        self.assertEqual(metadata["priority_eligible_cell_count"], 1)
        self.assertEqual(metadata["top_cell_count"], 1)

    def test_bare_land_outliers_do_not_change_eligible_scores(self) -> None:
        eligible_rows = [
            _source_row(79.001, "0.2", "30", "100"),
            _source_row(79.002, "0.8", "40", "500"),
        ]
        baseline, _ = self._run(eligible_rows)
        with_bare_outlier, metadata = self._run(
            eligible_rows
            + [_source_row(79.003, "1.0", "55", "1000000", bare="0.9")]
        )

        baseline_by_longitude = {
            float(row["longitude"]): row
            for row in baseline
        }
        expanded_by_longitude = {
            float(row["longitude"]): row
            for row in with_bare_outlier
        }
        for longitude in (79.001, 79.002):
            for field in (
                "normalized_ndvi",
                "normalized_lst",
                "normalized_population",
                "exposure_score",
                "priority_score",
            ):
                self.assertEqual(
                    baseline_by_longitude[longitude][field],
                    expanded_by_longitude[longitude][field],
                )

        bare_cell = expanded_by_longitude[79.003]
        self.assertEqual(bare_cell["exclusion_reason"], "bare_land")
        self.assertEqual(float(bare_cell["normalized_ndvi"]), 1.0)
        self.assertEqual(float(bare_cell["normalized_lst"]), 1.0)
        self.assertEqual(float(bare_cell["normalized_population"]), 1.0)
        self.assertEqual(metadata["normalization_population"].split(";")[0],
                         "Complete non-water cells with bare probability <= 0.5")
        self.assertTrue(metadata["cooling_estimate"]["included_bare_land_cells"])

    def test_no_priority_eligible_cells_have_unavailable_scores(self) -> None:
        rows, metadata = self._run(
            [
                _source_row(79.001, "0.2", "35", "100", bare="0.8"),
                _source_row(79.002, "0.3", "36", "200", bare="0.9"),
            ]
        )

        self.assertEqual(metadata["priority_eligible_cell_count"], 0)
        self.assertEqual(metadata["top_cell_count"], 0)
        self.assertTrue(all(row["priority_score"] == "" for row in rows))
        self.assertTrue(all(row["exclusion_reason"] == "bare_land" for row in rows))

    def test_missing_metrics_are_unavailable_and_excluded(self) -> None:
        missing = _source_row(79.001, "0.2", "38", "120")
        missing["TREE_PROB"] = ""
        rows, metadata = self._run(
            [missing, _source_row(79.002, "0.4", "40", "220")]
        )
        missing_cell = next(
            row for row in rows if float(row["longitude"]) == 79.001
        )

        self.assertEqual(missing_cell["recommended_action"], "Unavailable")
        self.assertEqual(missing_cell["exclusion_reason"], "missing_metrics")
        self.assertEqual(missing_cell["priority_score"], "")
        self.assertEqual(metadata["missing_metric_cell_count"], 1)

    def test_top_decile_uses_ceiling_and_deterministic_ties(self) -> None:
        rows, metadata = self._run(
            [
                _source_row(
                    79.001 + index / 100_000,
                    "0.5",
                    "35",
                    "50",
                )
                for index in range(11)
            ]
        )
        selected = [row for row in rows if row["top_10_percent"] == "True"]

        self.assertEqual(len(selected), math.ceil(11 * 0.10))
        self.assertEqual(metadata["top_cell_count"], 2)
        self.assertEqual(metadata["priority_eligible_cell_count"], 11)

        expected_ids = sorted(row["cell_id"] for row in rows)[:2]
        self.assertEqual(sorted(row["cell_id"] for row in selected), expected_ids)

    def test_highest_priority_cell_is_selected_for_ten_eligible_cells(self) -> None:
        rows, metadata = self._run(
            [
                _source_row(
                    79.001 + index / 100_000,
                    f"{index / 10:.1f}",
                    str(30 + index),
                    str(index * 10),
                )
                for index in range(10)
            ]
        )

        selected = [row for row in rows if row["top_10_percent"] == "True"]
        self.assertEqual(len(selected), 1)
        self.assertAlmostEqual(float(selected[0]["longitude"]), 79.00109)
        self.assertEqual(metadata["top_cell_count"], 1)

    def test_constant_population_zero_keeps_half_exposure_weight(self) -> None:
        rows, _ = self._run(
            [
                _source_row(79.001, "0.3", "30", "0"),
                _source_row(79.002, "0.3", "40", "0"),
            ]
        )

        self.assertTrue(
            all(float(row["normalized_population"]) == 0 for row in rows)
        )

    def test_cooling_association_reports_change_per_point_one_ndvi(self) -> None:
        _, metadata = self._run(
            [
                _source_row(79.001, "0.2", "40", "100"),
                _source_row(79.002, "0.4", "36", "200"),
            ]
        )
        estimate = metadata["cooling_estimate"]

        self.assertAlmostEqual(estimate["correlation"], -1.0)
        self.assertAlmostEqual(estimate["slope_celsius_per_ndvi"], -20.0)
        self.assertAlmostEqual(
            estimate["associated_lst_change_c_per_0_1_ndvi"], -2.0
        )
        self.assertIn("does not prove causation", estimate["caveat"])

    def test_invalid_probability_is_rejected(self) -> None:
        with self.assertRaisesRegex(ScoringError, "BUILT_PROB must be between"):
            self._run(
                [
                    _source_row(79.001, "0.2", "35", "100", built="1.2"),
                    _source_row(79.002, "0.3", "36", "150"),
                ]
            )

    def test_duplicate_cell_centers_are_rejected(self) -> None:
        row = _source_row(79.001, "0.2", "35", "100")
        with self.assertRaisesRegex(ScoringError, "duplicates a grid-cell center"):
            self._run([row, row.copy()])


if __name__ == "__main__":
    unittest.main()

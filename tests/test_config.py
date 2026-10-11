"""Tests for project configuration and input-path validation."""

import tempfile
import unittest
from pathlib import Path

from config import (
    ConfigurationError,
    estimate_grid_cell_count,
    load_config,
    validate_aoi_bounds,
    validate_input_path,
)


class ProjectConfigTests(unittest.TestCase):
    def test_defaults_load_without_analysis_boundary(self) -> None:
        config = load_config({})

        self.assertEqual(config.city, "Nagpur")
        self.assertEqual(config.grid_size_m, 100)
        self.assertIsNone(config.aoi_bounds)
        self.assertEqual(config.report_language, "english")
        self.assertIsNone(config.earth_engine_project)
        self.assertEqual(config.worldpop_year, 2020)

    def test_valid_analysis_settings_and_cell_count(self) -> None:
        config = load_config(
            {
                "AOI_BOUNDS": "79.0,21.0,79.1,21.1",
                "MAX_GRID_CELLS": "50000",
            }
        )

        self.assertGreater(config.validate_for_analysis(), 0)

    def test_missing_boundary_blocks_analysis(self) -> None:
        with self.assertRaisesRegex(ConfigurationError, "AOI_BOUNDS"):
            load_config({}).validate_for_analysis()

    def test_rejects_unsupported_city(self) -> None:
        with self.assertRaisesRegex(ConfigurationError, "Unsupported CITY"):
            load_config({"CITY": "Mumbai"})

    def test_rejects_out_of_india_bounds(self) -> None:
        with self.assertRaisesRegex(ConfigurationError, "within India's"):
            validate_aoi_bounds((79.0, 21.0, 98.0, 21.1))

    def test_rejects_reversed_date_range(self) -> None:
        with self.assertRaisesRegex(ConfigurationError, "on or before"):
            load_config(
                {"START_DATE": "2026-05-01", "END_DATE": "2026-03-01"}
            )

    def test_rejects_grid_exceeding_cell_cap(self) -> None:
        config = load_config(
            {
                "AOI_BOUNDS": "79.0,21.0,79.1,21.1",
                "MAX_GRID_CELLS": "100",
            }
        )

        with self.assertRaisesRegex(ConfigurationError, "exceeding MAX_GRID_CELLS"):
            config.validate_for_analysis()

    def test_estimates_cells_for_valid_bounds(self) -> None:
        count = estimate_grid_cell_count((79.0, 21.0, 79.1, 21.1), 100)

        self.assertGreater(count, 1)

    def test_rejects_output_path_outside_project(self) -> None:
        with self.assertRaisesRegex(ConfigurationError, "inside the project"):
            load_config({"OUTPUT_DIR": ".."})


class InputPathTests(unittest.TestCase):
    def test_accepts_project_synthetic_fixture(self) -> None:
        fixture = Path(__file__).parent / "fixtures" / "sample.geojson"

        self.assertEqual(
            validate_input_path(str(fixture)),
            fixture.resolve(),
        )

    def test_accepts_supported_file_inside_project_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_file = root / "data.geojson"
            input_file.write_text("{}", encoding="utf-8")

            self.assertEqual(
                validate_input_path("data.geojson", project_root=root),
                input_file.resolve(),
            )

    def test_rejects_unsupported_file_type(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_file = root / "data.txt"
            input_file.write_text("data", encoding="utf-8")

            with self.assertRaisesRegex(ConfigurationError, "Unsupported input type"):
                validate_input_path("data.txt", project_root=root)

    def test_rejects_path_outside_project_root(self) -> None:
        with tempfile.TemporaryDirectory() as project_dir:
            with tempfile.TemporaryDirectory() as outside_dir:
                outside_file = Path(outside_dir) / "data.csv"
                outside_file.write_text("a,b", encoding="utf-8")

                with self.assertRaisesRegex(ConfigurationError, "inside the project"):
                    validate_input_path(str(outside_file), project_root=Path(project_dir))

    def test_reports_missing_input(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(ConfigurationError, "does not exist"):
                validate_input_path("missing.csv", project_root=Path(temp_dir))


if __name__ == "__main__":
    unittest.main()

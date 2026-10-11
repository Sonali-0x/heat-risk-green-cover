"""Tests for map, report, and artifact generation."""

import csv
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from config import load_config
from map_output import render_priority_map
from phase5 import OutputGenerationError, generate_outputs
from scoring import score_prepared_csv


def _source_row(longitude: float, ndvi: float, lst: float, population: int) -> dict[str, str]:
    return {
        "NDVI": str(ndvi),
        "LST_C": str(lst),
        "TREE_PROB": "0.2",
        "BUILT_PROB": "0.2",
        "BARE_PROB": "0.1",
        "POPULATION": str(population),
        ".geo": json.dumps(
            {"type": "Point", "coordinates": [longitude, 21.0]},
            separators=(",", ":"),
        ),
    }


class Phase5Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.config = replace(
            load_config(
                {
                    "AOI_BOUNDS": "79.0,21.0,79.1,21.1",
                    "MAX_GRID_CELLS": "50000",
                }
            ),
            output_dir=self.root / "outputs",
        )
        self.scored_dir = self.root / "scored"
        self.scored_dir.mkdir()
        prepared = self.root / "prepared.csv"
        with prepared.open("w", encoding="utf-8", newline="") as handle:
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
            writer.writerows(
                [
                    _source_row(79.001, 0.2, 40, 100),
                    _source_row(79.002, 0.8, 34, 250),
                    _source_row(79.003, 0.4, 37, 120),
                ]
            )
        self.scored = score_prepared_csv(prepared, self.scored_dir, self.config)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _generate(self):
        return generate_outputs(
            self.scored.all_cells_path,
            self.scored.top_cells_path,
            self.scored.metadata_path,
            self.config.output_dir,
            self.config,
        )

    def test_generates_map_ranked_csv_report_and_metadata(self) -> None:
        generated = self._generate()

        self.assertTrue(generated.map_path.is_file())
        self.assertTrue(generated.top_cells_path.is_file())
        self.assertTrue(generated.report_path.is_file())
        self.assertTrue(generated.metadata_path.is_file())
        map_html = generated.map_path.read_text(encoding="utf-8")
        report = generated.report_path.read_text(encoding="utf-8")
        metadata = json.loads(generated.metadata_path.read_text(encoding="utf-8"))
        with generated.top_cells_path.open(encoding="utf-8", newline="") as handle:
            ranked_rows = list(csv.DictReader(handle))

        self.assertIn("NDVI", map_html)
        self.assertIn("LST (°C)", map_html)
        self.assertIn("Priority", map_html)
        self.assertIn("Surface temperature is not air temperature", map_html)
        self.assertIn("correlation", report.casefold())
        self.assertIn("Field verification is required", report)
        self.assertEqual(len(ranked_rows), self.scored.top_cell_count)
        self.assertEqual(metadata["scoring"]["city"], "Nagpur")
        self.assertEqual(metadata["license_and_attribution_status"][:10], "Dataset-sp")

    def test_popup_values_are_html_escaped(self) -> None:
        with self.scored.all_cells_path.open(
            "r", encoding="utf-8", newline=""
        ) as handle:
            reader = csv.DictReader(handle)
            rows = list(reader)
        rows[0]["recommended_action"] = "<script>alert(1)</script>"
        metadata = json.loads(self.scored.metadata_path.read_text(encoding="utf-8"))
        map_html = render_priority_map(rows, metadata, title=self.config.map_title)
        self.assertNotIn("<script>alert(1)</script>", map_html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", map_html)

    def test_report_uses_selected_language_for_actions_and_sources(self) -> None:
        hindi_config = replace(self.config, report_language="hindi")
        generated = generate_outputs(
            self.scored.all_cells_path,
            self.scored.top_cells_path,
            self.scored.metadata_path,
            self.config.output_dir,
            hindi_config,
        )
        report = generated.report_path.read_text(encoding="utf-8")

        self.assertIn("# शहरी गर्मी और हरित क्षेत्र", report)
        self.assertIn("पेड़ लगाएँ", report)
        self.assertIn("भूमि-सतह तापमान", report)

    def test_rejects_metadata_for_another_analysis_period(self) -> None:
        metadata = json.loads(self.scored.metadata_path.read_text(encoding="utf-8"))
        metadata["analysis_start_inclusive"] = "2025-03-01"
        self.scored.metadata_path.write_text(
            json.dumps(metadata), encoding="utf-8"
        )

        with self.assertRaisesRegex(
            OutputGenerationError, "does not match the configured analysis start"
        ):
            self._generate()


if __name__ == "__main__":
    unittest.main()

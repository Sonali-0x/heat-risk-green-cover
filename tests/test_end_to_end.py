"""Synthetic end-to-end test from per-cell inputs through the static site."""

import csv
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from config import load_config
from phase5 import generate_outputs
from publish_site import publish_site
from scoring import score_prepared_csv


class SyntheticEndToEndTests(unittest.TestCase):
    def test_prepared_metrics_generate_ranked_map_report_and_site(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            config = replace(
                load_config(
                    {
                        "AOI_BOUNDS": "79.0,21.0,79.1,21.1",
                        "MAX_GRID_CELLS": "50000",
                    }
                ),
                output_dir=root / "outputs",
                site_dir=root / "site",
            )
            prepared_path = root / "synthetic_prepared_cells.csv"
            fields = [
                "NDVI",
                "LST_C",
                "TREE_PROB",
                "BUILT_PROB",
                "BARE_PROB",
                "POPULATION",
                ".geo",
            ]
            rows = [
                (0.4, 36, 0.8, 0.2, 0.1, 150),
                (0.3, 42, 0.1, 0.1, 0.8, 400),
                (-0.05, 38, 0.1, 0.8, 0.1, 300),
                (0.2, 41, 0.1, 0.7, 0.1, 350),
                (0.6, 34, 0.5, 0.2, 0.1, 200),
            ]
            with prepared_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                for index, metrics in enumerate(rows):
                    ndvi, lst, tree, built, bare, population = metrics
                    writer.writerow(
                        {
                            "NDVI": ndvi,
                            "LST_C": lst,
                            "TREE_PROB": tree,
                            "BUILT_PROB": built,
                            "BARE_PROB": bare,
                            "POPULATION": population,
                            ".geo": (
                                '{"type":"Point","coordinates":['
                                f"{79.001 + index / 1000},21.0]}}"
                            ),
                        }
                    )

            scored = score_prepared_csv(
                prepared_path,
                config.output_dir / "scored",
                config,
            )
            generated = generate_outputs(
                scored.all_cells_path,
                scored.top_cells_path,
                scored.metadata_path,
                config.output_dir,
                config,
            )
            published = publish_site(
                config.output_dir,
                config.site_dir,
                site_url="https://demo.example/heat/",
            )

            self.assertTrue(generated.map_path.is_file())
            self.assertTrue(generated.report_path.is_file())
            self.assertTrue(generated.top_cells_path.is_file())
            self.assertTrue((published.site_dir / "index.html").is_file())
            self.assertTrue((published.site_dir / "priority_map.html").is_file())
            self.assertTrue((published.site_dir / "top_priority_cells.csv").is_file())
            self.assertTrue((published.site_dir / "action_report.md").is_file())
            robots = (published.site_dir / "robots.txt").read_text(encoding="utf-8")
            self.assertIn("https://demo.example/heat/sitemap.xml", robots)
            with generated.top_cells_path.open(
                "r", encoding="utf-8", newline=""
            ) as handle:
                ranked = list(csv.DictReader(handle))
            self.assertEqual(len(ranked), scored.top_cell_count)
            self.assertTrue(
                all(float(row["ndvi"]) >= 0 for row in ranked)
            )
            self.assertTrue(
                all(float(row["bare_probability"]) <= 0.5 for row in ranked)
            )
            self.assertIn(
                "correlation",
                generated.report_path.read_text(encoding="utf-8").casefold(),
            )


if __name__ == "__main__":
    unittest.main()

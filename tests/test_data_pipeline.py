"""Offline tests for data preparation setup and cache behavior."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from config import load_config
from data_pipeline import DataPipelineError, prepare_inputs


class DataPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = load_config(
            {
                "AOI_BOUNDS": "79.0,21.0,79.1,21.1",
                "EARTH_ENGINE_PROJECT": "test-earth-engine-project",
                "MAX_GRID_CELLS": "50000",
            }
        )

    def test_offline_mode_requires_a_matching_cache(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_dir = Path(temp_dir)
            paths = (
                cache_dir / "missing.csv",
                cache_dir / "missing.json",
                "test-cache-key",
            )
            with patch("data_pipeline._cache_paths", return_value=paths):
                with self.assertRaisesRegex(DataPipelineError, "No prepared-data cache"):
                    prepare_inputs(self.config, offline=True)

    def test_offline_mode_loads_a_matching_cache(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_dir = Path(temp_dir)
            csv_path = cache_dir / "prepared.csv"
            metadata_path = cache_dir / "prepared.json"
            cache_key = "test-cache-key"
            csv_path.write_text(
                "NDVI,LST_C,TREE_PROB,BUILT_PROB,BARE_PROB,POPULATION,.geo\n"
                '0.2,38.0,0.3,0.5,0.1,1200,"{""type"":""Point"",""coordinates"":[79,21]}"\n',
                encoding="utf-8",
            )
            metadata_path.write_text(
                json.dumps(
                    {
                        "cache_key": cache_key,
                        "cell_count": 4,
                        "complete_cell_count": 3,
                    }
                ),
                encoding="utf-8",
            )
            paths = (csv_path, metadata_path, cache_key)

            with patch("data_pipeline._cache_paths", return_value=paths):
                prepared = prepare_inputs(self.config, offline=True)

        self.assertEqual(prepared.cell_count, 4)
        self.assertEqual(prepared.complete_cell_count, 3)

    def test_online_mode_requires_an_earth_engine_project(self) -> None:
        config_without_project = load_config(
            {
                "AOI_BOUNDS": "79.0,21.0,79.1,21.1",
                "MAX_GRID_CELLS": "50000",
            }
        )

        with self.assertRaisesRegex(DataPipelineError, "EARTH_ENGINE_PROJECT"):
            prepare_inputs(config_without_project)


if __name__ == "__main__":
    unittest.main()

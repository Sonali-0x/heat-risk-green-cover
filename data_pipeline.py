"""Prepare and cache aligned heat-risk source metrics from Earth Engine."""

import hashlib
import importlib
import json
import os
import tempfile
import csv
import io
from dataclasses import dataclass
from datetime import timedelta, timezone, datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.request import urlopen

from config import ProjectConfig


MAX_DOWNLOAD_BYTES = 32 * 1024 * 1024
WORLDPOP_COLLECTION = "WorldPop/GP/100m/pop"
LANDSAT_COLLECTIONS = (
    "LANDSAT/LC08/C02/T1_L2",
    "LANDSAT/LC09/C02/T1_L2",
)
DYNAMIC_WORLD_COLLECTION = "GOOGLE/DYNAMICWORLD/V1"
TARGET_CRS = "EPSG:32644"
OUTPUT_BANDS = (
    "NDVI",
    "LST_C",
    "TREE_PROB",
    "BUILT_PROB",
    "BARE_PROB",
    "POPULATION",
)


class DataPipelineError(RuntimeError):
    """Raised when source data cannot be prepared or a valid cache is absent."""


@dataclass(frozen=True)
class PreparedInputs:
    csv_path: Path
    metadata_path: Path
    cache_key: str
    cell_count: int
    complete_cell_count: int


def _cache_key(config: ProjectConfig) -> str:
    settings = {
        "city": config.city,
        "start_date": config.start_date.isoformat(),
        "end_date": config.end_date.isoformat(),
        "aoi_bounds": config.aoi_bounds,
        "grid_size_m": config.grid_size_m,
        "worldpop_year": config.worldpop_year,
        "target_crs": TARGET_CRS,
    }
    encoded = json.dumps(settings, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()[:12]


def _cache_paths(config: ProjectConfig) -> Tuple[Path, Path, str]:
    cache_key = _cache_key(config)
    date_range = (
        f"{config.start_date:%Y%m%d}-{config.end_date:%Y%m%d}"
    )
    stem = f"{config.city.lower()}-{date_range}-{config.grid_size_m}m-{cache_key}"
    cache_dir = config.output_dir / "prepared"
    return cache_dir / f"{stem}.csv", cache_dir / f"{stem}.json", cache_key


def _read_cache(
    csv_path: Path, metadata_path: Path, cache_key: str
) -> PreparedInputs:
    if not csv_path.is_file() or not metadata_path.is_file():
        raise DataPipelineError(
            "No prepared-data cache matches these settings. Run without --offline "
            "once while Earth Engine access is available."
        )
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DataPipelineError(
            f"Prepared-data metadata is invalid: {metadata_path}"
        ) from exc
    if not isinstance(metadata, dict):
        raise DataPipelineError(f"Prepared-data metadata is invalid: {metadata_path}")
    if metadata.get("cache_key") != cache_key:
        raise DataPipelineError(
            "Prepared-data cache settings do not match the current configuration."
        )
    try:
        cell_count = int(metadata["cell_count"])
        complete_cell_count = int(metadata["complete_cell_count"])
    except (KeyError, TypeError, ValueError) as exc:
        raise DataPipelineError(
            f"Prepared-data metadata is incomplete: {metadata_path}"
        ) from exc
    if cell_count < 1 or not 1 <= complete_cell_count <= cell_count:
        raise DataPipelineError(
            f"Prepared-data cell counts are invalid: {metadata_path}"
        )
    _validate_csv(csv_path.read_bytes())
    return PreparedInputs(
        csv_path=csv_path,
        metadata_path=metadata_path,
        cache_key=cache_key,
        cell_count=cell_count,
        complete_cell_count=complete_cell_count,
    )


def _validate_csv(content: bytes) -> None:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise DataPipelineError("Prepared CSV is not valid UTF-8.") from exc
    reader = csv.DictReader(io.StringIO(text))
    required_fields = set(OUTPUT_BANDS) | {".geo"}
    missing_fields = required_fields.difference(reader.fieldnames or ())
    if missing_fields:
        missing = ", ".join(sorted(missing_fields))
        raise DataPipelineError(
            f"Prepared CSV is missing required fields: {missing}."
        )
    if next(reader, None) is None:
        raise DataPipelineError("Prepared CSV contains no cell rows.")


def _atomic_write(destination: Path, content: bytes) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=destination.parent, prefix=".partial-", delete=False
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            temporary_file.write(content)
        os.replace(temporary_path, destination)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def _metadata(
    config: ProjectConfig,
    cache_key: str,
    cell_count: int,
    complete_cell_count: int,
) -> Dict[str, Any]:
    return {
        "cache_key": cache_key,
        "city": config.city,
        "aoi": {
            "type": "bounding_box",
            "crs": "EPSG:4326",
            "west_south_east_north": list(config.aoi_bounds or ()),
            "boundary_verification": "pending",
        },
        "date_start_inclusive": config.start_date.isoformat(),
        "date_end_inclusive": config.end_date.isoformat(),
        "landsat_collections": list(LANDSAT_COLLECTIONS),
        "landsat_processing": {
            "surface_reflectance_scale": 0.0000275,
            "surface_reflectance_offset": -0.2,
            "ndvi_formula": "(SR_B5 - SR_B4) / (SR_B5 + SR_B4)",
            "surface_temperature_band": "ST_B10",
            "surface_temperature_scale": 0.00341802,
            "surface_temperature_offset_kelvin": 149.0,
            "kelvin_to_celsius_offset": -273.15,
            "composite": "cloud-masked seasonal median",
            "quality_mask": "QA_PIXEL bits 0 through 5 and QA_RADSAT == 0",
        },
        "dynamic_world_collection": DYNAMIC_WORLD_COLLECTION,
        "dynamic_world_processing": {
            "source_bands": ["trees", "built", "bare"],
            "composite": "seasonal median probability",
            "aggregation": "mean probability per target cell",
        },
        "worldpop_collection": WORLDPOP_COLLECTION,
        "worldpop_reference_year": config.worldpop_year,
        "worldpop_aggregation": "sum estimated people per target cell",
        "grid_size_m": config.grid_size_m,
        "grid_crs": TARGET_CRS,
        "licenses_and_attribution": (
            "Dataset-specific licenses and attributions verified: Landsat (USGS/NASA, Public Domain), "
            "Dynamic World (WRI/Google, CC-BY 4.0), WorldPop (University of Southampton, CC-BY 4.0), "
            "OpenStreetMap (ODbL)."
        ),
        "cell_count": cell_count,
        "complete_cell_count": complete_cell_count,
        "cells_with_missing_metrics": cell_count - complete_cell_count,
        "cell_geometry": (
            f"sample point at the center of each {config.grid_size_m} m grid cell"
        ),
        "thermal_resolution_note": (
            "Landsat surface-temperature measurements are coarser than the "
            "30 m product grid; reprojection does not add spatial detail."
        ),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def _load_earth_engine() -> Any:
    try:
        return importlib.import_module("ee")
    except ModuleNotFoundError as exc:
        if exc.name == "ee":
            raise DataPipelineError(
                "Earth Engine API is not installed. Install the pinned dependencies "
                "from requirements.txt."
            ) from exc
        raise


def _landsat_metrics(ee: Any, region: Any, start: str, end: str) -> Any:
    collection = None
    for collection_id in LANDSAT_COLLECTIONS:
        source = (
            ee.ImageCollection(collection_id)
            .filterBounds(region)
            .filterDate(start, end)
            .filter(ee.Filter.eq("PROCESSING_LEVEL", "L2SP"))
            .filter(ee.Filter.lt("CLOUD_COVER", 80))
        )
        collection = source if collection is None else collection.merge(source)

    image_count = collection.size().getInfo()
    if not image_count:
        raise DataPipelineError(
            "No Landsat Level 2 surface-temperature scenes were found for the "
            "selected area and dates."
        )

    def prepare_scene(image: Any) -> Any:
        qa = image.select("QA_PIXEL")
        invalid_bits = (1 << 0) | (1 << 1) | (1 << 2) | (1 << 3) | (1 << 4) | (1 << 5)
        clear_pixels = qa.bitwiseAnd(invalid_bits).eq(0)
        unsaturated_pixels = image.select("QA_RADSAT").eq(0)

        red = image.select("SR_B4").multiply(0.0000275).add(-0.2)
        nir = image.select("SR_B5").multiply(0.0000275).add(-0.2)
        denominator = nir.add(red)
        ndvi = (
            nir.subtract(red)
            .divide(denominator)
            .updateMask(denominator.abs().gt(1e-6))
            .rename("NDVI")
        )
        land_surface_temperature = (
            image.select("ST_B10")
            .multiply(0.00341802)
            .add(149.0)
            .subtract(273.15)
            .rename("LST_C")
        )
        return (
            ndvi.addBands(land_surface_temperature)
            .updateMask(clear_pixels)
            .updateMask(unsaturated_pixels)
            .copyProperties(image, ["system:time_start"])
        )

    composite = collection.map(prepare_scene).median()
    source_projection = ee.Image(collection.first()).select("SR_B4").projection()
    return composite.setDefaultProjection(source_projection).clip(region)


def _prepare_earth_engine_collection(
    config: ProjectConfig, ee: Any
) -> Tuple[Any, int, int]:
    if config.aoi_bounds is None:
        raise DataPipelineError("An area of interest is required before data retrieval.")
    if not config.earth_engine_project:
        raise DataPipelineError(
            "Set EARTH_ENGINE_PROJECT to an Earth Engine-enabled Google Cloud "
            "project ID and authenticate locally with `earthengine authenticate`."
        )

    ee.Initialize(project=config.earth_engine_project)
    region = ee.Geometry.Rectangle(
        list(config.aoi_bounds), proj="EPSG:4326", geodesic=False
    )
    start = config.start_date.isoformat()
    end = (config.end_date + timedelta(days=1)).isoformat()

    landsat = _landsat_metrics(ee, region, start, end)

    dynamic_world = (
        ee.ImageCollection(DYNAMIC_WORLD_COLLECTION)
        .filterBounds(region)
        .filterDate(start, end)
    )
    if not dynamic_world.size().getInfo():
        raise DataPipelineError(
            "No Dynamic World scenes were found for the selected area and dates."
        )
    dynamic_world_composite = dynamic_world.select(["trees", "built", "bare"]).median()
    dynamic_world_projection = (
        ee.Image(dynamic_world.first()).select("trees").projection()
    )
    land_cover = (
        dynamic_world_composite.setDefaultProjection(dynamic_world_projection)
        .rename(["TREE_PROB", "BUILT_PROB", "BARE_PROB"])
        .clip(region)
    )

    population = (
        ee.ImageCollection(WORLDPOP_COLLECTION)
        .filter(ee.Filter.eq("year", config.worldpop_year))
        .filterBounds(region)
    )
    if not population.size().getInfo():
        raise DataPipelineError(
            f"No WorldPop data was found for reference year {config.worldpop_year}."
        )
    population_projection = (
        ee.Image(population.first()).select("population").projection()
    )
    population_image = (
        population.mosaic()
        .select("population")
        .setDefaultProjection(population_projection)
        .clip(region)
    )

    target_projection = ee.Projection(TARGET_CRS).atScale(config.grid_size_m)
    landsat_on_grid = (
        landsat.select(["NDVI", "LST_C"])
        .reduceResolution(reducer=ee.Reducer.mean(), maxPixels=1024)
        .reproject(crs=target_projection)
    )
    land_cover_on_grid = (
        land_cover.reduceResolution(reducer=ee.Reducer.mean(), maxPixels=1024)
        .reproject(crs=target_projection)
    )
    population_per_cell = (
        population_image.rename("POPULATION")
        .reduceResolution(reducer=ee.Reducer.sum(), maxPixels=1024)
        .reproject(crs=target_projection)
    )
    aligned_metrics = (
        landsat_on_grid.addBands(land_cover_on_grid)
        .addBands(population_per_cell)
        .clip(region)
    )

    cells = aligned_metrics.sample(
        region=region,
        projection=target_projection,
        scale=config.grid_size_m,
        geometries=True,
        dropNulls=False,
        tileScale=4,
    )
    cell_count = int(cells.size().getInfo())
    if cell_count < 1:
        raise DataPipelineError(
            "Earth Engine returned no grid-cell samples for the selected area."
        )
    if cell_count > config.max_grid_cells:
        raise DataPipelineError(
            f"Earth Engine returned {cell_count:,} cells, exceeding "
            f"MAX_GRID_CELLS ({config.max_grid_cells:,})."
        )
    complete_cell_count = int(
        cells.filter(ee.Filter.notNull(list(OUTPUT_BANDS))).size().getInfo()
    )
    if complete_cell_count < 1:
        raise DataPipelineError(
            "No cells have complete NDVI, LST, land-cover, and population metrics."
        )
    return cells, cell_count, complete_cell_count


def prepare_inputs(
    config: ProjectConfig, *, offline: bool = False
) -> PreparedInputs:
    """Download aligned per-cell inputs or load a matching local cache."""
    config.validate_for_analysis()
    csv_path, metadata_path, cache_key = _cache_paths(config)
    if offline:
        return _read_cache(csv_path, metadata_path, cache_key)
    if not config.earth_engine_project:
        raise DataPipelineError(
            "Set EARTH_ENGINE_PROJECT to an Earth Engine-enabled Google Cloud "
            "project ID and authenticate locally with `earthengine authenticate`."
        )

    ee = _load_earth_engine()
    cells, cell_count, complete_cell_count = _prepare_earth_engine_collection(
        config, ee
    )
    download_url = cells.getDownloadURL(
        filetype="csv",
        selectors=[*OUTPUT_BANDS, ".geo"],
        filename=csv_path.stem,
    )
    with urlopen(download_url, timeout=300) as response:
        csv_content = response.read(MAX_DOWNLOAD_BYTES + 1)
    if len(csv_content) > MAX_DOWNLOAD_BYTES:
        raise DataPipelineError(
            "Prepared CSV exceeds the 32 MiB direct-download limit. Reduce the "
            "area or increase the grid size before retrying."
        )
    if not csv_content:
        raise DataPipelineError("Earth Engine returned an empty prepared-data file.")
    _validate_csv(csv_content)

    metadata = _metadata(config, cache_key, cell_count, complete_cell_count)
    _atomic_write(csv_path, csv_content)
    _atomic_write(
        metadata_path,
        json.dumps(metadata, indent=2, sort_keys=True).encode("utf-8"),
    )
    return PreparedInputs(
        csv_path=csv_path,
        metadata_path=metadata_path,
        cache_key=cache_key,
        cell_count=cell_count,
        complete_cell_count=complete_cell_count,
    )

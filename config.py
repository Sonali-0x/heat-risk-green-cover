"""Project settings and input-safety validation."""

import math
import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Mapping, Optional, Sequence, Tuple


PROJECT_ROOT = Path(__file__).resolve().parent
ALLOWED_CITIES = {"nagpur"}
ALLOWED_LANGUAGES = {"english", "hindi", "marathi"}
ALLOWED_INPUT_SUFFIXES = {
    ".csv",
    ".geojson",
    ".gpkg",
    ".json",
    ".shp",
    ".tif",
    ".tiff",
}
INDIA_BOUNDS = (68.1, 6.5, 97.5, 35.7)
MAX_ALLOWED_GRID_CELLS = 50_000
WORLDPOP_REFERENCE_YEAR = 2020


class ConfigurationError(ValueError):
    """Raised when project settings or input paths are invalid."""


def _parse_date(name: str, value: str) -> date:
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must use YYYY-MM-DD format.") from exc
    if parsed.isoformat() != value:
        raise ConfigurationError(f"{name} must use YYYY-MM-DD format.")
    return parsed


def validate_aoi_bounds(value: Sequence[float]) -> Tuple[float, float, float, float]:
    """Validate a west, south, east, north bounding box inside India."""
    if len(value) != 4:
        raise ConfigurationError("AOI bounds must contain west,south,east,north.")
    try:
        west, south, east, north = (float(coordinate) for coordinate in value)
    except (TypeError, ValueError) as exc:
        raise ConfigurationError("AOI bounds must contain four numeric coordinates.") from exc
    if not all(math.isfinite(coordinate) for coordinate in (west, south, east, north)):
        raise ConfigurationError("AOI bounds must contain finite coordinates.")
    if west >= east or south >= north:
        raise ConfigurationError("AOI bounds must have west < east and south < north.")
    india_west, india_south, india_east, india_north = INDIA_BOUNDS
    if (
        west < india_west
        or south < india_south
        or east > india_east
        or north > india_north
    ):
        raise ConfigurationError("AOI bounds must be within India's configured extent.")
    return west, south, east, north


def estimate_grid_cell_count(
    bounds: Sequence[float], grid_size_m: int
) -> int:
    """Estimate grid cells for a lon/lat rectangle using its midpoint latitude."""
    west, south, east, north = validate_aoi_bounds(bounds)
    if grid_size_m <= 0:
        raise ConfigurationError("GRID_SIZE_M must be a positive integer.")

    midpoint_latitude = math.radians((south + north) / 2)
    width_m = (east - west) * 111_320 * math.cos(midpoint_latitude)
    height_m = (north - south) * 110_574
    return math.ceil(width_m / grid_size_m) * math.ceil(height_m / grid_size_m)


def _project_path(value: str, name: str) -> Path:
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    resolved = candidate.resolve()
    if not resolved.is_relative_to(PROJECT_ROOT) or resolved == PROJECT_ROOT:
        raise ConfigurationError(f"{name} must be a directory inside the project.")
    return resolved


def _parse_bounds_setting(value: Optional[str]) -> Optional[Tuple[float, float, float, float]]:
    if value is None or not value.strip():
        return None
    return validate_aoi_bounds(value.split(","))


@dataclass(frozen=True)
class ProjectConfig:
    city: str
    start_date: date
    end_date: date
    aoi_bounds: Optional[Tuple[float, float, float, float]]
    grid_size_m: int
    max_grid_cells: int
    output_dir: Path
    site_dir: Path
    map_title: str
    report_language: str
    earth_engine_project: Optional[str]
    worldpop_year: int

    def validate_for_analysis(self) -> int:
        """Require an AOI and return its estimated cell count."""
        if self.aoi_bounds is None:
            raise ConfigurationError(
                "Set AOI_BOUNDS to west,south,east,north before running analysis."
            )
        estimated_cells = estimate_grid_cell_count(self.aoi_bounds, self.grid_size_m)
        if estimated_cells > self.max_grid_cells:
            raise ConfigurationError(
                f"AOI requires about {estimated_cells:,} cells, exceeding "
                f"MAX_GRID_CELLS ({self.max_grid_cells:,}). Increase GRID_SIZE_M "
                "or use a smaller city boundary."
            )
        return estimated_cells


def load_config(env: Optional[Mapping[str, str]] = None) -> ProjectConfig:
    """Load and validate settings from environment variables or .env."""
    if env is None:
        try:
            from dotenv import load_dotenv

            load_dotenv(PROJECT_ROOT / ".env")
        except ImportError:
            pass
        settings = os.environ
    else:
        settings = env


    city = settings.get("CITY", "Nagpur").strip()
    if city.casefold() not in ALLOWED_CITIES:
        raise ConfigurationError(
            f"Unsupported CITY {city!r}. Allowed cities: Nagpur."
        )

    start_date = _parse_date("START_DATE", settings.get("START_DATE", "2026-03-01"))
    end_date = _parse_date("END_DATE", settings.get("END_DATE", "2026-05-31"))
    if start_date > end_date:
        raise ConfigurationError("START_DATE must be on or before END_DATE.")

    try:
        grid_size_m = int(settings.get("GRID_SIZE_M", "100"))
        max_grid_cells = int(
            settings.get("MAX_GRID_CELLS", str(MAX_ALLOWED_GRID_CELLS))
        )
    except ValueError as exc:
        raise ConfigurationError(
            "GRID_SIZE_M and MAX_GRID_CELLS must be integers."
        ) from exc
    if grid_size_m < 10 or grid_size_m > 1_000:
        raise ConfigurationError("GRID_SIZE_M must be between 10 and 1000 metres.")
    if max_grid_cells < 1 or max_grid_cells > MAX_ALLOWED_GRID_CELLS:
        raise ConfigurationError(
            f"MAX_GRID_CELLS must be between 1 and {MAX_ALLOWED_GRID_CELLS:,}."
        )

    report_language = settings.get("REPORT_LANGUAGE", "english").strip().casefold()
    if report_language not in ALLOWED_LANGUAGES:
        allowed = ", ".join(sorted(ALLOWED_LANGUAGES))
        raise ConfigurationError(f"REPORT_LANGUAGE must be one of: {allowed}.")

    map_title = settings.get("MAP_TITLE", "Green Cover & Urban Heat Priority Map").strip()
    if not map_title:
        raise ConfigurationError("MAP_TITLE must not be empty.")

    return ProjectConfig(
        city="Nagpur",
        start_date=start_date,
        end_date=end_date,
        aoi_bounds=_parse_bounds_setting(settings.get("AOI_BOUNDS")),
        grid_size_m=grid_size_m,
        max_grid_cells=max_grid_cells,
        output_dir=_project_path(settings.get("OUTPUT_DIR", "outputs"), "OUTPUT_DIR"),
        site_dir=_project_path(settings.get("SITE_DIR", "site"), "SITE_DIR"),
        map_title=map_title,
        report_language=report_language,
        earth_engine_project=(
            settings.get("EARTH_ENGINE_PROJECT", "").strip()
            or settings.get("EE_PROJECT_ID", "").strip()
            or None
        ),
        worldpop_year=WORLDPOP_REFERENCE_YEAR,
    )


def validate_input_path(value: str, project_root: Path = PROJECT_ROOT) -> Path:
    """Return an existing supported input file located inside the project."""
    if not value.strip():
        raise ConfigurationError("Input path must not be empty.")

    root = project_root.resolve()
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = root / candidate

    try:
        resolved = candidate.resolve(strict=True)
    except FileNotFoundError as exc:
        raise ConfigurationError(f"Input file does not exist: {candidate}") from exc
    if not resolved.is_relative_to(root):
        raise ConfigurationError("Input files must be located inside the project directory.")
    if not resolved.is_file():
        raise ConfigurationError(f"Input path is not a file: {resolved}")
    if resolved.suffix.lower() not in ALLOWED_INPUT_SUFFIXES:
        supported = ", ".join(sorted(ALLOWED_INPUT_SUFFIXES))
        raise ConfigurationError(
            f"Unsupported input type. Supported extensions: {supported}"
        )
    return resolved

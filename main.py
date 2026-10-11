"""Entry point for the heat-risk and green-cover mapping pipeline."""

import argparse

from config import ConfigurationError, load_config, validate_input_path
from data_pipeline import DataPipelineError, prepare_inputs
from phase5 import OutputGenerationError, generate_outputs
from scoring import ScoringError, score_prepared_csv


def _load_project_config():
    return load_config()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run or validate the heat-risk and green-cover mapping pipeline."
    )
    parser.add_argument(
        "input",
        nargs="?",
        help="Path to a supported input file (CSV, GeoJSON, GeoPackage, shapefile, or GeoTIFF).",
    )
    parser.add_argument(
        "--prepare",
        action="store_true",
        help="Prepare aligned source metrics from Google Earth Engine.",
    )
    parser.add_argument(
        "--score",
        action="store_true",
        help="Score prepared metrics and generate the map, ranked CSV, and report.",
    )
    parser.add_argument(
        "--generate",
        action="store_true",
        help="Generate Phase 5 outputs from existing Phase 4 scored files.",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Load a prepared-data cache instead of contacting Earth Engine.",
    )
    args = parser.parse_args()

    selected_modes = sum((args.prepare, args.score, args.generate))
    if selected_modes > 1:
        parser.error("Use only one of --prepare, --score, or --generate.")
    if args.offline and not (args.prepare or args.score):
        parser.error("--offline can only be used with --prepare or --score.")

    try:
        config = _load_project_config()
        if args.generate:
            scored_dir = config.output_dir / "scored"
            generated = generate_outputs(
                scored_dir / "cell_priority_scores.csv",
                scored_dir / "top_priority_cells.csv",
                scored_dir / "scoring_metadata.json",
                config.output_dir,
                config,
            )
            print(f"Map: {generated.map_path}")
            print(f"Top cells: {generated.top_cells_path}")
            print(f"Action report: {generated.report_path}")
            print(f"Processing metadata: {generated.metadata_path}")
            return

        estimated_cells = config.validate_for_analysis()
        if args.prepare:
            prepared = prepare_inputs(config, offline=args.offline)
            print(
                f"Prepared {prepared.cell_count:,} cells; "
                f"{prepared.complete_cell_count:,} have complete metrics."
            )
            print(f"Metrics: {prepared.csv_path}")
            print(f"Metadata: {prepared.metadata_path}")
            return
        if args.score:
            if args.input:
                target_csv = validate_input_path(args.input)
                print(f"Using provided metrics input: {target_csv}")
            else:
                prepared = prepare_inputs(config, offline=args.offline)
                target_csv = prepared.csv_path
            result = score_prepared_csv(
                target_csv,
                config.output_dir / "scored",
                config,
            )
            print(
                f"Scored {result.cell_count:,} cells; "
                f"{result.priority_eligible_count:,} are eligible and "
                f"{result.top_cell_count:,} are in the top 10%."
            )
            print(f"All scores: {result.all_cells_path}")
            print(f"Scoring metadata: {result.metadata_path}")
            generated = generate_outputs(
                result.all_cells_path,
                result.top_cells_path,
                result.metadata_path,
                config.output_dir,
                config,
            )
            print(f"Map: {generated.map_path}")
            print(f"Top cells: {generated.top_cells_path}")
            print(f"Action report: {generated.report_path}")
            print(f"Processing metadata: {generated.metadata_path}")
            return
        if not args.input:
            parser.error("Provide an input file or use --prepare, --score, or --generate.")
        input_path = validate_input_path(args.input)
    except (
        ConfigurationError,
        DataPipelineError,
        OutputGenerationError,
        ScoringError,
    ) as exc:
        parser.error(str(exc))

    print(f"Input is safe to process: {input_path}")
    print(
        f"Configuration is valid for {config.city} "
        f"({config.start_date.isoformat()} to {config.end_date.isoformat()}, "
        f"about {estimated_cells:,} grid cells)."
    )
    if input_path.suffix.lower() == ".csv":
        print("To score this prepared CSV and generate map and report, run:")
        print(f"  python main.py {args.input} --score")
    else:
        print("Geospatial input validated successfully.")


if __name__ == "__main__":
    main()

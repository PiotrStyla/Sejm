"""Entry point for the Sejm Dataset Agent."""

import argparse
import logging
from pathlib import Path

from sejm_dataset_agent.pipeline import run_pipeline
from config.settings import load_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Sejm Dataset Agent")
    parser.add_argument(
        "--date",
        required=True,
        help="Date of the Sejm proceedings in ISO format (e.g., 2024-01-11).",
    )
    parser.add_argument(
        "--output",
        default="./datasets",
        help="Output directory for generated datasets.",
    )
    parser.add_argument(
        "--term",
        default="10",
        help="Sejm term number (default: 10).",
    )
    args = parser.parse_args()

    settings = load_settings()
    output_dir = Path(args.output) / args.date
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Starting Sejm Dataset Agent for date: %s", args.date)
    run_pipeline(
        date=args.date,
        term=args.term,
        output_dir=output_dir,
        settings=settings,
    )
    logger.info("Datasets written to: %s", output_dir)


if __name__ == "__main__":
    main()

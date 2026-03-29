"""CLI entry point for the Fragrantica-to-Parfumo migrator."""

import argparse
import sys

from migrator.exceptions import AuthenticationError, ScraperError, UnknownDataTypeError
from migrator.models import MigrationConfig
from migrator.migrator import Migrator, registry
from migrator.reporter import Reporter
from migrator.review_scraper import ReviewScraper
from migrator.review_submitter import ReviewSubmitter


def _register_plugins() -> None:
    """Register all built-in data type handlers."""
    registry.register("reviews", ReviewScraper, ReviewSubmitter)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fragrantica-migrator",
        description="Migrate your fragrance data from Fragrantica to Parfumo.",
    )
    parser.add_argument(
        "--profile-url",
        required=True,
        help="Fragrantica profile URL (e.g. https://www.fragrantica.com/member/12345)",
    )
    parser.add_argument(
        "--parfumo-user",
        required=True,
        help="Parfumo username",
    )
    parser.add_argument(
        "--parfumo-pass",
        required=True,
        help="Parfumo password",
    )
    parser.add_argument(
        "--data-type",
        default="reviews",
        help="Type of data to migrate (default: reviews)",
    )
    parser.add_argument(
        "--confidence",
        type=int,
        default=80,
        help="Fuzzy match confidence threshold 0-100 (default: 80)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional file path to write the migration report",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        default=False,
        help="Run the browser in headless mode",
    )
    return parser


def main(argv=None) -> None:
    _register_plugins()
    parser = _build_parser()
    args = parser.parse_args(argv)

    config = MigrationConfig(
        profile_url=args.profile_url,
        parfumo_username=args.parfumo_user,
        parfumo_password=args.parfumo_pass,
        data_type=args.data_type,
        confidence_threshold=args.confidence,
        output_path=args.output,
        headless=args.headless,
    )

    migrator = Migrator()
    reporter = Reporter()

    try:
        report = migrator.run(config)
    except UnknownDataTypeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    except AuthenticationError as exc:
        print(f"Authentication failed: {exc}", file=sys.stderr)
        sys.exit(1)
    except ScraperError as exc:
        print(f"Failed to scrape profile: {exc}", file=sys.stderr)
        sys.exit(1)

    reporter.output(report, output_path=config.output_path)


if __name__ == "__main__":
    main()

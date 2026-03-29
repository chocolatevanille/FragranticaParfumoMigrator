"""Unit tests for Reporter.

Tests:
- Report file is created at configured path
- Stdout output matches file content

Requirements: 5.3
"""

from __future__ import annotations

import io
import os
import tempfile
from unittest.mock import patch

import pytest

from migrator.models import (
    MigrationReport,
    ScrapedItem,
    SubmissionResult,
    SubmissionStatus,
)
from migrator.reporter import Reporter


def _make_item(name: str = "Shalimar", brand: str = "Guerlain") -> ScrapedItem:
    return ScrapedItem(fragrance_name=name, brand=brand, review_text="Great scent.")


def _make_report(
    results: list[SubmissionResult] | None = None,
) -> MigrationReport:
    results = results or []
    successful = sum(1 for r in results if r.status == SubmissionStatus.SUCCESS)
    skipped = sum(1 for r in results if r.status == SubmissionStatus.SKIPPED)
    failed = sum(1 for r in results if r.status == SubmissionStatus.FAILED)
    return MigrationReport(
        total_scraped=len(results),
        successful=successful,
        skipped=skipped,
        failed=failed,
        results=results,
    )


class TestReporterFileOutput:
    def test_file_is_created_at_configured_path(self, tmp_path):
        """Reporter creates a file at the given output_path."""
        report = _make_report()
        reporter = Reporter()
        output_file = tmp_path / "report.txt"

        buf = io.StringIO()
        with patch("sys.stdout", buf):
            reporter.output(report, output_path=str(output_file))

        assert output_file.exists(), "Report file was not created"

    def test_file_content_matches_stdout(self, tmp_path):
        """File content is identical to the formatted report string."""
        results = [
            SubmissionResult(item=_make_item(), status=SubmissionStatus.SUCCESS),
            SubmissionResult(
                item=_make_item("Light Blue", "Dolce & Gabbana"),
                status=SubmissionStatus.SKIPPED,
                reason="No match found",
            ),
            SubmissionResult(
                item=_make_item("Chanel No. 5", "Chanel"),
                status=SubmissionStatus.FAILED,
                reason="Submission error",
            ),
        ]
        report = _make_report(results)
        reporter = Reporter()
        output_file = tmp_path / "report.txt"

        buf = io.StringIO()
        with patch("sys.stdout", buf):
            reporter.output(report, output_path=str(output_file))

        file_content = output_file.read_text(encoding="utf-8")
        formatted = reporter._format(report)

        assert file_content == formatted
        assert formatted in buf.getvalue()

    def test_no_file_written_when_output_path_is_none(self, tmp_path):
        """No file is written when output_path is None."""
        report = _make_report()
        reporter = Reporter()

        buf = io.StringIO()
        with patch("sys.stdout", buf):
            reporter.output(report, output_path=None)

        # No files should have been created in tmp_path
        assert list(tmp_path.iterdir()) == []


class TestReporterFormat:
    def test_totals_appear_in_output(self):
        """Summary counts appear in the formatted output."""
        results = [
            SubmissionResult(item=_make_item(), status=SubmissionStatus.SUCCESS),
            SubmissionResult(
                item=_make_item("Rose", "Dior"),
                status=SubmissionStatus.SKIPPED,
                reason="Low confidence",
            ),
        ]
        report = _make_report(results)
        reporter = Reporter()
        formatted = reporter._format(report)

        assert "2" in formatted  # total_scraped
        assert "1" in formatted  # successful / skipped

    def test_skipped_item_details_in_output(self):
        """Skipped items include fragrance name, brand, and reason."""
        item = _make_item("Aventus", "Creed")
        result = SubmissionResult(
            item=item, status=SubmissionStatus.SKIPPED, reason="No autocomplete match"
        )
        report = _make_report([result])
        reporter = Reporter()
        formatted = reporter._format(report)

        assert "Aventus" in formatted
        assert "Creed" in formatted
        assert "No autocomplete match" in formatted

    def test_failed_item_details_in_output(self):
        """Failed items include fragrance name, brand, and reason."""
        item = _make_item("Oud Wood", "Tom Ford")
        result = SubmissionResult(
            item=item, status=SubmissionStatus.FAILED, reason="Submission error"
        )
        report = _make_report([result])
        reporter = Reporter()
        formatted = reporter._format(report)

        assert "Oud Wood" in formatted
        assert "Tom Ford" in formatted
        assert "Submission error" in formatted

    def test_successful_items_not_in_detail_section(self):
        """Successful items do not appear in the skipped/failed detail sections."""
        item = _make_item("Shalimar", "Guerlain")
        result = SubmissionResult(item=item, status=SubmissionStatus.SUCCESS)
        report = _make_report([result])
        reporter = Reporter()
        formatted = reporter._format(report)

        assert "--- Skipped ---" not in formatted
        assert "--- Failed ---" not in formatted

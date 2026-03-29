"""Reporter: formats and outputs MigrationReport to stdout and optionally a file."""

from __future__ import annotations

import sys
from typing import Optional

from migrator.models import MigrationReport, SubmissionStatus


class Reporter:
    """Formats a MigrationReport and writes it to stdout (and optionally a file)."""

    def output(self, report: MigrationReport, output_path: Optional[str] = None) -> None:
        """Format the report and print to stdout; also write to file if output_path is set.

        Credentials are never included in the output.

        Args:
            report: The MigrationReport to format and output.
            output_path: Optional file path to write the report to.
        """
        content = self._format(report)
        print(content)
        if output_path:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(content)

    def _format(self, report: MigrationReport) -> str:
        """Format a MigrationReport as a human-readable string.

        Args:
            report: The MigrationReport to format.

        Returns:
            Formatted report string.
        """
        lines: list[str] = []
        lines.append("=== Migration Report ===")
        lines.append(f"Total scraped : {report.total_scraped}")
        lines.append(f"Successful    : {report.successful}")
        lines.append(f"Skipped       : {report.skipped}")
        lines.append(f"Failed        : {report.failed}")

        skipped_results = [
            r for r in report.results if r.status == SubmissionStatus.SKIPPED
        ]
        failed_results = [
            r for r in report.results if r.status == SubmissionStatus.FAILED
        ]

        if skipped_results:
            lines.append("")
            lines.append("--- Skipped ---")
            for r in skipped_results:
                reason = r.reason or "no reason given"
                lines.append(
                    f"  {r.item.fragrance_name} by {r.item.brand} — {reason}"
                )

        if failed_results:
            lines.append("")
            lines.append("--- Failed ---")
            for r in failed_results:
                reason = r.reason or "no reason given"
                lines.append(
                    f"  {r.item.fragrance_name} by {r.item.brand} — {reason}"
                )

        return "\n".join(lines)

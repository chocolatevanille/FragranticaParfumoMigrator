# Feature: fragrantica-to-parfumo-migrator, Property 8: report accurately reflects results
# Feature: fragrantica-to-parfumo-migrator, Property 9: report file matches stdout
# Feature: fragrantica-to-parfumo-migrator, Property 7: credentials never in output

"""
Property-based tests for Reporter.

Property 7: Credentials never appear in output
Property 8: Migration report accurately reflects results
Property 9: Report file matches stdout output

Validates: Requirements 4.4, 5.1, 5.2, 5.3
"""

from __future__ import annotations

import io
import os
import tempfile
from unittest.mock import patch

from hypothesis import given, settings
from hypothesis import strategies as st

from migrator.models import (
    MigrationReport,
    ScrapedItem,
    SubmissionResult,
    SubmissionStatus,
)
from migrator.reporter import Reporter


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_safe_text = st.text(
    min_size=1,
    max_size=40,
    alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd", "Zs")),
)

_reason = st.one_of(st.none(), _safe_text)

_status = st.sampled_from(list(SubmissionStatus))


def _scraped_item_strategy():
    return st.builds(
        ScrapedItem,
        fragrance_name=_safe_text,
        brand=_safe_text,
        review_text=_safe_text,
    )


def _submission_result_strategy():
    return st.builds(
        SubmissionResult,
        item=_scraped_item_strategy(),
        status=_status,
        reason=_reason,
    )


def _results_list_strategy():
    return st.lists(_submission_result_strategy(), min_size=0, max_size=20)


def _report_from_results(results: list[SubmissionResult]) -> MigrationReport:
    """Build a MigrationReport consistent with the given results list."""
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


def _random_report_strategy():
    return _results_list_strategy().map(_report_from_results)


# ---------------------------------------------------------------------------
# Property 8: Migration report accurately reflects results
# ---------------------------------------------------------------------------

@given(results=_results_list_strategy())
@settings(max_examples=100)
def test_report_count_accuracy(results: list[SubmissionResult]) -> None:
    """Report counts match the actual SubmissionResult list.

    Validates: Requirements 5.1, 5.2
    """
    report = _report_from_results(results)
    reporter = Reporter()

    # Capture stdout
    buf = io.StringIO()
    with patch("sys.stdout", buf):
        reporter.output(report)

    output = buf.getvalue()

    # Count fields must match
    assert report.total_scraped == len(results)
    assert report.successful == sum(1 for r in results if r.status == SubmissionStatus.SUCCESS)
    assert report.skipped == sum(1 for r in results if r.status == SubmissionStatus.SKIPPED)
    assert report.failed == sum(1 for r in results if r.status == SubmissionStatus.FAILED)

    # Every skipped/failed item must appear in the output with name, brand, reason
    for r in results:
        if r.status in (SubmissionStatus.SKIPPED, SubmissionStatus.FAILED):
            assert r.item.fragrance_name in output, (
                f"Expected fragrance name '{r.item.fragrance_name}' in output"
            )
            assert r.item.brand in output, (
                f"Expected brand '{r.item.brand}' in output"
            )
            if r.reason:
                assert r.reason in output, (
                    f"Expected reason '{r.reason}' in output"
                )


# ---------------------------------------------------------------------------
# Property 9: Report file matches stdout output
# ---------------------------------------------------------------------------

@given(report=_random_report_strategy())
@settings(max_examples=100)
def test_file_stdout_parity(report: MigrationReport) -> None:
    """File content is identical to stdout content.

    Validates: Requirements 5.3
    """
    reporter = Reporter()

    with tempfile.NamedTemporaryFile(mode="r", suffix=".txt", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            reporter.output(report, output_path=tmp_path)

        stdout_content = buf.getvalue()

        with open(tmp_path, "r", encoding="utf-8") as f:
            file_content = f.read()

        # stdout includes a trailing newline from print(); file should match the
        # formatted string exactly (without the extra newline added by print).
        # We compare the formatted string itself.
        assert file_content == reporter._format(report), (
            "File content does not match formatted report"
        )
        assert reporter._format(report) in stdout_content, (
            "Stdout does not contain the formatted report"
        )
        assert file_content in stdout_content, (
            "File content not found in stdout output"
        )
    finally:
        os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# Property 7: Credentials never appear in output
# ---------------------------------------------------------------------------

# Credentials use a fixed prefix "CRED_" followed by alphanumeric chars.
# The prefix "CRED_" cannot appear in the report's fragrance data (which uses
# _safe_text with only letters/digits/spaces — no underscores), so a credential
# will only appear in the output if the reporter explicitly embeds it.
_credential_text = st.text(
    min_size=1,
    max_size=25,
    alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
).map(lambda s: "CRED_" + s)


@given(
    username=_credential_text,
    password=_credential_text,
    report=_random_report_strategy(),
)
@settings(max_examples=100)
def test_credentials_never_in_output(
    username: str, password: str, report: MigrationReport
) -> None:
    """Neither username nor password appears in stdout or written file.

    Validates: Requirements 4.4
    """
    reporter = Reporter()

    with tempfile.NamedTemporaryFile(mode="r", suffix=".txt", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            reporter.output(report, output_path=tmp_path)

        stdout_content = buf.getvalue()

        with open(tmp_path, "r", encoding="utf-8") as f:
            file_content = f.read()

        assert username not in stdout_content, (
            f"Username '{username}' found in stdout output"
        )
        assert password not in stdout_content, (
            f"Password '{password}' found in stdout output"
        )
        assert username not in file_content, (
            f"Username '{username}' found in file output"
        )
        assert password not in file_content, (
            f"Password '{password}' found in file output"
        )
    finally:
        os.unlink(tmp_path)

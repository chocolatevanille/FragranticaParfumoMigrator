"""Unit tests for ReviewSubmitter.

Validates: Requirements 2.5, 3.4, 3.5, 3.6
"""

import logging
from unittest.mock import MagicMock, patch, PropertyMock

import pytest
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support.ui import WebDriverWait

from migrator.models import ScrapedItem, SubmissionStatus
from migrator.review_submitter import ReviewSubmitter, _WAIT_TIMEOUT


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_item(
    fragrance_name: str = "Light Blue",
    brand: str = "Dolce & Gabbana",
    review_text: str = "A lovely fresh scent.",
) -> ScrapedItem:
    return ScrapedItem(
        fragrance_name=fragrance_name,
        brand=brand,
        review_text=review_text,
    )


def _make_submitter(threshold: int = 80) -> ReviewSubmitter:
    """Return a ReviewSubmitter with a fully mocked WebDriver."""
    driver = MagicMock()
    return ReviewSubmitter(driver=driver, confidence_threshold=threshold)


# ---------------------------------------------------------------------------
# Requirement 3.6 — WebDriverWait configured with 10-second timeout
# ---------------------------------------------------------------------------

def test_webdriverwait_timeout_is_ten_seconds() -> None:
    """WebDriverWait must be configured with a 10-second timeout.

    Validates: Requirements 3.6
    """
    assert _WAIT_TIMEOUT == 10

    submitter = _make_submitter()
    # The internal _wait attribute must be a WebDriverWait instance
    assert isinstance(submitter._wait, WebDriverWait)
    # WebDriverWait stores the timeout as _timeout
    assert submitter._wait._timeout == 10


# ---------------------------------------------------------------------------
# Requirement 2.5 — skip + warning when no candidate meets threshold
# ---------------------------------------------------------------------------

def test_skip_with_warning_when_no_candidate_meets_threshold(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """When all candidates score below the threshold, submit returns SKIPPED
    and logs a warning containing the fragrance name, brand, and best candidate.

    Validates: Requirements 2.5
    """
    submitter = _make_submitter(threshold=95)
    item = _make_item(fragrance_name="Light Blue", brand="Dolce & Gabbana")

    # Patch _search_autocomplete to return a low-scoring candidate
    low_score_candidate = ("Some Unrelated Fragrance Brand", "https://parfumo.de/x")
    submitter._search_autocomplete = MagicMock(return_value=[low_score_candidate])

    with caplog.at_level(logging.WARNING, logger="migrator.review_submitter"):
        result = submitter.submit(item)

    assert result.status == SubmissionStatus.SKIPPED
    assert result.reason is not None
    assert "95" in result.reason  # threshold mentioned
    assert "Some Unrelated Fragrance Brand" in result.reason  # best candidate mentioned

    # A warning must have been logged
    warning_messages = [r.message for r in caplog.records if r.levelno == logging.WARNING]
    assert any("Light Blue" in m for m in warning_messages)
    assert any("Dolce & Gabbana" in m for m in warning_messages)


def test_skip_when_no_autocomplete_suggestions(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """When autocomplete returns no suggestions, submit returns SKIPPED and warns.

    Validates: Requirements 2.5
    """
    submitter = _make_submitter()
    item = _make_item()

    submitter._search_autocomplete = MagicMock(return_value=[])

    with caplog.at_level(logging.WARNING, logger="migrator.review_submitter"):
        result = submitter.submit(item)

    assert result.status == SubmissionStatus.SKIPPED
    assert result.reason is not None

    warning_messages = [r.message for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warning_messages) >= 1


# ---------------------------------------------------------------------------
# Requirement 3.5 — SubmissionResult.FAILED on Parfumo error response
# ---------------------------------------------------------------------------

def test_failed_when_parfumo_modal_does_not_close(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """When the submit button stays visible after clicking (modal stays open),
    the result must be FAILED — indicating a Parfumo error response.

    Validates: Requirements 3.5
    """
    submitter = _make_submitter(threshold=0)
    item = _make_item()

    # Provide a high-scoring candidate so matching succeeds
    submitter._search_autocomplete = MagicMock(
        return_value=[("Light Blue Dolce Gabbana", "https://parfumo.de/lb")]
    )

    # Patch _verify_page to pass
    submitter._verify_page = MagicMock(return_value=True)

    # Simulate the WebDriverWait sequence inside _fill_and_submit_review:
    # 1. review panel button found & clickable → click succeeds
    # 2. textarea found → fill succeeds
    # 3. submit button found & clickable → click succeeds
    # 4. invisibility_of submit button → TimeoutException (modal stays open)
    mock_panel_btn = MagicMock()
    mock_textarea = MagicMock()
    mock_submit_btn = MagicMock()

    wait_side_effects = [
        mock_panel_btn,   # element_to_be_clickable(.pd_review_panel)
        mock_textarea,    # presence_of_element_located(textarea)
        mock_submit_btn,  # element_to_be_clickable(button.action_submit_review)
        TimeoutException(),  # invisibility_of submit button — modal stays open
    ]
    submitter._wait = MagicMock()
    submitter._wait.until.side_effect = wait_side_effects

    with caplog.at_level(logging.ERROR, logger="migrator.review_submitter"):
        result = submitter.submit(item)

    assert result.status == SubmissionStatus.FAILED
    assert result.reason is not None
    assert "modal" in result.reason.lower() or "confirm" in result.reason.lower()

    error_messages = [r.message for r in caplog.records if r.levelno == logging.ERROR]
    assert len(error_messages) >= 1


# ---------------------------------------------------------------------------
# Requirement 3.4 — SubmissionResult.SKIPPED when review textarea not found
# ---------------------------------------------------------------------------

def test_skipped_when_review_textarea_not_found(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """When the review textarea cannot be located, submit returns SKIPPED
    and logs an error with the fragrance name.

    Validates: Requirements 3.4
    """
    submitter = _make_submitter(threshold=0)
    item = _make_item(fragrance_name="Shalimar", brand="Guerlain")

    submitter._search_autocomplete = MagicMock(
        return_value=[("Shalimar Guerlain", "https://parfumo.de/shalimar")]
    )
    submitter._verify_page = MagicMock(return_value=True)

    mock_panel_btn = MagicMock()

    # 1. review panel button found → click succeeds
    # 2. textarea wait → TimeoutException (not found)
    wait_side_effects = [
        mock_panel_btn,      # element_to_be_clickable(.pd_review_panel)
        TimeoutException(),  # presence_of_element_located(textarea) — not found
    ]
    submitter._wait = MagicMock()
    submitter._wait.until.side_effect = wait_side_effects

    with caplog.at_level(logging.ERROR, logger="migrator.review_submitter"):
        result = submitter.submit(item)

    assert result.status == SubmissionStatus.SKIPPED
    assert result.reason is not None
    assert "textarea" in result.reason.lower()

    error_messages = [r.message for r in caplog.records if r.levelno == logging.ERROR]
    assert any("Shalimar" in m for m in error_messages)

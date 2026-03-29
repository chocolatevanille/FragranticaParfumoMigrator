# Feature: fragrantica-to-parfumo-migrator, Property 11: routing by length

"""
Property 11: Submission routing is determined solely by review text length.

For any ScrapedItem, ReviewSubmitter.submit routes exclusively by len(review_text):
  - >= 300 chars  → _fill_and_submit_review  → SUCCESS (or review-specific failure)
  - <= 140 chars  → _fill_and_submit_statement → SUCCESS (or statement-specific failure)
  - 141–299 chars → neither helper called     → SKIPPED with "incompatible length"

Validates: Requirements 7.1, 7.2, 7.3
"""

from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from migrator.models import ScrapedItem, SubmissionResult, SubmissionStatus
from migrator.review_submitter import ReviewSubmitter

# ---------------------------------------------------------------------------
# Strategies for each length zone
# ---------------------------------------------------------------------------

_ALPHABET = st.characters(whitelist_categories=("L", "N", "Zs"), min_codepoint=32)

_statement_text = st.text(alphabet=_ALPHABET, min_size=1, max_size=140)
_incompatible_text = st.text(alphabet=_ALPHABET, min_size=141, max_size=299)
_review_text = st.text(alphabet=_ALPHABET, min_size=300, max_size=400)


def _make_submitter() -> ReviewSubmitter:
    driver = MagicMock()
    submitter = ReviewSubmitter(driver=driver, confidence_threshold=0)
    # Bypass matching/navigation so routing is the only variable
    submitter._search_autocomplete = MagicMock(
        return_value=[("Some Fragrance", "", "https://parfumo.com/x")]
    )
    submitter._verify_page = MagicMock(return_value=True)
    submitter.driver.get = MagicMock()
    return submitter


def _make_item(text: str) -> ScrapedItem:
    return ScrapedItem(fragrance_name="Test", brand="Brand", review_text=text)


_success_result = SubmissionResult(
    item=_make_item("x"), status=SubmissionStatus.SUCCESS
)


# ---------------------------------------------------------------------------
# Property 11a: texts >= 300 chars → review path
# ---------------------------------------------------------------------------

@settings(max_examples=100)
@given(text=_review_text)
def test_routing_review_zone_calls_fill_and_submit_review(text: str) -> None:
    """Texts of 300+ chars must be routed to _fill_and_submit_review."""
    assert len(text) >= 300
    submitter = _make_submitter()
    item = _make_item(text)

    review_result = SubmissionResult(item=item, status=SubmissionStatus.SUCCESS)
    with (
        patch.object(submitter, "_fill_and_submit_review", return_value=review_result) as mock_review,
        patch.object(submitter, "_fill_and_submit_statement") as mock_statement,
    ):
        result = submitter.submit(item)

    mock_review.assert_called_once()
    mock_statement.assert_not_called()
    assert result.status == SubmissionStatus.SUCCESS


# ---------------------------------------------------------------------------
# Property 11b: texts <= 140 chars → statement path
# ---------------------------------------------------------------------------

@settings(max_examples=100)
@given(text=_statement_text)
def test_routing_statement_zone_calls_fill_and_submit_statement(text: str) -> None:
    """Texts of 140 chars or fewer must be routed to _fill_and_submit_statement."""
    assert len(text) <= 140
    submitter = _make_submitter()
    item = _make_item(text)

    statement_result = SubmissionResult(item=item, status=SubmissionStatus.SUCCESS)
    with (
        patch.object(submitter, "_fill_and_submit_statement", return_value=statement_result) as mock_statement,
        patch.object(submitter, "_fill_and_submit_review") as mock_review,
    ):
        result = submitter.submit(item)

    mock_statement.assert_called_once()
    mock_review.assert_not_called()
    assert result.status == SubmissionStatus.SUCCESS


# ---------------------------------------------------------------------------
# Property 11c: texts 141–299 chars → SKIPPED with "incompatible length"
# ---------------------------------------------------------------------------

@settings(max_examples=100)
@given(text=_incompatible_text)
def test_routing_incompatible_zone_returns_skipped(text: str) -> None:
    """Texts of 141–299 chars must be skipped with 'incompatible length' reason."""
    assert 141 <= len(text) <= 299
    submitter = _make_submitter()
    item = _make_item(text)

    with (
        patch.object(submitter, "_fill_and_submit_review") as mock_review,
        patch.object(submitter, "_fill_and_submit_statement") as mock_statement,
    ):
        result = submitter.submit(item)

    mock_review.assert_not_called()
    mock_statement.assert_not_called()
    assert result.status == SubmissionStatus.SKIPPED
    assert result.reason is not None
    assert "incompatible length" in result.reason

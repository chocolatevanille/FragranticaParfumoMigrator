# Feature: fragrantica-to-parfumo-migrator, Property 6: auth before any submission

"""
Property 6: Authentication is performed before any submission.

For any list of ScrapedItems (0–10 items), _authenticate is called exactly
once and always before any submit() call.

Validates: Requirements 4.2
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch, call

from hypothesis import given, settings
from hypothesis import strategies as st

from migrator.models import (
    MigrationConfig,
    ScrapedItem,
    SubmissionResult,
    SubmissionStatus,
)
from migrator.migrator import Migrator
from migrator.registry import PluginRegistry


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_text = st.text(min_size=1, max_size=30, alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd", "Zs")))

scraped_item_strategy = st.builds(
    ScrapedItem,
    fragrance_name=_text,
    brand=_text,
    review_text=_text,
)

items_list_strategy = st.lists(scraped_item_strategy, min_size=0, max_size=10)


# ---------------------------------------------------------------------------
# Property 6
# ---------------------------------------------------------------------------

@given(items=items_list_strategy)
@settings(max_examples=100)
def test_auth_before_any_submission(items: list[ScrapedItem]) -> None:
    """_authenticate is called exactly once and before any submit() call.

    Validates: Requirements 4.2
    """
    call_log: list[str] = []

    # Build a mock scraper class
    mock_scraper_instance = MagicMock()
    mock_scraper_instance.scrape.return_value = items
    MockScraperCls = MagicMock(return_value=mock_scraper_instance)

    # Build a mock submitter class that records calls in call_log
    def _submit(item: ScrapedItem) -> SubmissionResult:
        call_log.append("submit")
        return SubmissionResult(item=item, status=SubmissionStatus.SUCCESS)

    mock_submitter_instance = MagicMock()
    mock_submitter_instance.submit.side_effect = _submit
    MockSubmitterCls = MagicMock(return_value=mock_submitter_instance)

    # Build a registry with the mock handler
    reg = PluginRegistry()
    reg.register("reviews", MockScraperCls, MockSubmitterCls)

    config = MigrationConfig(
        profile_url="https://www.fragrantica.com/member/123",
        parfumo_username="testuser",
        parfumo_password="testpass",
        data_type="reviews",
    )

    migrator = Migrator(plugin_registry=reg)

    mock_driver = MagicMock()

    def _fake_authenticate(driver, username, password):
        call_log.append("authenticate")

    with (
        patch("migrator.migrator.create_driver", return_value=mock_driver),
        patch("migrator.migrator._authenticate", side_effect=_fake_authenticate),
    ):
        report = migrator.run(config)

    # _authenticate called exactly once
    auth_calls = [e for e in call_log if e == "authenticate"]
    assert len(auth_calls) == 1, f"Expected 1 auth call, got {len(auth_calls)}"

    # _authenticate called before any submit
    if call_log:
        first_auth_idx = call_log.index("authenticate")
        submit_indices = [i for i, e in enumerate(call_log) if e == "submit"]
        for idx in submit_indices:
            assert first_auth_idx < idx, (
                f"authenticate (pos {first_auth_idx}) must precede submit (pos {idx})"
            )

    # Report totals match item count
    assert report.total_scraped == len(items)
    assert report.successful == len(items)

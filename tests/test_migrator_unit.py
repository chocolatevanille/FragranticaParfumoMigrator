"""Unit tests for Migrator.

Tests:
- AuthenticationError halts run with no submissions attempted (Req 4.2)
- UnknownDataTypeError halts run before browser is created (Req 4.3, 6.3)
- Unexpected per-item exception is caught, item marked FAILED, run continues (Req 4.2)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch, call
import pytest

from migrator.exceptions import AuthenticationError, UnknownDataTypeError
from migrator.migrator import Migrator
from migrator.models import (
    MigrationConfig,
    ScrapedItem,
    SubmissionResult,
    SubmissionStatus,
)
from migrator.registry import PluginRegistry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(**kwargs) -> MigrationConfig:
    defaults = dict(
        profile_url="https://www.fragrantica.com/member/123",
        parfumo_username="user",
        parfumo_password="pass",
        data_type="reviews",
    )
    defaults.update(kwargs)
    return MigrationConfig(**defaults)


def _make_registry(scraper_cls=None, submitter_cls=None) -> PluginRegistry:
    reg = PluginRegistry()
    scraper_cls = scraper_cls or MagicMock()
    submitter_cls = submitter_cls or MagicMock()
    reg.register("reviews", scraper_cls, submitter_cls)
    return reg


def _item(name="Rose", brand="Acme") -> ScrapedItem:
    return ScrapedItem(fragrance_name=name, brand=brand, review_text="Nice.")


# ---------------------------------------------------------------------------
# Test: UnknownDataTypeError halts before browser is created
# ---------------------------------------------------------------------------

def test_unknown_data_type_raises_before_browser_created():
    """UnknownDataTypeError is raised before create_driver is ever called."""
    reg = PluginRegistry()  # empty — no handlers registered
    migrator = Migrator(plugin_registry=reg)
    config = _make_config(data_type="ratings")

    with patch("migrator.migrator.create_driver") as mock_create_driver:
        with pytest.raises(UnknownDataTypeError) as exc_info:
            migrator.run(config)

    mock_create_driver.assert_not_called()
    assert "ratings" in str(exc_info.value)


def test_unknown_data_type_error_message_lists_supported_types():
    """Error message includes all registered type names."""
    reg = PluginRegistry()
    reg.register("reviews", MagicMock(), MagicMock())
    reg.register("ratings", MagicMock(), MagicMock())
    migrator = Migrator(plugin_registry=reg)
    config = _make_config(data_type="wishlist")

    with patch("migrator.migrator.create_driver", return_value=MagicMock()):
        with pytest.raises(UnknownDataTypeError) as exc_info:
            migrator.run(config)

    msg = str(exc_info.value)
    assert "reviews" in msg
    assert "ratings" in msg


# ---------------------------------------------------------------------------
# Test: AuthenticationError halts run with no submissions attempted
# ---------------------------------------------------------------------------

def test_auth_error_halts_run_no_submissions():
    """When _authenticate raises AuthenticationError, submit is never called."""
    mock_submitter_instance = MagicMock()
    MockSubmitterCls = MagicMock(return_value=mock_submitter_instance)

    mock_scraper_instance = MagicMock()
    mock_scraper_instance.scrape.return_value = [_item(), _item()]
    MockScraperCls = MagicMock(return_value=mock_scraper_instance)

    reg = _make_registry(MockScraperCls, MockSubmitterCls)
    migrator = Migrator(plugin_registry=reg)
    mock_driver = MagicMock()

    with (
        patch("migrator.migrator.create_driver", return_value=mock_driver),
        patch(
            "migrator.migrator._authenticate",
            side_effect=AuthenticationError("bad credentials"),
        ),
        pytest.raises(AuthenticationError),
    ):
        migrator.run(_make_config())

    mock_submitter_instance.submit.assert_not_called()
    mock_driver.quit.assert_called_once()


def test_auth_error_propagates_to_caller():
    """AuthenticationError is re-raised to the caller."""
    reg = _make_registry()
    migrator = Migrator(plugin_registry=reg)

    with (
        patch("migrator.migrator.create_driver", return_value=MagicMock()),
        patch(
            "migrator.migrator._authenticate",
            side_effect=AuthenticationError("invalid credentials"),
        ),
        pytest.raises(AuthenticationError, match="invalid credentials"),
    ):
        migrator.run(_make_config())


# ---------------------------------------------------------------------------
# Test: driver.quit() is always called (even on error)
# ---------------------------------------------------------------------------

def test_driver_quit_called_on_auth_error():
    """driver.quit() is called in the finally block even when auth fails."""
    mock_driver = MagicMock()
    reg = _make_registry()
    migrator = Migrator(plugin_registry=reg)

    with (
        patch("migrator.migrator.create_driver", return_value=mock_driver),
        patch("migrator.migrator._authenticate", side_effect=AuthenticationError("x")),
        pytest.raises(AuthenticationError),
    ):
        migrator.run(_make_config())

    mock_driver.quit.assert_called_once()


# ---------------------------------------------------------------------------
# Test: unexpected per-item exception → item marked FAILED, run continues
# ---------------------------------------------------------------------------

def test_unexpected_submit_exception_marks_item_failed_and_continues():
    """An unexpected exception during submit marks that item FAILED and continues."""
    items = [_item("Rose", "Acme"), _item("Oud", "Niche"), _item("Iris", "Fancy")]

    mock_scraper_instance = MagicMock()
    mock_scraper_instance.scrape.return_value = items

    call_count = 0

    def _submit(item):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise RuntimeError("network blip")
        return SubmissionResult(item=item, status=SubmissionStatus.SUCCESS)

    mock_submitter_instance = MagicMock()
    mock_submitter_instance.submit.side_effect = _submit

    reg = _make_registry(
        MagicMock(return_value=mock_scraper_instance),
        MagicMock(return_value=mock_submitter_instance),
    )
    migrator = Migrator(plugin_registry=reg)

    with (
        patch("migrator.migrator.create_driver", return_value=MagicMock()),
        patch("migrator.migrator._authenticate"),
    ):
        report = migrator.run(_make_config())

    assert report.total_scraped == 3
    assert report.successful == 2
    assert report.failed == 1

    failed = [r for r in report.results if r.status == SubmissionStatus.FAILED]
    assert len(failed) == 1
    assert failed[0].item.fragrance_name == "Oud"
    assert "Unexpected exception" in (failed[0].reason or "")


# ---------------------------------------------------------------------------
# Test: successful run aggregates report correctly
# ---------------------------------------------------------------------------

def test_successful_run_report_totals():
    """A clean run with mixed results produces correct report totals."""
    items = [_item("A"), _item("B"), _item("C")]
    statuses = [SubmissionStatus.SUCCESS, SubmissionStatus.SKIPPED, SubmissionStatus.FAILED]

    mock_scraper_instance = MagicMock()
    mock_scraper_instance.scrape.return_value = items

    def _submit(item):
        idx = [i.fragrance_name for i in items].index(item.fragrance_name)
        return SubmissionResult(item=item, status=statuses[idx], reason="reason" if idx > 0 else None)

    mock_submitter_instance = MagicMock()
    mock_submitter_instance.submit.side_effect = _submit

    reg = _make_registry(
        MagicMock(return_value=mock_scraper_instance),
        MagicMock(return_value=mock_submitter_instance),
    )
    migrator = Migrator(plugin_registry=reg)

    with (
        patch("migrator.migrator.create_driver", return_value=MagicMock()),
        patch("migrator.migrator._authenticate"),
    ):
        report = migrator.run(_make_config())

    assert report.total_scraped == 3
    assert report.successful == 1
    assert report.skipped == 1
    assert report.failed == 1

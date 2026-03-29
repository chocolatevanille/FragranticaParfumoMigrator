"""Unit tests for ReviewScraper — scroll loop termination and navigation errors.

Validates: Requirements 1.2, 1.3
"""

from unittest.mock import MagicMock, patch, call

import pytest
from selenium.common.exceptions import WebDriverException

from migrator.exceptions import ScraperError
from migrator.review_scraper import ReviewScraper, _MAX_STABLE_ROUNDS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_scraper() -> ReviewScraper:
    return ReviewScraper(driver=MagicMock())


def _html_with_n_cards(n: int) -> str:
    cards = ""
    for i in range(n):
        cards += f"""
        <div class="group rounded-md">
          <a href="/perfume/Tom-Ford/Fragrance-{i}-123.html">
            <img alt="Fragrance {i} Tom Ford" />
          </a>
          <div class="group/lazy"><p>Review text {i}</p></div>
        </div>
        """
    return f"<html><body>{cards}</body></html>"


# ---------------------------------------------------------------------------
# Scroll loop tests
# ---------------------------------------------------------------------------

@patch("migrator.review_scraper.time.sleep")
def test_scroll_terminates_when_count_is_stable(mock_sleep: MagicMock) -> None:
    """Scroll loop exits after _MAX_STABLE_ROUNDS with no new cards.

    Validates: Requirements 1.2
    """
    scraper = _make_scraper()
    # Fixed HTML — count never increases, so stable_rounds increments each time.
    scraper.driver.page_source = _html_with_n_cards(3)

    scraper._scroll_until_stable()

    # First scroll: count goes 0→3 (growth, resets stable_rounds).
    # Next _MAX_STABLE_ROUNDS scrolls: count stays at 3 → loop exits.
    assert scraper.driver.execute_script.call_count == 1 + _MAX_STABLE_ROUNDS
    mock_sleep.assert_called()


@patch("migrator.review_scraper.time.sleep")
def test_scroll_terminates_after_growth_then_stable(mock_sleep: MagicMock) -> None:
    """Scroll loop resets stable counter when new cards appear, then exits.

    Validates: Requirements 1.2
    """
    scraper = _make_scraper()

    # Simulate: 0→2 cards (growth), 2→5 cards (growth), then stable for 3 rounds.
    # Total execute_script calls: 2 (growth) + 3 (stable) = 5
    html_sequence = [
        _html_with_n_cards(2),  # scroll 1: count grows 0→2, stable_rounds reset
        _html_with_n_cards(5),  # scroll 2: count grows 2→5, stable_rounds reset
        _html_with_n_cards(5),  # scroll 3: stable round 1
        _html_with_n_cards(5),  # scroll 4: stable round 2
        _html_with_n_cards(5),  # scroll 5: stable round 3 → exit
    ]
    type(scraper.driver).page_source = property(
        lambda self, _seq=iter(html_sequence): next(_seq)
    )

    scraper._scroll_until_stable()

    expected_calls = 2 + _MAX_STABLE_ROUNDS  # 2 growth scrolls + 3 stable
    assert scraper.driver.execute_script.call_count == expected_calls


# ---------------------------------------------------------------------------
# Navigation / ScraperError tests
# ---------------------------------------------------------------------------

def test_scraper_error_on_webdriver_exception() -> None:
    """ScraperError is raised when driver.get() throws WebDriverException.

    Validates: Requirements 1.3
    """
    scraper = _make_scraper()
    url = "https://www.fragrantica.com/member/99999"
    scraper.driver.get.side_effect = WebDriverException("connection refused")

    with pytest.raises(ScraperError) as exc_info:
        scraper.scrape(url)

    assert url in str(exc_info.value)


def test_scraper_error_on_error_page_title() -> None:
    """ScraperError is raised when the page title signals an error (e.g. 404).

    Validates: Requirements 1.3
    """
    scraper = _make_scraper()
    url = "https://www.fragrantica.com/member/00000"
    scraper.driver.get.return_value = None
    scraper.driver.title = "404 Not Found"
    scraper.driver.current_url = url

    with pytest.raises(ScraperError):
        scraper.scrape(url)


def test_scraper_error_on_unexpected_redirect() -> None:
    """ScraperError is raised when the browser is redirected off fragrantica.com.

    Validates: Requirements 1.3
    """
    scraper = _make_scraper()
    url = "https://www.fragrantica.com/member/123"
    scraper.driver.get.return_value = None
    scraper.driver.title = "Some Page"
    scraper.driver.current_url = "https://other-domain.com/something"

    with pytest.raises(ScraperError):
        scraper.scrape(url)

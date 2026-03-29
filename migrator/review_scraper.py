"""ReviewScraper: scrapes reviews from a Fragrantica profile page."""

import logging
import time

from bs4 import BeautifulSoup
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.remote.webdriver import WebDriver

from migrator.base_scraper import BaseScraper
from migrator.exceptions import ScraperError
from migrator.models import ScrapedItem

logger = logging.getLogger(__name__)

# CSS selectors for Fragrantica review cards — update here if the site changes.
_REVIEW_CARD_SELECTOR = "div.cell.fr-news-block"
_FRAGRANCE_NAME_SELECTOR = "span[itemprop='name']"
_BRAND_SELECTOR = "span[itemprop='brand']"
_REVIEW_TEXT_SELECTOR = "div.review-text, p.review-text, div[itemprop='reviewBody']"

# How long to wait (seconds) after each scroll before checking for new reviews.
_SCROLL_PAUSE = 1.5
# Maximum number of scroll attempts with no new reviews before giving up.
_MAX_STABLE_ROUNDS = 3


class ReviewScraper(BaseScraper):
    """Concrete BaseScraper that extracts reviews from a Fragrantica profile."""

    def __init__(self, driver: WebDriver) -> None:
        super().__init__(driver)

    def scrape(self, profile_url: str) -> list[ScrapedItem]:
        """Navigate to *profile_url*, scroll until all reviews are loaded, and
        return a list of :class:`ScrapedItem` objects.

        Raises:
            ScraperError: if the URL is unreachable or the page signals an error.
        """
        self._navigate(profile_url)
        self._scroll_until_stable()
        return self._parse(self.driver.page_source)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _navigate(self, url: str) -> None:
        """Load *url* in the driver and raise :class:`ScraperError` on failure."""
        try:
            self.driver.get(url)
        except WebDriverException as exc:
            raise ScraperError(
                f"Profile URL unreachable: '{url}'. Detail: {exc}"
            ) from exc

        # Selenium doesn't expose HTTP status codes directly; check for common
        # browser error page indicators instead.
        title = self.driver.title or ""
        current_url = self.driver.current_url or ""

        error_indicators = (
            "404",
            "not found",
            "page not found",
            "error",
            "cannot be reached",
            "site can't be reached",
            "err_",
        )
        title_lower = title.lower()
        if any(ind in title_lower for ind in error_indicators):
            raise ScraperError(
                f"Profile URL returned an error page: '{url}'. Page title: '{title}'"
            )

        # If the browser was redirected away from the requested domain it is
        # also a sign that the page does not exist.
        if url.startswith("https://www.fragrantica.com") and not current_url.startswith(
            "https://www.fragrantica.com"
        ):
            raise ScraperError(
                f"Unexpected redirect when loading '{url}'. "
                f"Landed on: '{current_url}'"
            )

    def _scroll_until_stable(self) -> None:
        """Scroll the page repeatedly until no new review cards appear."""
        stable_rounds = 0
        last_count = 0

        while stable_rounds < _MAX_STABLE_ROUNDS:
            # Scroll to the very bottom of the page.
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(_SCROLL_PAUSE)

            soup = BeautifulSoup(self.driver.page_source, "html.parser")
            current_count = len(soup.select(_REVIEW_CARD_SELECTOR))

            if current_count > last_count:
                logger.debug(
                    "Loaded %d review cards so far (was %d).",
                    current_count,
                    last_count,
                )
                last_count = current_count
                stable_rounds = 0
            else:
                stable_rounds += 1
                logger.debug(
                    "No new reviews after scroll (stable round %d/%d).",
                    stable_rounds,
                    _MAX_STABLE_ROUNDS,
                )

        logger.info("Finished scrolling. Total review cards found: %d.", last_count)

    def _parse(self, html: str) -> list[ScrapedItem]:
        """Parse *html* and return one :class:`ScrapedItem` per valid review card."""
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select(_REVIEW_CARD_SELECTOR)
        items: list[ScrapedItem] = []

        for idx, card in enumerate(cards):
            fragrance_name = self._extract_text(card, _FRAGRANCE_NAME_SELECTOR)
            brand = self._extract_text(card, _BRAND_SELECTOR)
            review_text = self._extract_text(card, _REVIEW_TEXT_SELECTOR)

            missing = [
                field
                for field, value in (
                    ("fragrance_name", fragrance_name),
                    ("brand", brand),
                    ("review_text", review_text),
                )
                if not value
            ]

            if missing:
                logger.warning(
                    "Skipping review card %d: missing field(s) %s. "
                    "Partial data — name=%r, brand=%r, text=%r.",
                    idx,
                    missing,
                    fragrance_name,
                    brand,
                    (review_text or "")[:80],
                )
                continue

            items.append(
                ScrapedItem(
                    fragrance_name=fragrance_name,  # type: ignore[arg-type]
                    brand=brand,  # type: ignore[arg-type]
                    review_text=review_text,  # type: ignore[arg-type]
                )
            )

        logger.info("Parsed %d valid review(s) from %d card(s).", len(items), len(cards))
        return items

    @staticmethod
    def _extract_text(card: BeautifulSoup, selector: str) -> str | None:
        """Return stripped text of the first element matching *selector*, or None."""
        element = card.select_one(selector)
        if element is None:
            return None
        text = element.get_text(strip=True)
        return text if text else None

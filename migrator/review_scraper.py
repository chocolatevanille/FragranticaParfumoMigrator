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
# The site uses a Vue.js/Tailwind stack; cards are identified by their rounded card class.
_REVIEW_CARD_SELECTOR = "div.group.rounded-md"
# Perfume thumbnail img: alt text is "{Fragrance Name} {Brand}" combined.
_PERFUME_IMG_SELECTOR = "a[href*='/perfume/'] img"
# Review body text lives inside a lazy-loaded prose container.
_REVIEW_TEXT_SELECTOR = "div.group\\/lazy p"

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
        """Parse *html* and return one :class:`ScrapedItem` per valid review card.

        The Fragrantica profile page uses a Vue.js/Tailwind layout where each
        review card is a ``div.group.rounded-md``.  The fragrance name and brand
        are encoded together in the ``alt`` attribute of the perfume thumbnail
        image (e.g. ``"Tuscan Leather Tom Ford"``).  The brand is also present
        as the second path segment of the perfume URL
        (``/perfume/{Brand-Slug}/{Name-id}.html``), which we use to split the
        combined alt text reliably.
        """
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select(_REVIEW_CARD_SELECTOR)
        items: list[ScrapedItem] = []

        for idx, card in enumerate(cards):
            img_el = card.select_one(_PERFUME_IMG_SELECTOR)
            text_el = card.select_one(_REVIEW_TEXT_SELECTOR)

            alt = img_el.get("alt", "").strip() if img_el else ""
            review_text = text_el.get_text(strip=True) if text_el else None

            # Derive brand from the URL slug so we can split the combined alt.
            # URL pattern: /perfume/{Brand-Slug}/{Name-id}.html
            fragrance_name: str | None = None
            brand: str | None = None
            if img_el:
                link = img_el.find_parent("a")
                href = link.get("href", "") if link else ""
                brand_slug = self._brand_from_href(href)
                if brand_slug and alt:
                    fragrance_name, brand = self._split_name_brand_from_alt(alt, brand_slug)
                elif alt:
                    fragrance_name = alt

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
    def _brand_from_href(href: str) -> str | None:
        """Extract the brand slug from a Fragrantica perfume URL.

        URL pattern: ``/perfume/{Brand-Slug}/{Name-id}.html``
        Returns the raw slug (e.g. ``"Dolce-Gabbana"``) so the caller can use
        it to locate the brand in the alt text.
        """
        try:
            parts = href.rstrip("/").split("/")
            perfume_idx = parts.index("perfume")
            return parts[perfume_idx + 1]
        except (ValueError, IndexError):
            return None

    @staticmethod
    def _split_name_brand_from_alt(alt: str, brand_slug: str) -> tuple[str | None, str | None]:
        """Split ``"{Fragrance Name} {Brand}"`` alt text using the URL brand slug.

        The slug (e.g. ``"Dolce-Gabbana"``) is normalised to lowercase
        alphanumeric tokens and matched against the trailing tokens of the
        normalised alt.  The brand is then taken verbatim from the original
        alt so that display forms like ``"Dolce&Gabbana"`` are preserved.

        Returns ``(fragrance_name, brand)`` or ``(None, None)`` on failure.
        """
        import re

        def _tokens(s: str) -> list[str]:
            """Split into lowercase alphanumeric tokens."""
            return re.findall(r"[a-z0-9]+", s.lower())

        slug_tokens = _tokens(brand_slug)
        alt_tokens = _tokens(alt)

        if len(alt_tokens) <= len(slug_tokens):
            return None, None

        # Check that the trailing tokens of the alt match the slug tokens.
        if alt_tokens[-len(slug_tokens):] != slug_tokens:
            return None, None

        # Now find the split point in the *original* alt words.
        # We need to figure out how many trailing *words* (space-separated)
        # of the alt correspond to the slug tokens.
        alt_words = alt.split()
        # Walk backwards through alt_words, accumulating tokens until we
        # have consumed exactly len(slug_tokens) tokens.
        consumed = 0
        brand_word_count = 0
        for word in reversed(alt_words):
            consumed += len(_tokens(word))
            brand_word_count += 1
            if consumed == len(slug_tokens):
                break
            if consumed > len(slug_tokens):
                # Mismatch — fall back
                return None, None

        if brand_word_count >= len(alt_words):
            return None, None

        fragrance_name = " ".join(alt_words[:-brand_word_count])
        brand = " ".join(alt_words[-brand_word_count:])
        return fragrance_name, brand

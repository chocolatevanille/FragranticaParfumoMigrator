"""ReviewSubmitter: submits scraped Fragrantica reviews to Parfumo."""

import logging
from typing import Optional

from selenium.common.exceptions import NoSuchElementException, TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from migrator.base_submitter import BaseSubmitter
from migrator.fuzzy import score_candidate, select_best
from migrator.models import ScrapedItem, SubmissionResult, SubmissionStatus

logger = logging.getLogger(__name__)

_WAIT_TIMEOUT = 10  # seconds


class ReviewSubmitter(BaseSubmitter):
    def __init__(self, driver: WebDriver, confidence_threshold: int) -> None:
        super().__init__(driver, confidence_threshold)
        self._wait = WebDriverWait(driver, _WAIT_TIMEOUT)

    def submit(self, item: ScrapedItem) -> SubmissionResult:
        """Find the fragrance on Parfumo and submit the review."""
        candidates = self._search_autocomplete(item.fragrance_name)
        if not candidates:
            logger.warning(
                "No autocomplete suggestions for '%s' by '%s'",
                item.fragrance_name,
                item.brand,
            )
            return SubmissionResult(
                item=item,
                status=SubmissionStatus.SKIPPED,
                reason="No autocomplete suggestions found",
            )

        scored = [
            (name, url, score_candidate(item.fragrance_name, item.brand, name))
            for name, url in candidates
        ]
        best_name, best_url, best_score = max(scored, key=lambda t: t[2])

        candidates_for_select = [(name, score) for name, _, score in scored]
        chosen_name = select_best(candidates_for_select, self.confidence_threshold)

        if chosen_name is None:
            logger.warning(
                "No candidate met threshold %d for '%s' by '%s'. Best: '%s' (%d)",
                self.confidence_threshold,
                item.fragrance_name,
                item.brand,
                best_name,
                best_score,
            )
            return SubmissionResult(
                item=item,
                status=SubmissionStatus.SKIPPED,
                reason=(
                    f"No candidate met confidence threshold {self.confidence_threshold}. "
                    f"Best: '{best_name}' ({best_score})"
                ),
            )

        # Navigate to the matched fragrance page
        chosen_url = next(url for name, url, _ in scored if name == chosen_name)
        try:
            self.driver.get(chosen_url)
        except WebDriverException as exc:
            logger.error("Failed to navigate to '%s': %s", chosen_url, exc)
            return SubmissionResult(
                item=item,
                status=SubmissionStatus.FAILED,
                reason=f"Navigation failed: {exc}",
            )

        # Verify displayed name/brand match expectations
        if not self._verify_page(item.fragrance_name, item.brand):
            logger.warning(
                "Page verification failed for '%s' by '%s' at %s",
                item.fragrance_name,
                item.brand,
                chosen_url,
            )
            return SubmissionResult(
                item=item,
                status=SubmissionStatus.SKIPPED,
                reason="Page name/brand did not match expected fragrance",
            )

        # Open the review panel and fill in the review
        return self._fill_and_submit_review(item, chosen_name)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _search_autocomplete(self, fragrance_name: str) -> list[tuple[str, str]]:
        """
        Type fragrance_name into the Parfumo live-search and collect suggestions.
        Returns a list of (display_name, url) tuples from .ls-perfume-item elements.
        """
        try:
            search_input = self._wait.until(
                EC.presence_of_element_located((By.ID, "s_top"))
            )
            search_input.clear()
            search_input.send_keys(fragrance_name)

            # Wait for at least one result to appear
            self._wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".ls-perfume-item"))
            )
        except TimeoutException:
            return []

        items = self.driver.find_elements(By.CSS_SELECTOR, ".ls-perfume-item")
        results: list[tuple[str, str]] = []
        for item in items:
            try:
                name = item.find_element(
                    By.CSS_SELECTOR, ".ls-perfume-info .name"
                ).text.strip()
                overlay = item.find_element(By.CSS_SELECTOR, ".ls-perfume-overlay")
                url = overlay.get_attribute("href") or ""
                if name and url:
                    results.append((name, url))
            except NoSuchElementException:
                continue
        return results

    def _verify_page(self, expected_name: str, expected_brand: str) -> bool:
        """
        Verify the loaded fragrance page matches the expected name and brand.
        Uses the same confidence_threshold for fuzzy comparison.
        """
        try:
            name_el = self._wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "h1.p_name_h1"))
            )
            displayed_name = name_el.text.strip()
            brand_el = name_el.find_element(
                By.CSS_SELECTOR, ".p_brand_name [itemprop='name']"
            )
            displayed_brand = brand_el.text.strip()
        except (TimeoutException, NoSuchElementException):
            return False

        name_score = score_candidate(expected_name, expected_brand, displayed_name)
        brand_score = score_candidate(expected_brand, "", displayed_brand)
        return name_score >= self.confidence_threshold or brand_score >= self.confidence_threshold

    def _fill_and_submit_review(
        self, item: ScrapedItem, matched_name: str
    ) -> SubmissionResult:
        """Click the Review panel button, fill the textarea, and submit."""
        # Click the "Review" panel trigger
        try:
            review_panel_btn = self._wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, ".pd_review_panel"))
            )
            review_panel_btn.click()
        except TimeoutException:
            logger.error(
                "Review panel button not found for '%s' by '%s'",
                item.fragrance_name,
                item.brand,
            )
            return SubmissionResult(
                item=item,
                status=SubmissionStatus.SKIPPED,
                reason="Review panel button not found on page",
            )

        # Wait for the review textarea inside the modal
        try:
            textarea = self._wait.until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "textarea.form_review_text")
                )
            )
            textarea.clear()
            textarea.send_keys(item.review_text)
        except TimeoutException:
            logger.error(
                "Review textarea not found for '%s' by '%s'",
                item.fragrance_name,
                item.brand,
            )
            return SubmissionResult(
                item=item,
                status=SubmissionStatus.SKIPPED,
                reason="Review textarea not found",
            )

        # Click the submit button
        try:
            submit_btn = self._wait.until(
                EC.element_to_be_clickable(
                    (By.CSS_SELECTOR, "button.action_submit_review")
                )
            )
            submit_btn.click()
        except TimeoutException:
            logger.error(
                "Submit button not found for '%s' by '%s'",
                item.fragrance_name,
                item.brand,
            )
            return SubmissionResult(
                item=item,
                status=SubmissionStatus.SKIPPED,
                reason="Submit button not found",
            )

        # Check for error response (modal stays open with an error, or page error)
        try:
            self._wait.until(
                EC.invisibility_of_element_located(
                    (By.CSS_SELECTOR, "button.action_submit_review")
                )
            )
        except TimeoutException:
            logger.error(
                "Review submission may have failed for '%s' by '%s' — modal did not close",
                item.fragrance_name,
                item.brand,
            )
            return SubmissionResult(
                item=item,
                status=SubmissionStatus.FAILED,
                reason="Parfumo did not confirm submission (modal stayed open)",
            )

        logger.info(
            "Review submitted for '%s' by '%s' (matched: '%s')",
            item.fragrance_name,
            item.brand,
            matched_name,
        )
        return SubmissionResult(item=item, status=SubmissionStatus.SUCCESS)

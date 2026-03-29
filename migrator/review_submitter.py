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
        """Find the fragrance on Parfumo and submit the review or statement."""
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
            (name, url, score_candidate(item.fragrance_name, item.brand, name, candidate_brand))
            for name, candidate_brand, url in candidates
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
        chosen_url = next(url for name, _, url in scored if name == chosen_name)
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

        # Route by review text length (Requirement 7)
        text_len = len(item.review_text)
        if text_len >= 300:
            return self._fill_and_submit_review(item, chosen_name)
        elif text_len <= 140:
            return self._fill_and_submit_statement(item)
        else:
            # 141–299 chars: incompatible with both formats
            logger.warning(
                "Skipping '%s' by '%s': review text is %d chars "
                "(incompatible length: too long for a Statement and too short for a Review)",
                item.fragrance_name,
                item.brand,
                text_len,
            )
            return SubmissionResult(
                item=item,
                status=SubmissionStatus.SKIPPED,
                reason="incompatible length: too long for a Statement and too short for a Review",
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _search_autocomplete(self, fragrance_name: str) -> list[tuple[str, str]]:
        """
        Type fragrance_name into the Parfumo live-search and collect suggestions.
        Returns a list of (display_name, url) tuples from .ls-perfume-item elements.
        """
        import time
        try:
            # Ensure we're on Parfumo before searching
            if "parfumo.com" not in self.driver.current_url:
                self.driver.get("https://www.parfumo.com")

            # Wait for any modal backdrop to disappear before interacting with the page
            try:
                WebDriverWait(self.driver, 5).until(
                    EC.invisibility_of_element_located((By.CSS_SELECTOR, "div.pm-backdrop"))
                )
            except TimeoutException:
                # Backdrop didn't disappear — try dismissing it via Escape key
                self.driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
                WebDriverWait(self.driver, 3).until(
                    EC.invisibility_of_element_located((By.CSS_SELECTOR, "div.pm-backdrop"))
                )

            search_input = self._wait.until(
                EC.element_to_be_clickable((By.ID, "s_top"))
            )

            # Clear any previous search — select-all + delete is more reliable than .clear()
            search_input.click()
            search_input.send_keys(Keys.CONTROL + "a")
            search_input.send_keys(Keys.DELETE)

            # Wait for livesearch to disappear (stale results gone) before typing
            try:
                WebDriverWait(self.driver, 2).until(
                    EC.invisibility_of_element_located((By.CSS_SELECTOR, ".ls-perfume-item"))
                )
            except TimeoutException:
                pass  # fine if it was already gone

            search_input.send_keys(fragrance_name)

            # Wait for fresh results to appear
            self._wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".ls-perfume-item"))
            )
            # Small pause to let all results render
            time.sleep(0.5)
        except TimeoutException:
            return []

        items = self.driver.find_elements(By.CSS_SELECTOR, ".ls-perfume-item")
        results: list[tuple[str, str, str]] = []
        for item in items:
            try:
                name_el = item.find_element(By.CSS_SELECTOR, ".ls-perfume-info .name")
                # Get only the direct text, excluding child span labels like "Eau de Toilette"
                name = self.driver.execute_script(
                    "return Array.from(arguments[0].childNodes)"
                    ".filter(n => n.nodeType === 3)"
                    ".map(n => n.textContent)"
                    ".join('').trim();",
                    name_el
                )
                if not name:
                    name = name_el.text.strip()
                try:
                    brand_el = item.find_element(By.CSS_SELECTOR, ".ls-perfume-info .brand")
                    candidate_brand = brand_el.text.strip()
                except NoSuchElementException:
                    candidate_brand = ""
                overlay = item.find_element(By.CSS_SELECTOR, ".ls-perfume-overlay")
                url = overlay.get_attribute("href") or ""
                if name and url:
                    results.append((name, candidate_brand, url))
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

    def _fill_and_submit_statement(self, item: ScrapedItem) -> SubmissionResult:
        """Click the Statement panel button, fill the textarea, and submit."""
        # Click the statement panel trigger to open the modal
        try:
            statement_panel_btn = self._wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, ".pd_statement_panel"))
            )
            statement_panel_btn.click()
        except TimeoutException:
            logger.error(
                "Statement panel button not found for '%s'",
                item.fragrance_name,
            )
            return SubmissionResult(
                item=item,
                status=SubmissionStatus.SKIPPED,
                reason="Statement panel button not found on page",
            )

        # Wait for the statement textarea
        try:
            textarea = self._wait.until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "textarea.form_statement_text")
                )
            )
            textarea.clear()
            textarea.send_keys(item.review_text)
            # NOTE: Statements have no title field — do not interact with any title input
        except TimeoutException:
            logger.error(
                "Statement textarea not found for '%s'",
                item.fragrance_name,
            )
            return SubmissionResult(
                item=item,
                status=SubmissionStatus.SKIPPED,
                reason="Statement textarea not found",
            )

        # Click the submit button
        try:
            submit_btn = self._wait.until(
                EC.element_to_be_clickable(
                    (By.CSS_SELECTOR, "button.action_submit_statement")
                )
            )
            submit_btn.click()
        except TimeoutException:
            logger.error(
                "Statement submit button not found for '%s'",
                item.fragrance_name,
            )
            return SubmissionResult(
                item=item,
                status=SubmissionStatus.SKIPPED,
                reason="Statement submit button not found",
            )

        # Wait for the submit button to disappear (modal closes on success)
        try:
            self._wait.until(
                EC.invisibility_of_element_located(
                    (By.CSS_SELECTOR, "button.action_submit_statement")
                )
            )
        except TimeoutException:
            logger.error(
                "Statement submission may have failed for '%s' by '%s' — modal did not close",
                item.fragrance_name,
                item.brand,
            )
            return SubmissionResult(
                item=item,
                status=SubmissionStatus.FAILED,
                reason="Parfumo did not confirm statement submission (modal stayed open)",
            )

        logger.info(
            "Statement submitted for '%s' by '%s'",
            item.fragrance_name,
            item.brand,
        )
        return SubmissionResult(item=item, status=SubmissionStatus.SUCCESS)

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

            # Fill the title field (required by Parfumo)
            try:
                title_field = self.driver.find_element(
                    By.CSS_SELECTOR, "input.form_review_title"
                )
                title_field.clear()
                title = item.review_title or item.fragrance_name
                title_field.send_keys(title[:200])  # Parfumo maxlength=200
            except NoSuchElementException:
                logger.warning(
                    "Review title field not found for '%s' — submitting without title",
                    item.fragrance_name,
                )
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

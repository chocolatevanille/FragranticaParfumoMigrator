"""Migrator orchestrator: drives the full migration run."""

from __future__ import annotations

import logging
import traceback

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from migrator.exceptions import AuthenticationError, UnknownDataTypeError
from migrator.models import (
    MigrationConfig,
    MigrationReport,
    ScrapedItem,
    SubmissionResult,
    SubmissionStatus,
)
from migrator.registry import PluginRegistry

logger = logging.getLogger(__name__)

_WAIT_TIMEOUT = 10
_PARFUMO_HOME = "https://www.parfumo.com"
_PARFUMO_LOGOUT = "https://www.parfumo.com/board/login.php?logout=1"

# Module-level registry; CLI registers handlers here.
registry = PluginRegistry()


def create_driver(headless: bool = False):
    """Thin wrapper around browser.create_driver; defined here so tests can patch it."""
    from migrator.browser import create_driver as _create  # noqa: PLC0415
    return _create(headless=headless)


def _authenticate(driver, username: str, password: str) -> None:
    """Authenticate with Parfumo, handling already-logged-in and remembered-user states.

    Args:
        driver: Selenium WebDriver instance.
        username: Parfumo username to log in as.
        password: Parfumo password.

    Raises:
        AuthenticationError: If login fails or times out.
    """
    wait = WebDriverWait(driver, _WAIT_TIMEOUT)

    driver.get(_PARFUMO_HOME)

    # Check if already logged in
    logged_in_els = driver.find_elements(By.CSS_SELECTOR, "div.icon-my-parfumo")
    if logged_in_els:
        # Extract current username from span.nick_name
        nick_els = driver.find_elements(By.CSS_SELECTOR, "span.nick_name")
        if nick_els:
            raw_text = nick_els[0].text.strip()
            # Strip dropdown arrow text — take first whitespace-separated token
            current_user = raw_text.split()[0] if raw_text else ""
        else:
            current_user = ""

        if current_user.lower() == username.lower():
            logger.debug("Already logged in as %s", username)
            return

        # Logged in as a different user — log out first
        logger.debug("Logged in as %s, logging out to switch to %s", current_user, username)
        driver.get(_PARFUMO_LOGOUT)

    # Confirm not-logged-in state: div#login-btn should be present
    login_btn_els = driver.find_elements(By.CSS_SELECTOR, "div#login-btn")
    if not login_btn_els:
        # Re-check: maybe logout redirected and we need to re-navigate
        driver.get(_PARFUMO_HOME)
        login_btn_els = driver.find_elements(By.CSS_SELECTOR, "div#login-btn")

    if not login_btn_els:
        raise AuthenticationError(
            "Parfumo authentication failed: could not find login button after logout"
        )

    # Click login button to open modal
    login_btn_els[0].click()

    # Wait for the login modal to appear
    wait.until(EC.presence_of_element_located(
        (By.CSS_SELECTOR, "div#pm-1.pm-login.pm--visible")
    ))

    # Scope all lookups to the live modal panel (#pm-1), not the hidden template copy
    modal = driver.find_element(By.CSS_SELECTOR, "div#pm-1.pm-login.pm--visible")

    # Check if a remembered user is shown inside the live modal
    remembered_els = modal.find_elements(By.CSS_SELECTOR, "div#login-remembered")
    remembered_visible = False
    if remembered_els:
        style = remembered_els[0].get_attribute("style") or ""
        remembered_visible = "display:none" not in style.replace(" ", "")

    if remembered_visible:
        # Read remembered username from the live modal
        remembered_name_els = modal.find_elements(By.CSS_SELECTOR, "div.text-lg.bold")
        remembered_name = remembered_name_els[0].text.strip() if remembered_name_els else ""

        if remembered_name.lower() == username.lower():
            # Correct user remembered — just enter password
            pwd_field = modal.find_element(By.CSS_SELECTOR, "input#password")
            pwd_field.clear()
            pwd_field.send_keys(password)
        else:
            # Different user remembered — click "Not you?" to show full form
            not_you_link = modal.find_element(By.CSS_SELECTOR, "a#login-not-you")
            not_you_link.click()
            _fill_username_password(driver, username, password)
    else:
        # Full username/password form is already shown
        _fill_username_password(driver, username, password)

    # Submit the form via the button inside the live modal
    submit_btn = modal.find_element(By.CSS_SELECTOR, "button[type='submit']")
    submit_btn.click()

    # Wait for successful login indicator
    try:
        wait.until(EC.presence_of_element_located(
            (By.CSS_SELECTOR, "div.icon-my-parfumo")
        ))
    except Exception:
        raise AuthenticationError(
            "Parfumo authentication failed: invalid credentials or unexpected page state"
        )

    logger.info("Successfully authenticated as %s", username)


def _fill_username_password(driver, username: str, password: str) -> None:
    """Fill in the full username + password form fields."""
    user_field = driver.find_element(By.CSS_SELECTOR, "input#username")
    user_field.clear()
    user_field.send_keys(username)

    pwd_field = driver.find_element(By.CSS_SELECTOR, "input#password")
    pwd_field.clear()
    pwd_field.send_keys(password)


class Migrator:
    """Orchestrates the full migration run."""

    def __init__(self, plugin_registry: PluginRegistry | None = None) -> None:
        self._registry = plugin_registry if plugin_registry is not None else registry

    def run(self, config: MigrationConfig) -> MigrationReport:
        """Execute the full migration pipeline.

        Args:
            config: Migration configuration.

        Returns:
            MigrationReport summarising the run.

        Raises:
            UnknownDataTypeError: If config.data_type is not registered.
            AuthenticationError: If Parfumo login fails.
        """
        # 1. Validate data_type before touching the browser
        scraper_cls, submitter_cls = self._registry.get(config.data_type)

        driver = create_driver(headless=config.headless)
        try:
            # 3. Authenticate
            _authenticate(driver, config.parfumo_username, config.parfumo_password)

            # 4. Instantiate scraper and submitter
            scraper = scraper_cls(driver)
            submitter = submitter_cls(driver, config.confidence_threshold)

            # 5. Scrape
            items: list[ScrapedItem] = scraper.scrape(config.profile_url)

            # 6. Submit each item
            results: list[SubmissionResult] = []
            for item in items:
                try:
                    result = submitter.submit(item)
                except Exception:
                    logger.error(
                        "Unexpected error submitting %s by %s:\n%s",
                        item.fragrance_name,
                        item.brand,
                        traceback.format_exc(),
                    )
                    result = SubmissionResult(
                        item=item,
                        status=SubmissionStatus.FAILED,
                        reason="Unexpected exception during submission",
                    )
                results.append(result)

            # 7. Aggregate into report
            return _build_report(results)

        finally:
            driver.quit()


def _build_report(results: list[SubmissionResult]) -> MigrationReport:
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

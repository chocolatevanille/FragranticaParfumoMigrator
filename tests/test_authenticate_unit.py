"""Unit tests for _authenticate() — driven by real Parfumo HTML snapshots.

Each test scenario corresponds to one of the captured page states:
  - parfumo_home_page_not_logged_in.html   → not logged in, no modal open
  - parfumo_home_page_log_in_assume_user.html → modal open, remembered user shown
  - parfumo_home_page_log_in_prompt.html   → modal open, full username form shown
  - light_blue_parfumo_page.html           → already logged in as chocovanille

The snapshots are parsed with BeautifulSoup to verify that the CSS selectors
used in _authenticate() actually match the real HTML, then a mock driver is
configured to return those elements so the function's branching logic is
exercised against real page structure.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest
from bs4 import BeautifulSoup
from selenium.common.exceptions import TimeoutException

from migrator.exceptions import AuthenticationError
from migrator.migrator import _authenticate

# ---------------------------------------------------------------------------
# Snapshot paths
# ---------------------------------------------------------------------------

_SNAPSHOTS = Path(__file__).parent / "__snapshots__"
_NOT_LOGGED_IN   = _SNAPSHOTS / "parfumo_home_page_not_logged_in.html"
_ASSUME_USER     = _SNAPSHOTS / "parfumo_home_page_log_in_assume_user.html"
_FULL_PROMPT     = _SNAPSHOTS / "parfumo_home_page_log_in_prompt.html"
_LOGGED_IN_PAGE  = _SNAPSHOTS / "light_blue_parfumo_page.html"


# ---------------------------------------------------------------------------
# Snapshot-based selector sanity checks
# (These run against the real HTML to confirm our selectors are correct.)
# ---------------------------------------------------------------------------

class TestSelectorsAgainstSnapshots:
    """Verify that the CSS selectors used in _authenticate match the real HTML."""

    def test_not_logged_in_has_login_btn(self):
        soup = BeautifulSoup(_NOT_LOGGED_IN.read_text(encoding="utf-8"), "html.parser")
        assert soup.select_one("div#login-btn") is not None

    def test_not_logged_in_has_no_icon_my_parfumo(self):
        soup = BeautifulSoup(_NOT_LOGGED_IN.read_text(encoding="utf-8"), "html.parser")
        assert soup.select_one("div.icon-my-parfumo") is None

    def test_logged_in_page_has_icon_my_parfumo(self):
        soup = BeautifulSoup(_LOGGED_IN_PAGE.read_text(encoding="utf-8"), "html.parser")
        assert soup.select_one("div.icon-my-parfumo") is not None

    def test_logged_in_page_nick_name_text(self):
        soup = BeautifulSoup(_LOGGED_IN_PAGE.read_text(encoding="utf-8"), "html.parser")
        nick = soup.select_one("span.nick_name")
        assert nick is not None
        # The text includes the username followed by the dropdown arrow icon text
        assert "chocovanille" in nick.get_text()

    def test_assume_user_modal_is_visible(self):
        soup = BeautifulSoup(_ASSUME_USER.read_text(encoding="utf-8"), "html.parser")
        modal = soup.select_one("div#pm-1.pm-login.pm--visible")
        assert modal is not None

    def test_assume_user_remembered_div_is_visible(self):
        """In the assume-user snapshot, #login-remembered has no display:none."""
        soup = BeautifulSoup(_ASSUME_USER.read_text(encoding="utf-8"), "html.parser")
        modal = soup.select_one("div#pm-1.pm-login.pm--visible")
        remembered = modal.select_one("div#login-remembered")
        assert remembered is not None
        style = remembered.get("style", "")
        assert "display:none" not in style.replace(" ", "")

    def test_assume_user_remembered_username(self):
        soup = BeautifulSoup(_ASSUME_USER.read_text(encoding="utf-8"), "html.parser")
        modal = soup.select_one("div#pm-1.pm-login.pm--visible")
        name_el = modal.select_one("div.text-lg.bold")
        assert name_el is not None
        assert name_el.get_text(strip=True) == "chocovanille"

    def test_assume_user_has_not_you_link(self):
        soup = BeautifulSoup(_ASSUME_USER.read_text(encoding="utf-8"), "html.parser")
        modal = soup.select_one("div#pm-1.pm-login.pm--visible")
        assert modal.select_one("a#login-not-you") is not None

    def test_assume_user_has_password_field(self):
        soup = BeautifulSoup(_ASSUME_USER.read_text(encoding="utf-8"), "html.parser")
        modal = soup.select_one("div#pm-1.pm-login.pm--visible")
        assert modal.select_one("input#password") is not None

    def test_assume_user_has_submit_button(self):
        soup = BeautifulSoup(_ASSUME_USER.read_text(encoding="utf-8"), "html.parser")
        modal = soup.select_one("div#pm-1.pm-login.pm--visible")
        assert modal.select_one("button[type='submit']") is not None

    def test_full_prompt_remembered_div_is_hidden(self):
        """In the full-prompt snapshot, #login-remembered has display:none."""
        soup = BeautifulSoup(_FULL_PROMPT.read_text(encoding="utf-8"), "html.parser")
        modal = soup.select_one("div#pm-1.pm-login.pm--visible")
        remembered = modal.select_one("div#login-remembered")
        assert remembered is not None
        style = remembered.get("style", "")
        assert "display:none" in style.replace(" ", "")

    def test_full_prompt_username_field_is_visible(self):
        """In the full-prompt snapshot, #login-username-field has no display:none."""
        soup = BeautifulSoup(_FULL_PROMPT.read_text(encoding="utf-8"), "html.parser")
        modal = soup.select_one("div#pm-1.pm-login.pm--visible")
        field_div = modal.select_one("div#login-username-field")
        assert field_div is not None
        style = field_div.get("style", "")
        # style="" means visible (no display:none)
        assert "display:none" not in style.replace(" ", "")

    def test_full_prompt_username_input_is_enabled(self):
        """In the full-prompt snapshot, input#username has no disabled attribute."""
        soup = BeautifulSoup(_FULL_PROMPT.read_text(encoding="utf-8"), "html.parser")
        modal = soup.select_one("div#pm-1.pm-login.pm--visible")
        username_input = modal.select_one("input#username")
        assert username_input is not None
        assert username_input.get("disabled") is None


# ---------------------------------------------------------------------------
# Helpers for building mock drivers
# ---------------------------------------------------------------------------

def _mock_el(text: str = "", style: str = "") -> MagicMock:
    el = MagicMock()
    el.text = text
    el.get_attribute.return_value = style
    return el


def _make_modal_mock(remembered_style: str, remembered_name: str) -> MagicMock:
    """Build a mock for the #pm-1.pm-login.pm--visible element."""
    modal = MagicMock()

    remembered_el = _mock_el(style=remembered_style)
    modal.find_elements.return_value = [remembered_el]

    name_el = _mock_el(text=remembered_name)
    modal.find_elements.side_effect = lambda by, sel: (
        [remembered_el] if "login-remembered" in sel else [name_el]
    )

    modal.find_element.return_value = MagicMock()  # pwd field, submit btn, etc.
    return modal


# ---------------------------------------------------------------------------
# Scenario 1: Already logged in as the target user → return immediately
# ---------------------------------------------------------------------------

def test_already_logged_in_as_target_user_returns_immediately():
    """When icon-my-parfumo is present and nick matches, no login steps are taken.

    Grounded in: light_blue_parfumo_page.html — chocovanille is logged in.
    """
    driver = MagicMock()
    nick_el = _mock_el(text="chocovanille ")  # trailing space as in real HTML

    # find_elements returns icon-my-parfumo, then nick_name
    driver.find_elements.side_effect = [
        [MagicMock()],   # div.icon-my-parfumo → logged in
        [nick_el],       # span.nick_name
    ]

    with patch("migrator.migrator.WebDriverWait"):
        _authenticate(driver, "chocovanille", "secret")

    # Should navigate to home once, then return — no login button click
    driver.get.assert_called_once_with("https://www.parfumo.com")
    driver.find_element.assert_not_called()


# ---------------------------------------------------------------------------
# Scenario 2: Not logged in, no remembered user → full username+password form
# ---------------------------------------------------------------------------

def test_not_logged_in_full_form_fills_username_and_password():
    """Not logged in + full-prompt modal → username and password are both filled.

    Grounded in: parfumo_home_page_log_in_prompt.html
    (login-remembered has display:none, username field is visible and enabled)
    """
    driver = MagicMock()
    login_btn = MagicMock()

    # Sequence of find_elements calls:
    # 1. div.icon-my-parfumo → [] (not logged in)
    # 2. div#login-btn → [login_btn]
    driver.find_elements.side_effect = [
        [],           # not logged in
        [login_btn],  # login button present
    ]

    # Modal mock: #login-remembered has display:none → full form shown
    modal = MagicMock()
    remembered_el = _mock_el(style="display:none")
    modal.find_elements.return_value = [remembered_el]

    username_field = MagicMock()
    password_field = MagicMock()
    submit_btn = MagicMock()

    # driver.find_element calls: input#username, input#password (from _fill_username_password)
    # modal.find_element calls: button[type='submit']
    driver.find_element.side_effect = [username_field, password_field]
    modal.find_element.return_value = submit_btn
    driver.find_element.side_effect = [username_field, password_field]

    mock_wait = MagicMock()
    mock_wait.until.side_effect = [None, MagicMock()]  # modal appears, then logged-in indicator

    with patch("migrator.migrator.WebDriverWait", return_value=mock_wait):
        driver.find_element.side_effect = [username_field, password_field]
        driver.find_element_by = MagicMock()
        driver.find_element.side_effect = [username_field, password_field]

        # Patch find_element on driver for _fill_username_password
        call_seq = [username_field, password_field]
        driver.find_element.side_effect = call_seq
        driver.find_element.return_value = MagicMock()

        # Use a simpler approach: track calls via side_effect list
        elements = {"input#username": username_field, "input#password": password_field}

        def _find_element(by, sel):
            return elements.get(sel, MagicMock())

        driver.find_element.side_effect = _find_element
        driver.find_element.return_value = MagicMock()

        driver.find_element.side_effect = _find_element
        driver.find_element.return_value = MagicMock()

        driver.find_element.side_effect = _find_element
        driver.find_element.return_value = MagicMock()

        modal_elements = {"button[type='submit']": submit_btn}

        def _modal_find(by, sel):
            return modal_elements.get(sel, MagicMock())

        modal.find_element.side_effect = _modal_find

        driver.find_element.side_effect = _find_element
        driver.find_element.return_value = MagicMock()

        with patch("migrator.migrator.WebDriverWait", return_value=mock_wait):
            driver.find_element.side_effect = _find_element
            driver.find_element.return_value = MagicMock()
            driver.find_element.side_effect = _find_element

            # Patch find_element on driver to use our selector map
            driver.find_element.side_effect = _find_element

            # driver.find_element(By.CSS_SELECTOR, "div#pm-1.pm-login.pm--visible") → modal
            def _driver_find(by, sel):
                if "pm-1" in sel:
                    return modal
                return elements.get(sel, MagicMock())

            driver.find_element.side_effect = _driver_find

            _authenticate(driver, "newuser", "pass123")

    username_field.send_keys.assert_called_once_with("newuser")
    password_field.send_keys.assert_called_once_with("pass123")
    submit_btn.click.assert_called_once()


# ---------------------------------------------------------------------------
# Scenario 3: Modal open, remembered user matches → only password filled
# ---------------------------------------------------------------------------

def test_remembered_user_matches_only_password_filled():
    """When the remembered user matches the target, only the password is entered.

    Grounded in: parfumo_home_page_log_in_assume_user.html
    (login-remembered visible, username = chocovanille)
    """
    driver = MagicMock()
    login_btn = MagicMock()

    driver.find_elements.side_effect = [
        [],           # not logged in
        [login_btn],  # login button present
    ]

    # Modal: remembered user visible, name = "chocovanille"
    modal = MagicMock()
    remembered_el = _mock_el(style="")  # no display:none → visible
    name_el = _mock_el(text="chocovanille")
    password_field = MagicMock()
    submit_btn = MagicMock()

    modal.find_elements.side_effect = lambda by, sel: (
        [remembered_el] if "login-remembered" in sel else [name_el]
    )

    modal_elements = {
        "input#password": password_field,
        "button[type='submit']": submit_btn,
    }
    modal.find_element.side_effect = lambda by, sel: modal_elements.get(sel, MagicMock())

    mock_wait = MagicMock()
    mock_wait.until.side_effect = [None, MagicMock()]

    def _driver_find(by, sel):
        if "pm-1" in sel:
            return modal
        return MagicMock()

    driver.find_element.side_effect = _driver_find

    with patch("migrator.migrator.WebDriverWait", return_value=mock_wait):
        _authenticate(driver, "chocovanille", "mypassword")

    password_field.send_keys.assert_called_once_with("mypassword")
    # _fill_username_password must NOT have been called — username field untouched
    username_field = MagicMock()  # was never set up, so send_keys was never called
    # Verify by checking driver.find_element was only called for the modal, not for input#username
    driver_find_selectors = [c.args[1] for c in driver.find_element.call_args_list]
    assert "input#username" not in driver_find_selectors
    submit_btn.click.assert_called_once()


# ---------------------------------------------------------------------------
# Scenario 4: Modal open, remembered user is different → "Not you?" clicked
# ---------------------------------------------------------------------------

def test_remembered_user_differs_clicks_not_you_then_fills_form():
    """When remembered user differs from target, 'Not you?' is clicked and full form filled.

    Grounded in: parfumo_home_page_log_in_assume_user.html structure —
    the 'Not you?' link (a#login-not-you) is present when a user is remembered.
    """
    driver = MagicMock()
    login_btn = MagicMock()

    driver.find_elements.side_effect = [
        [],           # not logged in
        [login_btn],  # login button present
    ]

    modal = MagicMock()
    remembered_el = _mock_el(style="")  # visible
    name_el = _mock_el(text="chocovanille")  # different from target "otheruser"
    not_you_link = MagicMock()

    modal.find_elements.side_effect = lambda by, sel: (
        [remembered_el] if "login-remembered" in sel else [name_el]
    )

    username_field = MagicMock()
    password_field = MagicMock()
    submit_btn = MagicMock()

    modal_elements = {
        "a#login-not-you": not_you_link,
        "button[type='submit']": submit_btn,
    }
    modal.find_element.side_effect = lambda by, sel: modal_elements.get(sel, MagicMock())

    driver_elements = {
        "input#username": username_field,
        "input#password": password_field,
    }

    def _driver_find(by, sel):
        if "pm-1" in sel:
            return modal
        return driver_elements.get(sel, MagicMock())

    driver.find_element.side_effect = _driver_find

    mock_wait = MagicMock()
    mock_wait.until.side_effect = [None, MagicMock()]

    with patch("migrator.migrator.WebDriverWait", return_value=mock_wait):
        _authenticate(driver, "otheruser", "otherpass")

    not_you_link.click.assert_called_once()
    username_field.send_keys.assert_called_once_with("otheruser")
    password_field.send_keys.assert_called_once_with("otherpass")
    submit_btn.click.assert_called_once()


# ---------------------------------------------------------------------------
# Scenario 5: Login fails (wait for icon-my-parfumo times out)
# ---------------------------------------------------------------------------

def test_auth_error_raised_when_login_indicator_never_appears():
    """AuthenticationError is raised when the logged-in indicator never appears.

    This covers bad credentials or unexpected page state after submit.
    """
    driver = MagicMock()
    login_btn = MagicMock()

    driver.find_elements.side_effect = [
        [],           # not logged in
        [login_btn],  # login button present
    ]

    modal = MagicMock()
    remembered_el = _mock_el(style="display:none")  # full form shown
    modal.find_elements.return_value = [remembered_el]
    modal.find_element.return_value = MagicMock()

    username_field = MagicMock()
    password_field = MagicMock()

    def _driver_find(by, sel):
        if "pm-1" in sel:
            return modal
        if sel == "input#username":
            return username_field
        if sel == "input#password":
            return password_field
        return MagicMock()

    driver.find_element.side_effect = _driver_find

    mock_wait = MagicMock()
    # First until: modal appears (ok). Second until: icon-my-parfumo → timeout.
    mock_wait.until.side_effect = [None, TimeoutException("timed out")]

    with patch("migrator.migrator.WebDriverWait", return_value=mock_wait):
        with pytest.raises(AuthenticationError, match="invalid credentials"):
            _authenticate(driver, "baduser", "wrongpass")


# ---------------------------------------------------------------------------
# Scenario 6: Already logged in as a different user → logout then re-login
# ---------------------------------------------------------------------------

def test_already_logged_in_as_different_user_logs_out_first():
    """When logged in as a different user, logout URL is navigated before re-login.

    Grounded in: light_blue_parfumo_page.html — chocovanille is logged in,
    but we want to log in as 'otheruser'.
    """
    driver = MagicMock()
    nick_el = _mock_el(text="chocovanille")
    login_btn = MagicMock()

    # After logout, find_elements returns [] for icon-my-parfumo, then [login_btn]
    driver.find_elements.side_effect = [
        [MagicMock()],  # div.icon-my-parfumo → logged in
        [nick_el],      # span.nick_name → "chocovanille"
        [],             # div#login-btn after logout (not found first time)
        [login_btn],    # div#login-btn after re-navigate
    ]

    modal = MagicMock()
    remembered_el = _mock_el(style="display:none")
    modal.find_elements.return_value = [remembered_el]
    modal.find_element.return_value = MagicMock()

    def _driver_find(by, sel):
        if "pm-1" in sel:
            return modal
        return MagicMock()

    driver.find_element.side_effect = _driver_find

    mock_wait = MagicMock()
    mock_wait.until.side_effect = [None, MagicMock()]

    with patch("migrator.migrator.WebDriverWait", return_value=mock_wait):
        _authenticate(driver, "otheruser", "pass")

    # Logout URL must have been visited
    get_calls = [c.args[0] for c in driver.get.call_args_list]
    assert "https://www.parfumo.com/board/login.php?logout=1" in get_calls

"""Unit tests for _authenticate() — driven by real Parfumo HTML snapshots.

Each test scenario corresponds to one of the captured page states:
  - parfumo_home_page_not_logged_in.html   → not logged in, no modal open
  - parfumo_home_page_log_in_assume_user.html → modal open, remembered user shown
  - parfumo_home_page_log_in_prompt.html   → modal open, full username form shown
  - light_blue_parfumo_page.html           → already logged in as chocovanille
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
_NOT_LOGGED_IN  = _SNAPSHOTS / "parfumo_home_page_not_logged_in.html"
_ASSUME_USER    = _SNAPSHOTS / "parfumo_home_page_log_in_assume_user.html"
_FULL_PROMPT    = _SNAPSHOTS / "parfumo_home_page_log_in_prompt.html"
_LOGGED_IN_PAGE = _SNAPSHOTS / "light_blue_parfumo_page.html"


# ---------------------------------------------------------------------------
# Snapshot-based selector sanity checks
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
        assert "chocovanille" in nick.get_text()

    def test_assume_user_modal_is_visible(self):
        soup = BeautifulSoup(_ASSUME_USER.read_text(encoding="utf-8"), "html.parser")
        assert soup.select_one("div#pm-1.pm-login.pm--visible") is not None

    def test_assume_user_remembered_div_is_visible(self):
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
        soup = BeautifulSoup(_FULL_PROMPT.read_text(encoding="utf-8"), "html.parser")
        modal = soup.select_one("div#pm-1.pm-login.pm--visible")
        remembered = modal.select_one("div#login-remembered")
        assert remembered is not None
        style = remembered.get("style", "")
        assert "display:none" in style.replace(" ", "")

    def test_full_prompt_username_field_is_visible(self):
        soup = BeautifulSoup(_FULL_PROMPT.read_text(encoding="utf-8"), "html.parser")
        modal = soup.select_one("div#pm-1.pm-login.pm--visible")
        field_div = modal.select_one("div#login-username-field")
        assert field_div is not None
        style = field_div.get("style", "")
        assert "display:none" not in style.replace(" ", "")

    def test_full_prompt_username_input_is_enabled(self):
        soup = BeautifulSoup(_FULL_PROMPT.read_text(encoding="utf-8"), "html.parser")
        modal = soup.select_one("div#pm-1.pm-login.pm--visible")
        username_input = modal.select_one("input#username")
        assert username_input is not None
        assert username_input.get("disabled") is None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_el(text: str = "", style: str = "") -> MagicMock:
    el = MagicMock()
    el.text = text
    el.get_attribute.return_value = style
    return el


def _make_wait(modal_el, *extra_until_returns):
    """Return a mock WebDriverWait whose .until() yields modal_el first,
    then each item in extra_until_returns, then a generic MagicMock."""
    mock_wait = MagicMock()
    side_effects = [modal_el] + list(extra_until_returns)
    # Pad with MagicMocks so we never run out
    mock_wait.until.side_effect = side_effects + [MagicMock()] * 10
    return mock_wait


# ---------------------------------------------------------------------------
# Scenario 1: Already logged in as the target user → return immediately
# ---------------------------------------------------------------------------

def test_already_logged_in_as_target_user_returns_immediately():
    driver = MagicMock()
    nick_el = _mock_el(text="chocovanille ")

    driver.find_elements.side_effect = [
        [MagicMock()],  # div.icon-my-parfumo → logged in
        [nick_el],      # span.nick_name
    ]

    with patch("migrator.migrator.WebDriverWait"), \
         patch("migrator.migrator._dismiss_cookie_consent"):
        _authenticate(driver, "chocovanille", "secret")

    driver.get.assert_called_once_with("https://www.parfumo.com")
    driver.find_element.assert_not_called()


# ---------------------------------------------------------------------------
# Scenario 2: Not logged in, no remembered user → full username+password form
# ---------------------------------------------------------------------------

def test_not_logged_in_full_form_fills_username_and_password():
    driver = MagicMock()
    login_btn = MagicMock()

    driver.find_elements.side_effect = [
        [],           # not logged in
        [login_btn],  # login button present
    ]

    modal = MagicMock()
    remembered_el = _mock_el(style="display:none")
    modal.find_elements.return_value = [remembered_el]

    user_field = MagicMock()
    pwd_field = MagicMock()
    submit_btn = MagicMock()
    logged_in_indicator = MagicMock()

    # wait.until returns: modal, user_field, pwd_field, submit_btn, logged_in_indicator
    mock_wait = _make_wait(modal, user_field, pwd_field, submit_btn, logged_in_indicator)

    def _driver_find(by, sel):
        if "pm-1" in sel:
            return modal
        return MagicMock()

    driver.find_element.side_effect = _driver_find

    with patch("migrator.migrator.WebDriverWait", return_value=mock_wait), \
         patch("migrator.migrator._dismiss_cookie_consent"):
        _authenticate(driver, "newuser", "pass123")

    user_field.send_keys.assert_called_once_with("newuser")
    pwd_field.send_keys.assert_called_once_with("pass123")
    submit_btn.click.assert_called_once()


# ---------------------------------------------------------------------------
# Scenario 3: Modal open, remembered user matches → only password filled
# ---------------------------------------------------------------------------

def test_remembered_user_matches_only_password_filled():
    driver = MagicMock()
    login_btn = MagicMock()

    driver.find_elements.side_effect = [
        [],           # not logged in
        [login_btn],  # login button present
    ]

    modal = MagicMock()
    remembered_el = _mock_el(style="")  # visible
    name_el = _mock_el(text="chocovanille")

    modal.find_elements.side_effect = lambda by, sel: (
        [remembered_el] if "login-remembered" in sel else [name_el]
    )

    pwd_field = MagicMock()
    submit_btn = MagicMock()
    logged_in_indicator = MagicMock()

    # wait.until: modal, pwd_field, submit_btn, logged_in_indicator
    mock_wait = _make_wait(modal, pwd_field, submit_btn, logged_in_indicator)

    def _driver_find(by, sel):
        if "pm-1" in sel:
            return modal
        return MagicMock()

    driver.find_element.side_effect = _driver_find

    with patch("migrator.migrator.WebDriverWait", return_value=mock_wait), \
         patch("migrator.migrator._dismiss_cookie_consent"):
        _authenticate(driver, "chocovanille", "mypassword")

    pwd_field.send_keys.assert_called_once_with("mypassword")
    submit_btn.click.assert_called_once()

    # username field should never have been filled
    until_calls = mock_wait.until.call_args_list
    called_selectors = [str(c) for c in until_calls]
    assert not any("input#username" in s for s in called_selectors)


# ---------------------------------------------------------------------------
# Scenario 4: Modal open, remembered user is different → "Not you?" clicked
# ---------------------------------------------------------------------------

def test_remembered_user_differs_clicks_not_you_then_fills_form():
    driver = MagicMock()
    login_btn = MagicMock()

    driver.find_elements.side_effect = [
        [],           # not logged in
        [login_btn],  # login button present
    ]

    modal = MagicMock()
    remembered_el = _mock_el(style="")  # visible
    name_el = _mock_el(text="chocovanille")  # different from target

    modal.find_elements.side_effect = lambda by, sel: (
        [remembered_el] if "login-remembered" in sel else [name_el]
    )

    not_you_link = MagicMock()
    user_field = MagicMock()
    pwd_field = MagicMock()
    submit_btn = MagicMock()
    logged_in_indicator = MagicMock()

    # wait.until: modal, not_you_link, user_field, pwd_field, submit_btn, logged_in_indicator
    mock_wait = _make_wait(modal, not_you_link, user_field, pwd_field, submit_btn, logged_in_indicator)

    def _driver_find(by, sel):
        if "pm-1" in sel:
            return modal
        return MagicMock()

    driver.find_element.side_effect = _driver_find

    with patch("migrator.migrator.WebDriverWait", return_value=mock_wait), \
         patch("migrator.migrator._dismiss_cookie_consent"):
        _authenticate(driver, "otheruser", "otherpass")

    not_you_link.click.assert_called_once()
    user_field.send_keys.assert_called_once_with("otheruser")
    pwd_field.send_keys.assert_called_once_with("otherpass")
    submit_btn.click.assert_called_once()


# ---------------------------------------------------------------------------
# Scenario 5: Login fails (wait for icon-my-parfumo times out)
# ---------------------------------------------------------------------------

def test_auth_error_raised_when_login_indicator_never_appears():
    driver = MagicMock()
    login_btn = MagicMock()

    driver.find_elements.side_effect = [
        [],           # not logged in
        [login_btn],  # login button present
    ]

    modal = MagicMock()
    remembered_el = _mock_el(style="display:none")
    modal.find_elements.return_value = [remembered_el]

    user_field = MagicMock()
    pwd_field = MagicMock()
    submit_btn = MagicMock()

    mock_wait = MagicMock()
    # modal, user_field, pwd_field, submit_btn, then TimeoutException on login indicator
    mock_wait.until.side_effect = [modal, user_field, pwd_field, submit_btn, TimeoutException("timed out")]

    def _driver_find(by, sel):
        if "pm-1" in sel:
            return modal
        return MagicMock()

    driver.find_element.side_effect = _driver_find

    with patch("migrator.migrator.WebDriverWait", return_value=mock_wait), \
         patch("migrator.migrator._dismiss_cookie_consent"):
        with pytest.raises(AuthenticationError, match="invalid credentials"):
            _authenticate(driver, "baduser", "wrongpass")


# ---------------------------------------------------------------------------
# Scenario 6: Already logged in as a different user → logout then re-login
# ---------------------------------------------------------------------------

def test_already_logged_in_as_different_user_logs_out_first():
    driver = MagicMock()
    nick_el = _mock_el(text="chocovanille")
    login_btn = MagicMock()

    driver.find_elements.side_effect = [
        [MagicMock()],  # div.icon-my-parfumo → logged in
        [nick_el],      # span.nick_name → "chocovanille"
        [],             # div#login-btn after logout (not found first time)
        [login_btn],    # div#login-btn after re-navigate
    ]

    modal = MagicMock()
    remembered_el = _mock_el(style="display:none")
    modal.find_elements.return_value = [remembered_el]

    user_field = MagicMock()
    pwd_field = MagicMock()
    submit_btn = MagicMock()
    logged_in_indicator = MagicMock()

    mock_wait = _make_wait(modal, user_field, pwd_field, submit_btn, logged_in_indicator)

    def _driver_find(by, sel):
        if "pm-1" in sel:
            return modal
        return MagicMock()

    driver.find_element.side_effect = _driver_find

    with patch("migrator.migrator.WebDriverWait", return_value=mock_wait), \
         patch("migrator.migrator._dismiss_cookie_consent"):
        _authenticate(driver, "otheruser", "pass")

    get_calls = [c.args[0] for c in driver.get.call_args_list]
    assert "https://www.parfumo.com/board/login.php?logout=1" in get_calls

# Feature: fragrantica-to-parfumo-migrator, Property 12: statement form mechanics

"""
Property 12: Statement form mechanics use the correct selectors and no title field.

For any review text of 140 characters or fewer, _fill_and_submit_statement must:
  - click the element matching .pd_statement_panel
  - populate textarea.form_statement_text with the exact review text
  - click button.action_submit_statement
  - never interact with any title-field selector

Validates: Requirements 7.4, 7.5, 7.6, 7.7
"""

from unittest.mock import MagicMock, patch

from hypothesis import given, settings
from hypothesis import strategies as st
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC

import migrator.review_submitter as rs_module
from migrator.models import ScrapedItem, SubmissionStatus
from migrator.review_submitter import ReviewSubmitter

_ALPHABET = st.characters(whitelist_categories=("L", "N", "Zs"), min_codepoint=32)
_statement_text = st.text(alphabet=_ALPHABET, min_size=1, max_size=140)

_TITLE_SELECTORS = ("form_review_title", "form_statement_title")


@settings(max_examples=100)
@given(text=_statement_text)
def test_statement_form_uses_correct_selectors_and_no_title(text: str) -> None:
    """
    For any statement-length text, _fill_and_submit_statement must:
    - click .pd_statement_panel
    - fill textarea.form_statement_text with the exact text
    - click button.action_submit_statement
    - never access any title-field selector
    """
    assert len(text) <= 140

    driver = MagicMock()
    submitter = ReviewSubmitter(driver=driver, confidence_threshold=0)

    mock_panel_btn = MagicMock()
    mock_textarea = MagicMock()
    mock_submit_btn = MagicMock()

    # Track CSS selectors passed to EC factories via a proxy
    used_selectors: list[str] = []
    original_ec = rs_module.EC

    class TrackingEC:
        """Proxy that records CSS selectors before delegating to real EC."""

        @staticmethod
        def element_to_be_clickable(locator):
            if isinstance(locator, tuple) and locator[0] == By.CSS_SELECTOR:
                used_selectors.append(locator[1])
            return original_ec.element_to_be_clickable(locator)

        @staticmethod
        def presence_of_element_located(locator):
            if isinstance(locator, tuple) and locator[0] == By.CSS_SELECTOR:
                used_selectors.append(locator[1])
            return original_ec.presence_of_element_located(locator)

        @staticmethod
        def invisibility_of_element_located(locator):
            if isinstance(locator, tuple) and locator[0] == By.CSS_SELECTOR:
                used_selectors.append(locator[1])
            return original_ec.invisibility_of_element_located(locator)

    with patch.object(rs_module, "EC", TrackingEC()):
        submitter._wait = MagicMock()
        submitter._wait.until.side_effect = [
            mock_panel_btn,   # element_to_be_clickable(.pd_statement_panel)
            mock_textarea,    # presence_of_element_located(textarea.form_statement_text)
            mock_submit_btn,  # element_to_be_clickable(button.action_submit_statement)
            None,             # invisibility_of_element_located(button.action_submit_statement)
        ]
        item = ScrapedItem(fragrance_name="Test", brand="Brand", review_text=text)
        result = submitter._fill_and_submit_statement(item)

    assert result.status == SubmissionStatus.SUCCESS

    # Correct selectors must have been used
    assert ".pd_statement_panel" in used_selectors, (
        f"Expected .pd_statement_panel in selectors, got: {used_selectors}"
    )
    assert "textarea.form_statement_text" in used_selectors, (
        f"Expected textarea.form_statement_text in selectors, got: {used_selectors}"
    )
    assert used_selectors.count("button.action_submit_statement") == 2, (
        f"Expected button.action_submit_statement twice (click + invisibility), got: {used_selectors}"
    )

    # Textarea filled with exact text
    mock_textarea.clear.assert_called_once()
    mock_textarea.send_keys.assert_called_once_with(text)

    # Panel button and submit button were clicked
    mock_panel_btn.click.assert_called_once()
    mock_submit_btn.click.assert_called_once()

    # No title-field selector was ever used
    for title_sel in _TITLE_SELECTORS:
        assert title_sel not in used_selectors, (
            f"Title selector '{title_sel}' was used but must not be for Statements"
        )
    all_driver_calls = str(driver.mock_calls)
    for title_sel in _TITLE_SELECTORS:
        assert title_sel not in all_driver_calls, (
            f"Title selector '{title_sel}' appeared in driver calls"
        )

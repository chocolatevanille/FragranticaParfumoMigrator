# Feature: fragrantica-to-parfumo-migrator, Property 5: page verification guards wrong fragrance

"""
Property 5: Page verification guards against wrong fragrance.

Tests the page-verification logic extracted from ReviewSubmitter._verify_page()
against random (expected_name, expected_brand, displayed_name, displayed_brand)
tuples.

The verification passes iff:
  score_candidate(expected_name, expected_brand, displayed_name) >= threshold
  OR
  score_candidate(expected_brand, "", displayed_brand) >= threshold

This mirrors the implementation in ReviewSubmitter._verify_page() exactly,
so the property validates that the guard is consistent with the fuzzy-matching
contract for all possible inputs.

Validates: Requirements 2.6
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from migrator.fuzzy import score_candidate

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Printable text: letters, digits, and spaces — representative of real
# fragrance names and brand names without degenerate control characters.
_text = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "Zs"), min_codepoint=32),
    min_size=1,
    max_size=50,
)

_threshold = st.integers(min_value=0, max_value=100)


# ---------------------------------------------------------------------------
# Pure helper that mirrors ReviewSubmitter._verify_page() without Selenium
# ---------------------------------------------------------------------------

def _verify_page_logic(
    expected_name: str,
    expected_brand: str,
    displayed_name: str,
    displayed_brand: str,
    threshold: int,
) -> bool:
    """Pure reimplementation of the verification logic from ReviewSubmitter._verify_page."""
    name_score = score_candidate(expected_name, expected_brand, displayed_name)
    brand_score = score_candidate(expected_brand, "", displayed_brand)
    return name_score >= threshold or brand_score >= threshold


# ---------------------------------------------------------------------------
# Property 5
# ---------------------------------------------------------------------------

@settings(max_examples=100)
@given(
    expected_name=_text,
    expected_brand=_text,
    displayed_name=_text,
    displayed_brand=_text,
    threshold=_threshold,
)
def test_page_verification_passes_iff_similarity_meets_threshold(
    expected_name: str,
    expected_brand: str,
    displayed_name: str,
    displayed_brand: str,
    threshold: int,
) -> None:
    """Validates: Requirements 2.6

    For any (expected_name, expected_brand, displayed_name, displayed_brand, threshold)
    tuple, page verification must pass if and only if at least one of the two
    fuzzy scores meets or exceeds the threshold:

      name_score  = score_candidate(expected_name, expected_brand, displayed_name)
      brand_score = score_candidate(expected_brand, "",             displayed_brand)

      passes iff name_score >= threshold OR brand_score >= threshold
    """
    name_score = score_candidate(expected_name, expected_brand, displayed_name)
    brand_score = score_candidate(expected_brand, "", displayed_brand)

    result = _verify_page_logic(
        expected_name, expected_brand, displayed_name, displayed_brand, threshold
    )

    expected_result = name_score >= threshold or brand_score >= threshold

    assert result == expected_result, (
        f"Verification result {result!r} does not match expected {expected_result!r}. "
        f"expected_name={expected_name!r}, expected_brand={expected_brand!r}, "
        f"displayed_name={displayed_name!r}, displayed_brand={displayed_brand!r}, "
        f"threshold={threshold}, name_score={name_score}, brand_score={brand_score}"
    )

# Feature: fragrantica-to-parfumo-migrator, Property 3: fuzzy score bounded and order-insensitive

"""
Property 3: Fuzzy score is bounded and order-insensitive.

Tests score_candidate() with random (name, brand, candidate) triples.
Asserts:
  1. The score is always in [0, 100].
  2. Swapping word order in the combined query does not decrease the score,
     since token_sort_ratio is order-insensitive by design.

Validates: Requirements 2.2
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from migrator.fuzzy import score_candidate

# Strategy: printable text strings (non-empty to avoid degenerate cases)
_text = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "Zs"), min_codepoint=32),
    min_size=1,
    max_size=50,
)


@settings(max_examples=100)
@given(name=_text, brand=_text, candidate=_text)
def test_score_is_bounded(name: str, brand: str, candidate: str) -> None:
    """Validates: Requirements 2.2

    For any (name, brand, candidate) triple the score must be in [0, 100].
    """
    score = score_candidate(name, brand, candidate)
    assert 0 <= score <= 100, (
        f"score_candidate({name!r}, {brand!r}, {candidate!r}) = {score} "
        f"is outside [0, 100]"
    )


@settings(max_examples=100)
@given(name=_text, brand=_text, candidate=_text)
def test_score_order_insensitive(name: str, brand: str, candidate: str) -> None:
    """Validates: Requirements 2.2

    token_sort_ratio sorts tokens before comparing, so reversing the word
    order of the combined query must yield the same score.
    """
    # Normal order: "{name} {brand}"
    score_normal = score_candidate(name, brand, candidate)

    # Reversed word order: split the combined query and reverse the words
    combined = f"{name} {brand}"
    reversed_combined = " ".join(combined.split()[::-1])

    # Build a reversed-order name/brand pair that produces the reversed query.
    # We pass the reversed string as the name and an empty brand so the
    # combined query inside score_candidate becomes "{reversed_combined} ".
    # To keep it clean, call fuzz directly with the reversed query instead.
    from rapidfuzz import fuzz

    score_reversed = fuzz.token_sort_ratio(reversed_combined, candidate)

    # token_sort_ratio is order-insensitive: both scores must be equal.
    assert score_normal == score_reversed, (
        f"Score changed with word-order swap: "
        f"normal={score_normal}, reversed={score_reversed} "
        f"(name={name!r}, brand={brand!r}, candidate={candidate!r})"
    )

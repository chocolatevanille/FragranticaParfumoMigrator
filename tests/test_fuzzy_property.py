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


# Feature: fragrantica-to-parfumo-migrator, Property 4: candidate selection respects threshold

"""
Property 4: Candidate selection respects confidence threshold.

Tests select_best() with random lists of (candidate, score) pairs and random
threshold values.
Asserts:
  1. When the highest-scoring candidate meets or exceeds the threshold, it is
     returned (first occurrence on tie).
  2. When no candidate meets the threshold, None is returned.

Validates: Requirements 2.3, 2.4, 2.5
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from migrator.fuzzy import select_best

# Strategy: a non-empty list of (candidate_name, score) pairs
_score = st.integers(min_value=0, max_value=100)
_candidate_name = st.text(min_size=1, max_size=30)
_candidate = st.tuples(_candidate_name, _score)
_candidates = st.lists(_candidate, min_size=1, max_size=20)
_threshold = st.integers(min_value=0, max_value=100)


@settings(max_examples=100)
@given(candidates=_candidates, threshold=_threshold)
def test_select_best_threshold_logic(
    candidates: list[tuple[str, int]], threshold: int
) -> None:
    """Validates: Requirements 2.3, 2.4, 2.5

    When the highest score meets the threshold, select_best must return the
    first candidate with that highest score.  When no candidate meets the
    threshold, select_best must return None.
    """
    result = select_best(candidates, threshold)

    max_score = max(score for _, score in candidates)

    if max_score >= threshold:
        # The highest-scoring candidate (first occurrence on tie) must be returned.
        expected = next(c for c, s in candidates if s == max_score)
        assert result == expected, (
            f"Expected {expected!r} (score={max_score}, threshold={threshold}) "
            f"but got {result!r}. candidates={candidates}"
        )
    else:
        # No candidate meets the threshold — must return None.
        assert result is None, (
            f"Expected None (max_score={max_score} < threshold={threshold}) "
            f"but got {result!r}. candidates={candidates}"
        )

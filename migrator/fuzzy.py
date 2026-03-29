from typing import Optional

from rapidfuzz import fuzz


def score_candidate(fragrance_name: str, brand: str, candidate: str) -> int:
    """Score a candidate string against the fragrance name and brand.

    Uses the higher of two scores:
    - name-only: token_sort_ratio(fragrance_name, candidate)
    - combined:  token_sort_ratio("{fragrance_name} {brand}", candidate)

    The name-only score prevents the brand tokens from penalising candidates
    that are an exact name match but don't include the brand (e.g. Parfumo
    autocomplete returns just the fragrance name without the brand).
    """
    name_score = fuzz.token_sort_ratio(fragrance_name, candidate)
    combined_score = fuzz.token_sort_ratio(f"{fragrance_name} {brand}", candidate)
    return max(name_score, combined_score)


def select_best(
    candidates_with_scores: list[tuple[str, int]], threshold: int
) -> Optional[str]:
    """Return the highest-scoring candidate at or above threshold (first on tie), or None."""
    if not candidates_with_scores:
        return None
    max_score = max(score for _, score in candidates_with_scores)
    if max_score < threshold:
        return None
    return next(c for c, s in candidates_with_scores if s == max_score)

from typing import Optional

from rapidfuzz import fuzz


def score_candidate(fragrance_name: str, brand: str, candidate: str) -> int:
    """Score a candidate string against the combined fragrance name and brand."""
    query = f"{fragrance_name} {brand}"
    return fuzz.token_sort_ratio(query, candidate)


def select_best(
    candidates_with_scores: list[tuple[str, int]], threshold: int
) -> Optional[str]:
    """Return the first candidate at or above threshold, or None."""
    for candidate, score in candidates_with_scores:
        if score >= threshold:
            return candidate
    return None

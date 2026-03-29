from typing import Optional

from rapidfuzz import fuzz


def score_candidate(fragrance_name: str, brand: str, candidate: str) -> int:
    """Score a candidate string against the combined fragrance name and brand."""
    query = f"{fragrance_name} {brand}"
    return fuzz.token_sort_ratio(query, candidate)


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

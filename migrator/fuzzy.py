from typing import Optional

from rapidfuzz import fuzz


def score_candidate(fragrance_name: str, brand: str, candidate: str, candidate_brand: str = "") -> int:
    """Score a candidate string against the fragrance name and brand.

    Scores are computed against the combined "{name} {brand}" string on both
    sides so that brand similarity contributes positively and brand mismatch
    penalises the score.

    Three scores are taken and the maximum is returned:
    - name-only:      token_sort_ratio(fragrance_name, candidate)
    - combined query: token_sort_ratio("{fragrance_name} {brand}", candidate)
    - combined both:  token_sort_ratio("{fragrance_name} {brand}", "{candidate} {candidate_brand}")
                      (only when candidate_brand is provided)
    """
    name_score = fuzz.token_sort_ratio(fragrance_name, candidate)
    combined_score = fuzz.token_sort_ratio(f"{fragrance_name} {brand}", candidate)
    scores = [name_score, combined_score]
    if candidate_brand:
        both_score = fuzz.token_sort_ratio(
            f"{fragrance_name} {brand}", f"{candidate} {candidate_brand}"
        )
        scores.append(both_score)
    return max(scores)


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

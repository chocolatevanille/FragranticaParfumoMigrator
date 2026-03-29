# Feature: fragrantica-to-parfumo-migrator, Property 1: extraction completeness

"""
Property 1: Extraction completeness.

Tests ReviewScraper._parse() against a real captured snapshot of
https://www.fragrantica.com/member/1186668 with all 10 reviews loaded.
Asserts the scraper returns exactly 10 ScrapedItem objects with the
correct fragrance name, brand, and review text for each entry.

Validates: Requirements 1.2
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from migrator.models import ScrapedItem
from migrator.review_scraper import ReviewScraper

# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

_SNAPSHOT = Path(__file__).parent / "__snapshots__" / "member_1186668_reviews.html"

# Ground-truth reviews extracted from the snapshot (order matches page order).
# Each tuple is (fragrance_name, brand, review_text_start) where review_text_start
# is a unique prefix long enough to identify the review unambiguously.
_EXPECTED_REVIEWS = [
    (
        "Prodigy",
        "Mind Games",
        "I tend to find Mind Games as a house is a little overrated.",
    ),
    (
        "Very Good Girl Elixir",
        "Carolina Herrera",
        "In the past the Good Girl line has played it a little safe for my taste.",
    ),
    (
        "Fun Things Always Happen After Sunset",
        "By Kilian",
        "I concur with the below review.",
    ),
    (
        "Beaver",
        "Zoologist Perfumes",
        "Potentially the worst fragrance I have ever had the displeasure of experiencing,",
    ),
    (
        "Tyrannosaurus Rex",
        "Zoologist Perfumes",
        "First impression: Wow, this is dirty.",
    ),
    (
        "Noir de Noir",
        "Tom Ford",
        "Sexual, mature, polished.",
    ),
    (
        "Explorer",
        "Montblanc",
        "Harsh, almost offensive opening of fruits and ambroxan.",
    ),
    (
        "Bleu de Chanel Parfum",
        "Chanel",
        "Wonderful lemon opening with multiple layers,",
    ),
    (
        "Tuscan Leather",
        "Tom Ford",
        "The ultimate masculine fragrance.",
    ),
    (
        "Light Blue Eau Intense Pour Homme",
        "Dolce&Gabbana",
        "Light Blue Eau Intense is a dreadful synthetic blue",
    ),
]


def _make_scraper() -> ReviewScraper:
    return ReviewScraper(driver=MagicMock())


# ---------------------------------------------------------------------------
# Snapshot test — Property 1: Extraction completeness
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _SNAPSHOT.exists(), reason="Snapshot file not present")
def test_extraction_completeness_snapshot() -> None:
    """Validates: Requirements 1.2

    Parse the captured HTML snapshot of member/1186668 and assert that
    _parse() returns exactly 10 ScrapedItem objects whose fields match
    the known ground-truth reviews.
    """
    html = _SNAPSHOT.read_text(encoding="utf-8")
    scraper = _make_scraper()

    results = scraper._parse(html)

    assert len(results) == len(_EXPECTED_REVIEWS), (
        f"Expected {len(_EXPECTED_REVIEWS)} reviews, got {len(results)}. "
        f"Names found: {[r.fragrance_name for r in results]}"
    )

    for i, (item, (exp_name, exp_brand, exp_text_start)) in enumerate(
        zip(results, _EXPECTED_REVIEWS)
    ):
        assert isinstance(item, ScrapedItem), f"Item {i} is not a ScrapedItem"

        assert item.fragrance_name == exp_name, (
            f"[{i}] fragrance_name: expected {exp_name!r}, got {item.fragrance_name!r}"
        )
        assert item.brand == exp_brand, (
            f"[{i}] brand: expected {exp_brand!r}, got {item.brand!r}"
        )
        assert item.review_text.startswith(exp_text_start), (
            f"[{i}] review_text does not start with {exp_text_start!r}. "
            f"Got: {item.review_text[:100]!r}"
        )

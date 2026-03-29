# Feature: fragrantica-to-parfumo-migrator, Property 10: only registered handler invoked

"""
Property 10: Only the registered handler is invoked for a given data type.

For any set of registered data-type handlers, when the migrator is invoked with
a specific data type, only the scraper and submitter registered for that data type
shall be called; handlers for other data types shall not be invoked.

Validates: Requirements 6.2
"""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from migrator.registry import PluginRegistry
from migrator.exceptions import UnknownDataTypeError


# ---------------------------------------------------------------------------
# Minimal stub classes that stand in for BaseScraper / BaseSubmitter.
# We avoid importing the abstract bases (which may not exist yet) and instead
# create plain classes that the registry accepts via its Type[...] annotations.
# ---------------------------------------------------------------------------

def make_handler_pair(tag: str):
    """Return a unique (scraper_cls, submitter_cls) pair identified by *tag*."""

    class _Scraper:
        handler_tag = tag

    class _Submitter:
        handler_tag = tag

    _Scraper.__name__ = f"Scraper_{tag}"
    _Submitter.__name__ = f"Submitter_{tag}"
    return _Scraper, _Submitter


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# Generate a non-empty list of distinct, non-empty ASCII data-type names.
data_type_names = st.text(
    alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd"), whitelist_characters="_"),
    min_size=1,
    max_size=20,
)

distinct_data_types = st.lists(
    data_type_names,
    min_size=2,
    max_size=8,
    unique=True,
)


# ---------------------------------------------------------------------------
# Property 10
# ---------------------------------------------------------------------------

@settings(max_examples=100)
@given(data_types=distinct_data_types)
def test_only_registered_handler_returned_for_data_type(data_types):
    """**Validates: Requirements 6.2**

    For any set of registered data-type handlers, get() with a specific data
    type returns exactly the (scraper_cls, submitter_cls) pair registered for
    that type and no other pair.
    """
    registry = PluginRegistry()

    # Build a mapping of data_type -> (scraper_cls, submitter_cls) and register all.
    handler_map = {}
    for dt in data_types:
        scraper_cls, submitter_cls = make_handler_pair(dt)
        handler_map[dt] = (scraper_cls, submitter_cls)
        registry.register(dt, scraper_cls, submitter_cls)

    # For each registered data type, assert only its own handler is returned.
    for target_dt in data_types:
        returned_scraper, returned_submitter = registry.get(target_dt)

        expected_scraper, expected_submitter = handler_map[target_dt]

        # The correct handler must be returned.
        assert returned_scraper is expected_scraper, (
            f"get('{target_dt}') returned wrong scraper: "
            f"expected {expected_scraper.__name__}, got {returned_scraper.__name__}"
        )
        assert returned_submitter is expected_submitter, (
            f"get('{target_dt}') returned wrong submitter: "
            f"expected {expected_submitter.__name__}, got {returned_submitter.__name__}"
        )

        # Handlers for every other data type must NOT be returned.
        for other_dt, (other_scraper, other_submitter) in handler_map.items():
            if other_dt == target_dt:
                continue
            assert returned_scraper is not other_scraper, (
                f"get('{target_dt}') returned scraper belonging to '{other_dt}'"
            )
            assert returned_submitter is not other_submitter, (
                f"get('{target_dt}') returned submitter belonging to '{other_dt}'"
            )


@settings(max_examples=100)
@given(
    registered_types=distinct_data_types,
    unknown_suffix=st.text(
        alphabet=st.characters(whitelist_categories=("Ll",)),
        min_size=1,
        max_size=10,
    ),
)
def test_unregistered_data_type_raises_unknown_error(registered_types, unknown_suffix):
    """**Validates: Requirements 6.2**

    Requesting a data type that was never registered must raise
    UnknownDataTypeError, ensuring no handler from another type is silently
    returned.
    """
    registry = PluginRegistry()
    for dt in registered_types:
        scraper_cls, submitter_cls = make_handler_pair(dt)
        registry.register(dt, scraper_cls, submitter_cls)

    # Construct a key guaranteed not to be in registered_types.
    unknown_key = "__unknown__" + unknown_suffix
    # Ensure it really isn't registered (extremely unlikely collision, but be safe).
    assume_not_registered = unknown_key not in registered_types

    if assume_not_registered:
        with pytest.raises(UnknownDataTypeError):
            registry.get(unknown_key)

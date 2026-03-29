"""Unit tests for PluginRegistry and UnknownDataTypeError.

Validates: Requirements 6.1, 6.3
"""

import pytest

from migrator.registry import PluginRegistry
from migrator.exceptions import UnknownDataTypeError


# ---------------------------------------------------------------------------
# Minimal stub classes
# ---------------------------------------------------------------------------

class StubScraper:
    pass


class StubSubmitter:
    pass


class AnotherScraper:
    pass


class AnotherSubmitter:
    pass


# ---------------------------------------------------------------------------
# UnknownDataTypeError message tests
# ---------------------------------------------------------------------------

class TestUnknownDataTypeErrorMessage:
    def test_message_contains_requested_key(self):
        err = UnknownDataTypeError("reviews", ["reviews", "notes"])
        assert "reviews" in str(err)

    def test_message_contains_all_registered_types(self):
        registry = PluginRegistry()
        registry.register("reviews", StubScraper, StubSubmitter)
        registry.register("notes", AnotherScraper, AnotherSubmitter)

        with pytest.raises(UnknownDataTypeError) as exc_info:
            registry.get("unknown_type")

        msg = str(exc_info.value)
        assert "reviews" in msg
        assert "notes" in msg

    def test_message_contains_unknown_key_that_was_requested(self):
        registry = PluginRegistry()
        registry.register("reviews", StubScraper, StubSubmitter)

        with pytest.raises(UnknownDataTypeError) as exc_info:
            registry.get("nonexistent")

        assert "nonexistent" in str(exc_info.value)

    def test_message_contains_none_registered_when_empty(self):
        registry = PluginRegistry()

        with pytest.raises(UnknownDataTypeError) as exc_info:
            registry.get("anything")

        assert "(none registered)" in str(exc_info.value)

    def test_error_stores_requested_and_supported_attributes(self):
        err = UnknownDataTypeError("foo", ["bar", "baz"])
        assert err.requested == "foo"
        assert err.supported == ["bar", "baz"]


# ---------------------------------------------------------------------------
# supported_types() tests
# ---------------------------------------------------------------------------

class TestSupportedTypes:
    def test_empty_registry_returns_empty_list(self):
        registry = PluginRegistry()
        assert registry.supported_types() == []

    def test_returns_all_registered_names(self):
        registry = PluginRegistry()
        registry.register("reviews", StubScraper, StubSubmitter)
        registry.register("notes", AnotherScraper, AnotherSubmitter)

        types = registry.supported_types()
        assert "reviews" in types
        assert "notes" in types
        assert len(types) == 2

    def test_insertion_order_is_preserved(self):
        registry = PluginRegistry()
        registry.register("alpha", StubScraper, StubSubmitter)
        registry.register("beta", AnotherScraper, AnotherSubmitter)
        registry.register("gamma", StubScraper, StubSubmitter)

        assert registry.supported_types() == ["alpha", "beta", "gamma"]

    def test_adding_new_type_updates_result(self):
        registry = PluginRegistry()
        registry.register("reviews", StubScraper, StubSubmitter)
        assert registry.supported_types() == ["reviews"]

        registry.register("notes", AnotherScraper, AnotherSubmitter)
        assert registry.supported_types() == ["reviews", "notes"]

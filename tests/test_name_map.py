"""Tests for name normalization."""
import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from name_map import normalize, NAME_MAP


class TestNormalize:
    def test_known_alias_resolves(self):
        assert normalize("ali arevalov") == "Ali Arevalo"

    def test_canonical_name_unchanged(self):
        assert normalize("Ali Arevalo") == "Ali Arevalo"

    def test_unknown_name_returned_stripped(self):
        assert normalize("  John Doe  ") == "John Doe"

    def test_case_insensitive_match(self):
        # Both "ali arevalov" and "ALI AREVALOV" should resolve
        assert normalize("ALI AREVALOV") == "Ali Arevalo"

    def test_empty_string(self):
        assert normalize("") == ""

    def test_whitespace_only(self):
        assert normalize("   ") == ""

    def test_name_map_has_entries(self):
        assert len(NAME_MAP) >= 2

    def test_all_map_values_are_canonical(self):
        # Every value should itself resolve to the same value (no chained aliases)
        for raw, canonical in NAME_MAP.items():
            assert normalize(canonical) == canonical, (
                f"Canonical name '{canonical}' does not resolve to itself"
            )

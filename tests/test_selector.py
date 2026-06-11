"""Tests for selector search filtering."""

from __future__ import annotations

from okit.selector import _build_nodes, _build_search_visible, _fuzzy_matches


class TestFuzzyMatches:
    def test_matches_case_insensitive_ordered_characters(self):
        # Given
        query = "rvw"
        label = "ReviewWriter"

        # When
        result = _fuzzy_matches(query, label)

        # Then
        assert result is True

    def test_rejects_out_of_order_characters(self):
        # Given
        query = "wrv"
        label = "Review"

        # When
        result = _fuzzy_matches(query, label)

        # Then
        assert result is False


class TestBuildSearchVisible:
    def test_includes_matching_leaf_and_ancestors(self):
        # Given
        groups = [
            {
                "label": "user/repo",
                "children": [
                    {
                        "label": "Agents",
                        "items": [(0, "reviewer"), (1, "planner")],
                    }
                ],
            }
        ]
        nodes = _build_nodes(groups)

        # When
        visible = _build_search_visible(nodes, "rv")

        # Then
        assert [nodes[pos].label for pos in visible] == ["user/repo", "Agents", "reviewer"]

    def test_returns_empty_list_when_nothing_matches(self):
        # Given
        groups = [
            {
                "label": "user/repo",
                "children": [{"label": "Skills", "items": [(0, "context7")]}],
            }
        ]
        nodes = _build_nodes(groups)

        # When
        visible = _build_search_visible(nodes, "zzz")

        # Then
        assert visible == []

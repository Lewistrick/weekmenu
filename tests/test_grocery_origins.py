"""Tests for reconstructing why an ingredient is on the grocery list."""

from src.grocery import compute_ingredient_origins


def test_origin_from_single_recipe() -> None:
    """An ingredient in one week-menu recipe reports that recipe's name."""
    origins = compute_ingredient_origins(
        recipe_ingredient_ids={10: {1, 2}},
        recipe_names={10: "Pasta"},
        weekly_ingredient_ids=set(),
    )

    assert origins[1]["recipe_names"] == ["Pasta"]
    assert origins[1]["from_weekly"] is False


def test_origin_from_multiple_recipes_sorted() -> None:
    """An ingredient shared by several recipes lists all names alphabetically."""
    origins = compute_ingredient_origins(
        recipe_ingredient_ids={10: {1}, 20: {1}, 30: {2}},
        recipe_names={10: "Stew", 20: "Curry", 30: "Salad"},
        weekly_ingredient_ids=set(),
    )

    assert origins[1]["recipe_names"] == ["Curry", "Stew"]


def test_origin_from_weekly_groceries() -> None:
    """An ingredient only in weekly groceries is flagged as weekly, no recipes."""
    origins = compute_ingredient_origins(
        recipe_ingredient_ids={},
        recipe_names={},
        weekly_ingredient_ids={5},
    )

    assert origins[5]["recipe_names"] == []
    assert origins[5]["from_weekly"] is True


def test_origin_from_recipe_and_weekly() -> None:
    """An ingredient from both sources reports the recipe and the weekly flag."""
    origins = compute_ingredient_origins(
        recipe_ingredient_ids={10: {1}},
        recipe_names={10: "Pasta"},
        weekly_ingredient_ids={1},
    )

    assert origins[1]["recipe_names"] == ["Pasta"]
    assert origins[1]["from_weekly"] is True


def test_manual_ingredient_absent_from_origins() -> None:
    """An ingredient in neither source is absent, signalling a manual add."""
    origins = compute_ingredient_origins(
        recipe_ingredient_ids={10: {1}},
        recipe_names={10: "Pasta"},
        weekly_ingredient_ids={2},
    )

    assert 99 not in origins

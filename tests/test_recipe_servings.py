"""Tests for resolving the servings shown on the recipe view.

Regression cover for a bug where opening the recipe view without a ``servings``
query parameter left the field empty, which in turn built an
``add-to-groceries?servings=`` URL that returned 400 Bad Request.
"""

from types import SimpleNamespace

from src.controllers.recipes import RecipeController


def _recipe(servings: object) -> SimpleNamespace:
    """Return a minimal stand-in exposing only ``.servings``."""
    return SimpleNamespace(servings=servings)


def test_missing_query_param_falls_back_to_recipe_servings() -> None:
    """No query value should display the recipe's own servings, not empty."""
    assert RecipeController._display_servings(None, _recipe(3)) == 3


def test_empty_query_param_falls_back_to_recipe_servings() -> None:
    """An empty ``servings=`` must not blow up; it uses the recipe servings."""
    assert RecipeController._display_servings("", _recipe(3)) == 3


def test_valid_query_param_overrides_recipe_servings() -> None:
    """A valid query value should win over the stored recipe servings."""
    assert RecipeController._display_servings("5", _recipe(3)) == 5


def test_non_positive_query_param_falls_back() -> None:
    """Zero or negative values are rejected in favour of the recipe servings."""
    assert RecipeController._display_servings("0", _recipe(3)) == 3


def test_non_numeric_query_param_falls_back() -> None:
    """Garbage input falls back to the recipe servings rather than erroring."""
    assert RecipeController._display_servings("abc", _recipe(3)) == 3


def test_invalid_recipe_servings_defaults_to_two() -> None:
    """A missing stored servings value still yields a sensible default."""
    assert RecipeController._display_servings(None, _recipe(None)) == 2

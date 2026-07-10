"""Tests for weekly grocery list helpers."""

from src.week_menu import GroceryItem
from src.weekly_groceries import weekly_groceries_missing_from_list


def test_weekly_groceries_missing_from_list_filters_present_lines() -> None:
    """Only weekly groceries missing from the current list should be returned."""
    weekly = [
        GroceryItem(ingredient_id=1, name="oats", unit="g", quantity=500.0),
        GroceryItem(ingredient_id=2, name="apples", unit="st", quantity=6.0),
    ]
    current = [
        GroceryItem(ingredient_id=1, name="oats", unit="g", quantity=200.0),
    ]

    missing = weekly_groceries_missing_from_list(weekly, current)

    assert len(missing) == 1
    assert missing[0]["name"] == "apples"

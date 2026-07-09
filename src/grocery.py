"""Grocery list grouping and plaintext export helpers."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, TypedDict

from src.shops import ShopInfo
from src.week_menu import GroceryItem

UNASSIGNED_SHOP_LABEL = "Unassigned"


class GroceryGroup(TypedDict):
    """A shop section on the grocery list."""

    shop_id: int
    shop_name: str
    foreground_color: str
    background_color: str
    letter: str
    entries: list[GroceryItem]


def format_grocery_line(item: GroceryItem) -> str:
    """Format one grocery line as ``{ingredient} - {amount} {unit}``."""
    quantity = format(item["quantity"], "g")
    return f"{item['name']} - {quantity} {item['unit']}"


def split_grocery_lists(
    items: list[GroceryItem],
    ingredient_shop_ids: dict[int, int | None],
    shops: list[ShopInfo],
    already_have_ids: set[int],
) -> tuple[list[GroceryItem], list[GroceryItem], list[GroceryGroup]]:
    """Split grocery items into unassigned, already-have, and shop groups.

    Args:
        items: Aggregated grocery items for the week menu.
        ingredient_shop_ids: Ingredient id to shop id mapping for the user.
        shops: Shops owned by the user.
        already_have_ids: Ingredient ids marked as already in stock.

    Returns:
        Unassigned items, already-have items, and assigned shop groups.
    """
    shops_by_id = {shop["id"]: shop for shop in shops}
    unassigned: list[GroceryItem] = []
    already_have: list[GroceryItem] = []
    shop_buckets: dict[int, list[GroceryItem]] = defaultdict(list)

    for item in items:
        if item["ingredient_id"] in already_have_ids:
            already_have.append(item)
            continue
        shop_id = ingredient_shop_ids.get(item["ingredient_id"])
        if shop_id is None or shop_id not in shops_by_id:
            unassigned.append(item)
            continue
        shop_buckets[shop_id].append(item)

    groups: list[GroceryGroup] = []
    for shop in sorted(shops, key=lambda entry: entry["name"].lower()):
        entries = shop_buckets.get(shop["id"], [])
        if not entries:
            continue
        groups.append(
            GroceryGroup(
                shop_id=shop["id"],
                shop_name=shop["name"],
                foreground_color=shop["foreground_color"],
                background_color=shop["background_color"],
                letter=shop["letter"],
                entries=sorted(entries, key=lambda entry: entry["name"].lower()),
            )
        )

    return (
        sorted(unassigned, key=lambda entry: entry["name"].lower()),
        sorted(already_have, key=lambda entry: entry["name"].lower()),
        groups,
    )


def format_grocery_export(
    unassigned: list[GroceryItem],
    groups: list[GroceryGroup],
) -> str:
    """Render grocery lists as plaintext sections per shop."""
    sections: list[str] = []
    if unassigned:
        lines = [format_grocery_line(item) for item in unassigned]
        sections.append(f"{UNASSIGNED_SHOP_LABEL}\n" + "\n".join(lines))
    for group in groups:
        if not group["entries"]:
            continue
        lines = [format_grocery_line(item) for item in group["entries"]]
        sections.append(f"{group['shop_name']}\n" + "\n".join(lines))
    return "\n\n".join(sections)


def format_week_menu_export(days: list[dict[str, Any]]) -> str:
    """Render the week menu as ``{day} - {recipe}`` lines."""
    lines: list[str] = []
    for row in days:
        recipe = row.get("recipe")
        if recipe is None:
            continue
        lines.append(f"{row['label']} - {recipe.name}")
    return "\n".join(lines)

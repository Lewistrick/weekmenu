"""Grocery list grouping and plaintext export helpers."""

from collections import defaultdict
from typing import Any, TypedDict

from src.shops import ShopInfo
from src.week_menu import GroceryItem, grocery_line_key, resolve_grocery_line_shop_id

UNASSIGNED_SHOP_LABEL = "Unassigned"
TO_CHECK_LABEL = "To check"


class GroceryGroup(TypedDict):
    """A shop section on the grocery list."""

    shop_id: int
    shop_name: str
    foreground_color: str
    background_color: str
    letter: str
    entries: list[GroceryItem]


class IngredientOrigin(TypedDict):
    """Reconstructed explanation of why an ingredient is on the grocery list.

    Origins are not stored; they are recomputed from the current week menu and
    weekly groceries. An ingredient can come from one or more week-menu recipes,
    from the weekly groceries, from both, or from neither (added manually).
    """

    recipe_names: list[str]
    from_weekly: bool


def compute_ingredient_origins(
    recipe_ingredient_ids: dict[int, set[int]],
    recipe_names: dict[int, str],
    weekly_ingredient_ids: set[int],
) -> dict[int, IngredientOrigin]:
    """Map each ingredient id to how it ended up on the grocery list.

    Args:
        recipe_ingredient_ids: Week-menu recipe id to the set of ingredient ids
            it contains.
        recipe_names: Week-menu recipe id to its display name.
        weekly_ingredient_ids: Ingredient ids present in the weekly groceries.

    Returns:
        A mapping of ingredient id to its origin. Ingredient ids that appear in
        neither source are absent, which callers treat as "added manually".
    """
    all_ingredient_ids: set[int] = set(weekly_ingredient_ids)
    for ingredient_ids in recipe_ingredient_ids.values():
        all_ingredient_ids |= ingredient_ids

    origins: dict[int, IngredientOrigin] = {}
    for ingredient_id in all_ingredient_ids:
        names = sorted(
            recipe_names[recipe_id]
            for recipe_id, ingredient_ids in recipe_ingredient_ids.items()
            if ingredient_id in ingredient_ids and recipe_id in recipe_names
        )
        origins[ingredient_id] = IngredientOrigin(
            recipe_names=names,
            from_weekly=ingredient_id in weekly_ingredient_ids,
        )
    return origins


def format_grocery_line(item: GroceryItem) -> str:
    """Format one grocery line as ``{ingredient} - {amount} {unit}``."""
    quantity = format(item["quantity"], "g")
    return f"{item['name']} - {quantity} {item['unit']}"


def split_grocery_lists(
    items: list[GroceryItem],
    ingredient_shop_ids: dict[int, int | None],
    shops: list[ShopInfo],
    already_have_line_keys: set[str],
    to_check_line_keys: set[str],
    line_shop_ids: dict[str, int],
) -> tuple[list[GroceryItem], list[GroceryItem], list[GroceryItem], list[GroceryGroup]]:
    """Split grocery items into unassigned, to-check, already-have, and shop groups.

    Args:
        items: Aggregated grocery items for the week menu.
        ingredient_shop_ids: Default ingredient id to shop id mapping for the user.
        shops: Shops owned by the user.
        already_have_line_keys: Grocery line keys marked as already in stock.
        to_check_line_keys: Grocery line keys marked for later verification.
        line_shop_ids: Per-line shop overrides for the current grocery list.

    Returns:
        Unassigned items, to-check items, already-have items, and assigned shop groups.
    """
    shops_by_id = {shop["id"]: shop for shop in shops}
    unassigned: list[GroceryItem] = []
    to_check: list[GroceryItem] = []
    already_have: list[GroceryItem] = []
    shop_buckets: dict[int, list[GroceryItem]] = defaultdict(list)

    for item in items:
        line_key = grocery_line_key(item["ingredient_id"], item["unit"])
        if line_key in already_have_line_keys:
            already_have.append(item)
            continue
        if line_key in to_check_line_keys:
            to_check.append(item)
            continue
        shop_id = resolve_grocery_line_shop_id(item, ingredient_shop_ids, line_shop_ids)
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
        sorted(to_check, key=lambda entry: entry["name"].lower()),
        sorted(already_have, key=lambda entry: entry["name"].lower()),
        groups,
    )


def format_grocery_export(
    unassigned: list[GroceryItem],
    to_check: list[GroceryItem],
    groups: list[GroceryGroup],
    *,
    unassigned_label: str = UNASSIGNED_SHOP_LABEL,
    to_check_label: str = TO_CHECK_LABEL,
) -> str:
    """Render grocery lists as plaintext sections per shop."""
    sections: list[str] = []
    if unassigned:
        lines = [format_grocery_line(item) for item in unassigned]
        sections.append(f"{unassigned_label}\n" + "\n".join(lines))
    if to_check:
        lines = [format_grocery_line(item) for item in to_check]
        sections.append(f"{to_check_label}\n" + "\n".join(lines))
    for group in groups:
        if not group["entries"]:
            continue
        lines = [format_grocery_line(item) for item in group["entries"]]
        sections.append(f"{group['shop_name']}\n" + "\n".join(lines))
    return "\n\n".join(sections)


def format_week_menu_export(days: list[dict[str, Any]]) -> str:
    """Render the week menu as ``{day_abbrev} {recipe}`` lines.

    Each day label is shortened to its first two characters (lowercase),
    with a space before the recipe name and no hyphen.
    """
    lines: list[str] = []
    for row in days:
        recipe = row.get("recipe")
        if recipe is None:
            continue
        day_abbrev = str(row["label"])[:2].lower()
        lines.append(f"{day_abbrev} {recipe.name}")
    return "\n".join(lines)

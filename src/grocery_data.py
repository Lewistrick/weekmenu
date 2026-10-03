"""Loading and splitting a user's grocery list for the pages that show it."""

from typing import TypedDict

from src.categories import (
    CategoryInfo,
    CategorySection,
    group_by_category,
    load_categories,
    load_ingredient_category_ids,
)
from src.grocery import GroceryGroup, split_grocery_lists
from src.i18n.service import t
from src.plan_store import (
    is_grocery_list_initialized,
    load_already_have_line_keys,
    load_grocery_line_shops,
    load_grocery_list,
    load_in_basket_line_keys,
    load_to_check_line_keys,
    prune_orphaned_grocery_lines,
)
from src.shops import ShopInfo, load_ingredient_shop_ids, load_shops
from src.week_menu import GroceryItem, hydrate_grocery_item_names


class GrocerySplit(TypedDict):
    """A grocery list split into its lists, plus what the pages need to render it."""

    shops: list[ShopInfo]
    ingredient_shop_ids: dict[int, int | None]
    line_shop_ids: dict[str, int]
    already_have_line_keys: set[str]
    to_check_line_keys: set[str]
    in_basket_line_keys: set[str]
    unassigned_items: list[GroceryItem]
    to_check_items: list[GroceryItem]
    already_have_items: list[GroceryItem]
    grocery_groups: list[GroceryGroup]
    to_check_sections: list[CategorySection]
    categories: list[CategoryInfo]
    ingredient_category_ids: dict[int, int | None]


async def load_current_grocery_items(user_id: int) -> list[GroceryItem]:
    """Return the persisted grocery list with names, or ``[]`` before one exists."""
    if not await is_grocery_list_initialized(user_id):
        return []
    return await prune_orphaned_grocery_lines(
        user_id,
        await hydrate_grocery_item_names(user_id, await load_grocery_list(user_id)),
    )


async def load_grocery_split(
    user_id: int, grocery_items: list[GroceryItem]
) -> GrocerySplit:
    """Split grocery items into lists and group them by the user's shelves.

    Args:
        user_id: Owner of the shops, shelves and sorting state.
        grocery_items: The list's lines, with display names.

    Returns:
        The unassigned, to-check and already-have lists, the shop groups (each
        with category sections) and the lookup tables the templates use.
    """
    ingredient_shop_ids = await load_ingredient_shop_ids(user_id)
    shops = await load_shops(user_id)
    already_have_line_keys = await load_already_have_line_keys(user_id)
    to_check_line_keys = await load_to_check_line_keys(user_id)
    line_shop_ids = await load_grocery_line_shops(user_id)
    unassigned_items, to_check_items, already_have_items, grocery_groups = (
        split_grocery_lists(
            grocery_items,
            ingredient_shop_ids,
            shops,
            already_have_line_keys,
            to_check_line_keys,
            line_shop_ids,
        )
    )
    categories = await load_categories(user_id)
    ingredient_category_ids = await load_ingredient_category_ids(user_id)
    uncategorised_label = t("categories.uncategorised")
    for group in grocery_groups:
        group["sections"] = group_by_category(
            group["entries"],
            ingredient_category_ids,
            categories,
            uncategorised_label=uncategorised_label,
        )
    return GrocerySplit(
        shops=shops,
        ingredient_shop_ids=ingredient_shop_ids,
        line_shop_ids=line_shop_ids,
        already_have_line_keys=already_have_line_keys,
        to_check_line_keys=to_check_line_keys,
        in_basket_line_keys=await load_in_basket_line_keys(user_id),
        unassigned_items=unassigned_items,
        to_check_items=to_check_items,
        already_have_items=already_have_items,
        grocery_groups=grocery_groups,
        to_check_sections=group_by_category(
            to_check_items,
            ingredient_category_ids,
            categories,
            uncategorised_label=uncategorised_label,
        ),
        categories=categories,
        ingredient_category_ids=ingredient_category_ids,
    )

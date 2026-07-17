"""Per-user shop helpers and ingredient-to-shop assignments."""

from collections import defaultdict
from typing import TypedDict

from src.models import Ingredient, RecipeIngredient, Shop, UserIngredientShop

DEFAULT_SHOP_COLORS: tuple[tuple[str, str], ...] = (
    ("#ffffff", "#2563eb"),
    ("#1f2937", "#fbbf24"),
    ("#ffffff", "#059669"),
    ("#ffffff", "#7c3aed"),
    ("#ffffff", "#dc2626"),
    ("#ffffff", "#0891b2"),
)


class ShopInfo(TypedDict):
    """Display metadata for one shop."""

    id: int
    name: str
    foreground_color: str
    background_color: str
    letter: str


def shop_letter(name: str) -> str:
    """Return the first letter of a shop name for chip buttons."""
    stripped = name.strip()
    return stripped[0].upper() if stripped else "?"


async def next_shop_colors(owner_id: int) -> tuple[str, str]:
    """Pick the next default foreground/background pair for a new shop."""
    count = await Shop.filter(owner_id=owner_id).count()
    return DEFAULT_SHOP_COLORS[count % len(DEFAULT_SHOP_COLORS)]


async def get_or_create_shop(
    owner_id: int,
    name: str,
    *,
    foreground_color: str | None = None,
    background_color: str | None = None,
) -> tuple[Shop, bool]:
    """Return a shop owned by ``owner_id``, creating it when missing."""
    normalized = name.strip()
    existing = await Shop.filter(owner_id=owner_id, name=normalized).first()
    if existing is not None:
        return existing, False
    fg, bg = await next_shop_colors(owner_id)
    return (
        await Shop.create(
            owner_id=owner_id,
            name=normalized,
            foreground_color=foreground_color or fg,
            background_color=background_color or bg,
        ),
        True,
    )


async def load_shops(owner_id: int) -> list[ShopInfo]:
    """Return all shops for a user with display metadata."""
    shops = await Shop.filter(owner_id=owner_id).order_by("name")
    return [
        ShopInfo(
            id=shop.id,
            name=shop.name,
            foreground_color=shop.foreground_color or "#ffffff",
            background_color=shop.background_color or "#2563eb",
            letter=shop_letter(shop.name),
        )
        for shop in shops
    ]


async def load_shop_names(owner_id: int) -> dict[int, str]:
    """Return shop ids mapped to names for one user."""
    shops = await Shop.filter(owner_id=owner_id).order_by("name")
    return {shop.id: shop.name for shop in shops}


async def load_ingredient_shop_ids(user_id: int) -> dict[int, int | None]:
    """Return ingredient ids mapped to assigned shop ids for one user."""
    rows = await UserIngredientShop.filter(user_id=user_id).values(
        "ingredient_id", "shop_id"
    )
    return {row["ingredient_id"]: row["shop_id"] for row in rows}


async def set_ingredient_shop(
    user_id: int, ingredient_id: int, shop_id: int | None
) -> None:
    """Persist which shop an ingredient should be bought at."""
    mapping = await UserIngredientShop.get_or_none(
        user_id=user_id, ingredient_id=ingredient_id
    )
    if shop_id is None:
        if mapping is not None:
            await mapping.delete()
        return

    if mapping is None:
        await UserIngredientShop.create(
            user_id=user_id, ingredient_id=ingredient_id, shop_id=shop_id
        )
        return

    mapping.shop_id = shop_id
    await mapping.save()


async def load_ingredient_recipe_counts(owner_id: int) -> dict[int, int]:
    """Return ingredient ids mapped to how many recipes use them."""
    rows = await RecipeIngredient.filter(ingredient__owner_id=owner_id).values(
        "ingredient_id", "recipe_id"
    )
    recipes_by_ingredient: dict[int, set[int]] = defaultdict(set)
    for row in rows:
        recipes_by_ingredient[row["ingredient_id"]].add(row["recipe_id"])
    return {
        ingredient_id: len(recipe_ids)
        for ingredient_id, recipe_ids in recipes_by_ingredient.items()
    }


async def delete_unused_ingredient(owner_id: int, ingredient_id: int) -> bool:
    """Delete an ingredient that is not used in any recipe.

    Returns:
        ``True`` when the ingredient was deleted, ``False`` when it is missing
        or still referenced by at least one recipe.
    """
    ingredient = await Ingredient.get_or_none(id=ingredient_id, owner_id=owner_id)
    if ingredient is None:
        return False
    if await RecipeIngredient.filter(ingredient_id=ingredient_id).exists():
        return False
    await UserIngredientShop.filter(
        user_id=owner_id, ingredient_id=ingredient_id
    ).delete()
    await ingredient.delete()
    return True


async def ingredient_assignment_rows(owner_id: int) -> list[dict[str, object]]:
    """Return ingredients with their current shop assignment for management UI."""
    ingredients = await Ingredient.filter(owner_id=owner_id).order_by("name")
    shop_ids = await load_ingredient_shop_ids(owner_id)
    recipe_counts = await load_ingredient_recipe_counts(owner_id)
    rows: list[dict[str, object]] = []
    for ingredient in ingredients:
        rows.append(
            {
                "ingredient": ingredient,
                "shop_id": shop_ids.get(ingredient.id),
                "recipe_count": recipe_counts.get(ingredient.id, 0),
            }
        )
    return rows


class AssignmentGroup(TypedDict):
    """One shop bucket on the manage-shops assignments panel."""

    label: str
    shop: ShopInfo | None
    rows: list[dict[str, object]]


async def ingredient_assignment_groups(
    owner_id: int, shops: list[ShopInfo]
) -> list[AssignmentGroup]:
    """Return ingredient assignments grouped by shop, unassigned first."""
    rows = await ingredient_assignment_rows(owner_id)
    groups: list[AssignmentGroup] = []

    unassigned = [row for row in rows if row["shop_id"] is None]
    if unassigned:
        groups.append({"label": "Unassigned", "shop": None, "rows": unassigned})

    for shop in shops:
        assigned = [row for row in rows if row["shop_id"] == shop["id"]]
        if assigned:
            groups.append({"label": shop["name"], "shop": shop, "rows": assigned})

    return groups

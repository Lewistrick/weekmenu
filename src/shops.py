"""Per-user shop helpers and ingredient-to-shop assignments."""

from __future__ import annotations

from typing import TypedDict

from src.models import Ingredient, Shop, UserIngredientShop

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


async def ingredient_assignment_rows(owner_id: int) -> list[dict[str, object]]:
    """Return ingredients with their current shop assignment for management UI."""
    ingredients = await Ingredient.filter(owner_id=owner_id).order_by("name")
    shop_ids = await load_ingredient_shop_ids(owner_id)
    rows: list[dict[str, object]] = []
    for ingredient in ingredients:
        rows.append(
            {
                "ingredient": ingredient,
                "shop_id": shop_ids.get(ingredient.id),
            }
        )
    return rows

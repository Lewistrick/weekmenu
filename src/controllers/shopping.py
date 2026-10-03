"""In-shop page: walk through a shop shelf by shelf and fill a basket.

Putting an item in the basket never touches the inventory. What goes into the
inventory is decided afterwards, at home, on the unpack page.
"""

from typing import TypedDict

from litestar import Controller, Request, get, post
from litestar.exceptions import NotFoundException
from litestar.response import Redirect, Template
from litestar.status_codes import HTTP_303_SEE_OTHER
from loguru import logger

from src.auth import get_current_user
from src.categories import CategorySection, group_by_category
from src.grocery_data import (
    GrocerySplit,
    load_current_grocery_items,
    load_grocery_split,
)
from src.grocery_origins import load_ingredient_origins
from src.i18n.service import t
from src.inventory import add_stock
from src.plan_store import (
    delete_in_basket_lines,
    mark_in_basket_line,
    mark_to_check_line,
    unmark_in_basket_line,
)
from src.shops import ShopInfo
from src.url_path import path_with_base
from src.user_settings import load_user_settings
from src.week_menu import (
    GroceryItem,
    grocery_line_key,
    parse_grocery_quantity,
    set_grocery_action_flash,
)

NO_SHOP_REF = "none"


class ShopItem(TypedDict):
    """One line on the shop page."""

    ingredient_id: int
    name: str
    unit: str
    quantity: float
    in_basket: bool


class ShelfView(TypedDict):
    """One collapsible shelf on the shop page."""

    id: str
    name: str
    icon: str
    # Not "items": Jinja would resolve shelf.items to the dict method.
    lines: list[ShopItem]
    left: int
    open: bool


class ShopView(TypedDict):
    """Everything the shop page shows for one shop."""

    shop: ShopInfo | None
    ref: str
    shelves: list[ShelfView]
    total: int
    done: int


class ShopCard(TypedDict):
    """One shop on the picker page."""

    shop: ShopInfo | None
    ref: str
    view: ShopView


class UnpackLine(TypedDict):
    """One bought line on the unpack page."""

    ingredient_id: int
    name: str
    unit: str
    quantity: float
    include: bool


def _shelf_view(section: CategorySection, in_basket_line_keys: set[str]) -> ShelfView:
    """Turn a category section into a shelf: items left first, basket last."""
    items = [
        ShopItem(
            ingredient_id=entry["ingredient_id"],
            name=entry["name"],
            unit=entry["unit"],
            quantity=entry["quantity"],
            in_basket=grocery_line_key(entry["ingredient_id"], entry["unit"])
            in in_basket_line_keys,
        )
        for entry in section["entries"]
    ]
    items.sort(key=lambda item: (item["in_basket"], item["name"].lower()))
    left = sum(1 for item in items if not item["in_basket"])
    category_id = section["category_id"]
    return ShelfView(
        id="none" if category_id is None else f"c{category_id}",
        name=section["name"],
        icon=section["icon"],
        lines=items,
        left=left,
        open=left > 0,
    )


def _shop_entries(split: GrocerySplit, shop_ref: str) -> tuple[ShopInfo | None, list]:
    """Return the shop (``None`` for "no shop yet") and its grocery lines."""
    if shop_ref == NO_SHOP_REF:
        return None, split["unassigned_items"]
    try:
        shop_id = int(shop_ref)
    except ValueError as error:
        raise NotFoundException() from error
    for shop in split["shops"]:
        if shop["id"] == shop_id:
            group = next(
                (g for g in split["grocery_groups"] if g["shop_id"] == shop_id), None
            )
            return shop, group["entries"] if group is not None else []
    raise NotFoundException()


def _shop_view(split: GrocerySplit, shop_ref: str) -> ShopView:
    """Build the shop page content: shelves with their items and progress."""
    shop, entries = _shop_entries(split, shop_ref)
    sections = group_by_category(
        entries,
        split["ingredient_category_ids"],
        split["categories"],
        uncategorised_label=t("categories.uncategorised"),
        always=True,
    )
    shelves = [
        _shelf_view(section, split["in_basket_line_keys"]) for section in sections
    ]
    total = sum(len(shelf["lines"]) for shelf in shelves)
    left = sum(shelf["left"] for shelf in shelves)
    return ShopView(
        shop=shop, ref=shop_ref, shelves=shelves, total=total, done=total - left
    )


class ShoppingController(Controller):
    """Shop page, basket and unpack step."""

    path = "/shopping"
    tags = ["shopping"]

    @staticmethod
    async def _owner_id(request: Request) -> int:
        """Return the logged-in user's id or raise when unauthenticated."""
        user = await get_current_user(request)
        if user is None:
            raise NotFoundException()
        return user.id

    @staticmethod
    async def _split(user_id: int) -> GrocerySplit:
        """Load the user's current grocery list, split into lists."""
        return await load_grocery_split(
            user_id, await load_current_grocery_items(user_id)
        )

    @get(summary="Pick a shop to go shopping in")
    async def picker_page(self, request: Request) -> Template:
        """Show the shops with how much is left to buy in each."""
        split = await self._split(await self._owner_id(request))
        shops_by_id = {shop["id"]: shop for shop in split["shops"]}
        cards = [
            ShopCard(
                shop=shops_by_id[group["shop_id"]],
                ref=str(group["shop_id"]),
                view=_shop_view(split, str(group["shop_id"])),
            )
            for group in split["grocery_groups"]
        ]
        if split["unassigned_items"]:
            cards.append(
                ShopCard(
                    shop=None, ref=NO_SHOP_REF, view=_shop_view(split, NO_SHOP_REF)
                )
            )
        return Template(
            template_name="shopping.html",
            context={
                "request": request,
                "cards": cards,
                "basket_count": len(split["in_basket_line_keys"]),
            },
        )

    @get(path="/shop/{shop_ref:str}", summary="Walk through one shop")
    async def shop_page(self, request: Request, shop_ref: str) -> Template:
        """Show one shop's items by shelf, with a basket."""
        split = await self._split(await self._owner_id(request))
        return Template(
            template_name="shop-walk.html",
            context={
                "request": request,
                "view": _shop_view(split, shop_ref),
                "basket_count": len(split["in_basket_line_keys"]),
            },
        )

    async def _shelf_response(
        self, request: Request, user_id: int, shop_ref: str, shelf_id: str
    ) -> Template | Redirect:
        """Re-render one shelf, plus the progress bar (htmx), or go back (no JS)."""
        if not request.headers.get("HX-Request"):
            return Redirect(
                path=path_with_base(f"/shopping/shop/{shop_ref}"),
                status_code=HTTP_303_SEE_OTHER,
            )
        view = _shop_view(await self._split(user_id), shop_ref)
        shelf = next((s for s in view["shelves"] if s["id"] == shelf_id), None)
        # No such shelf any more (its last item moved away): the update then
        # swaps the shelf's element for nothing.
        return Template(
            template_name="partials/shopping-shelf-update.html",
            context={"request": request, "shelf": shelf, "view": view},
        )

    @staticmethod
    async def _form_line(request: Request) -> tuple[int, str, str, str]:
        """Read ``ingredient_id``, ``unit``, ``shop_ref`` and ``shelf_id``."""
        form_data = await request.form()
        try:
            ingredient_id = int(form_data.get("ingredient_id", 0))
        except ValueError as error:
            raise NotFoundException() from error
        unit = str(form_data.get("unit", "")).strip()
        shop_ref = str(form_data.get("shop_ref", NO_SHOP_REF)).strip() or NO_SHOP_REF
        shelf_id = str(form_data.get("shelf_id", "")).strip()
        return ingredient_id, unit, shop_ref, shelf_id

    @post(path="/basket", summary="Put a line in the basket, or take it out")
    async def toggle_basket(self, request: Request) -> Template | Redirect:
        """Toggle one grocery line in the basket; the inventory is never touched."""
        user_id = await self._owner_id(request)
        form_data = await request.form()
        ingredient_id, unit, shop_ref, shelf_id = await self._form_line(request)
        if str(form_data.get("in_basket", "")) == "1":
            await mark_in_basket_line(user_id, ingredient_id, unit)
        else:
            await unmark_in_basket_line(user_id, ingredient_id, unit)
        return await self._shelf_response(request, user_id, shop_ref, shelf_id)

    @post(path="/to-check", summary="Move a line to the to-check list")
    async def move_to_check(self, request: Request) -> Template | Redirect:
        """Can't find it? Send the line to the to-check list."""
        user_id = await self._owner_id(request)
        ingredient_id, unit, shop_ref, shelf_id = await self._form_line(request)
        await mark_to_check_line(user_id, ingredient_id, unit)
        return await self._shelf_response(request, user_id, shop_ref, shelf_id)

    async def _unpack_lines(self, user_id: int) -> list[UnpackLine]:
        """The lines in the basket, with unpack defaults from where they came from."""
        split = await self._split(user_id)
        in_basket = split["in_basket_line_keys"]
        if not in_basket:
            return []
        origins = await load_ingredient_origins(
            user_id, (await load_user_settings(user_id))["servings"]
        )
        entries: list[GroceryItem] = [
            *split["unassigned_items"],
            *(entry for group in split["grocery_groups"] for entry in group["entries"]),
        ]
        lines = []
        for entry in entries:
            if grocery_line_key(entry["ingredient_id"], entry["unit"]) not in in_basket:
                continue
            origin = origins.get(entry["ingredient_id"])
            # Staples start ticked; anything that is also in a recipe does not.
            weekly_only = bool(
                origin and origin["from_weekly"] and not origin["recipe_names"]
            )
            lines.append(
                UnpackLine(
                    ingredient_id=entry["ingredient_id"],
                    name=entry["name"],
                    unit=entry["unit"],
                    quantity=entry["quantity"],
                    include=weekly_only,
                )
            )
        return sorted(lines, key=lambda line: line["name"].lower())

    @get(path="/unpack", summary="Unpack what you bought")
    async def unpack_page(self, request: Request) -> Template:
        """List the basket so the user can pick what goes into the inventory."""
        return Template(
            template_name="shopping-unpack.html",
            context={
                "request": request,
                "lines": await self._unpack_lines(await self._owner_id(request)),
            },
        )

    @post(path="/unpack", summary="Add ticked lines to the inventory, clear the basket")
    async def unpack(self, request: Request) -> Redirect:
        """Add the ticked lines to the inventory and remove the listed lines."""
        user_id = await self._owner_id(request)
        form_data = await request.form()
        try:
            count = int(form_data.get("line_count", 0))
        except ValueError as error:
            raise NotFoundException() from error
        added = 0
        listed: set[str] = set()
        for index in range(count):
            try:
                ingredient_id = int(form_data.get(f"ingredient_id_{index}", 0))
            except ValueError:
                continue
            unit = str(form_data.get(f"unit_{index}", "")).strip()
            listed.add(grocery_line_key(ingredient_id, unit))
            quantity = parse_grocery_quantity(form_data.get(f"quantity_{index}"))
            if form_data.get(f"include_{index}") and quantity is not None:
                if await add_stock(user_id, ingredient_id, unit, quantity):
                    added += 1
        # Only the lines that were on the page are removed: one put in the basket
        # in the meantime (another tab) stays until it is unpacked.
        cleared = await delete_in_basket_lines(user_id, listed)
        logger.info(f"Unpacked basket: {added} to inventory, {cleared} cleared")
        set_grocery_action_flash(
            request, t("message.shopping.unpacked", added=added, cleared=cleared)
        )
        return Redirect(
            path=path_with_base("/week-menu/grocery-list"),
            status_code=HTTP_303_SEE_OTHER,
        )

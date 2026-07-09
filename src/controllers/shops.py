"""Shop management and ingredient-to-shop assignment endpoints."""

from litestar import Controller, Request, delete, get, post
from litestar.exceptions import NotFoundException
from litestar.response import Template
from loguru import logger

from src.auth import get_current_user
from src.models import Ingredient, Shop
from src.shops import (
    delete_unused_ingredient,
    get_or_create_shop,
    ingredient_assignment_groups,
    load_shops,
    set_ingredient_shop,
)


def _parse_color(value: object, *, fallback: str) -> str:
    """Return a normalized hex color from form data."""
    text = str(value or "").strip()
    if len(text) == 7 and text.startswith("#"):
        return text.lower()
    return fallback


class ShopController(Controller):
    """Manage shops and assign ingredients to them."""

    path = "/shops"
    tags = ["shops"]

    @staticmethod
    async def _owner_id(request: Request) -> int:
        """Return the logged-in user's id or raise when unauthenticated."""
        user = await get_current_user(request)
        if user is None:
            raise NotFoundException()
        return user.id

    @staticmethod
    async def _owned_shop(request: Request, shop_id: int) -> Shop:
        """Return a shop owned by the current user."""
        owner_id = await ShopController._owner_id(request)
        shop = await Shop.get_or_none(id=shop_id, owner_id=owner_id)
        if shop is None:
            raise NotFoundException()
        return shop

    @staticmethod
    async def _owned_ingredient(request: Request, ingredient_id: int) -> Ingredient:
        """Return an ingredient owned by the current user."""
        owner_id = await ShopController._owner_id(request)
        ingredient = await Ingredient.get_or_none(id=ingredient_id, owner_id=owner_id)
        if ingredient is None:
            raise NotFoundException()
        return ingredient

    async def _build_manage_context(
        self,
        request: Request,
        *,
        messages: list[str] | None = None,
        warnings: list[str] | None = None,
    ) -> dict[str, object]:
        """Build template context for the shop management page."""
        owner_id = await self._owner_id(request)
        shops = await load_shops(owner_id)
        return {
            "request": request,
            "shops": shops,
            "assignment_groups": await ingredient_assignment_groups(owner_id, shops),
            "messages": messages or [],
            "warnings": warnings or [],
        }

    async def _render_manage_page(
        self,
        request: Request,
        *,
        messages: list[str] | None = None,
        warnings: list[str] | None = None,
    ) -> Template:
        """Render the shop management page."""
        return Template(
            template_name="manage-shops.html",
            context=await self._build_manage_context(
                request, messages=messages, warnings=warnings
            ),
        )

    async def _render_assignments_partial(self, request: Request) -> Template:
        """Render only the ingredient assignments section for HTMX swaps."""
        owner_id = await self._owner_id(request)
        shops = await load_shops(owner_id)
        return Template(
            template_name="partials/manage-shop-assignments.html",
            context={
                "request": request,
                "shops": shops,
                "assignment_groups": await ingredient_assignment_groups(
                    owner_id, shops
                ),
            },
        )

    @get(path="/manage", summary="Manage shops")
    async def manage_page(self, request: Request) -> Template:
        """Show shops and ingredient-to-shop assignments."""
        return await self._render_manage_page(request)

    @post(summary="Create a shop")
    async def create_shop(self, request: Request) -> Template:
        """Create a new shop for the current user."""
        owner_id = await self._owner_id(request)
        form_data = await request.form()
        shop_name = str(form_data.get("shop_name", "")).strip()
        if not shop_name:
            return await self._render_manage_page(
                request, warnings=["Shop name is required."]
            )
        if await Shop.filter(owner_id=owner_id, name=shop_name).exists():
            return await self._render_manage_page(
                request, warnings=["That shop already exists."]
            )
        await get_or_create_shop(
            owner_id,
            shop_name,
            foreground_color=_parse_color(
                form_data.get("foreground_color"), fallback="#ffffff"
            ),
            background_color=_parse_color(
                form_data.get("background_color"), fallback="#2563eb"
            ),
        )
        logger.info(f"Created shop: {shop_name}")
        return await self._render_manage_page(request, messages=["Shop added."])

    @post(path="/{shop_id:int}", summary="Rename a shop")
    async def rename_shop(self, request: Request, shop_id: int) -> Template:
        """Rename an owned shop."""
        owner_id = await self._owner_id(request)
        shop = await self._owned_shop(request, shop_id)
        form_data = await request.form()
        shop_name = str(form_data.get("shop_name", "")).strip()
        if not shop_name:
            return await self._render_manage_page(
                request, warnings=["Shop name is required."]
            )
        duplicate = (
            await Shop.filter(owner_id=owner_id, name=shop_name)
            .exclude(id=shop_id)
            .first()
        )
        if duplicate is not None:
            return await self._render_manage_page(
                request, warnings=["That shop name is already in use."]
            )
        shop.name = shop_name
        shop.foreground_color = _parse_color(
            form_data.get("foreground_color"), fallback=shop.foreground_color
        )
        shop.background_color = _parse_color(
            form_data.get("background_color"), fallback=shop.background_color
        )
        await shop.save()
        return await self._render_manage_page(request, messages=["Shop updated."])

    @delete(path="/{shop_id:int}", summary="Delete a shop", status_code=200)
    async def delete_shop(self, request: Request, shop_id: int) -> Template:
        """Delete an owned shop."""
        shop = await self._owned_shop(request, shop_id)
        await shop.delete()
        return await self._render_manage_page(request, messages=["Shop deleted."])

    @post(path="/assignments", summary="Assign ingredient to shop")
    async def assign_ingredient(self, request: Request) -> Template:
        """Assign or clear the shop for one ingredient."""
        owner_id = await self._owner_id(request)
        form_data = await request.form()
        ingredient_id = int(form_data.get("ingredient_id", 0))
        shop_value = str(form_data.get("shop_id", "")).strip()
        ingredient = await self._owned_ingredient(request, ingredient_id)

        shop_id: int | None
        if not shop_value:
            shop_id = None
        else:
            shop_id = int(shop_value)
            if await Shop.get_or_none(id=shop_id, owner_id=owner_id) is None:
                raise NotFoundException()

        await set_ingredient_shop(owner_id, ingredient.id, shop_id)
        if request.headers.get("HX-Request"):
            return await self._render_assignments_partial(request)
        return await self._render_manage_page(request, messages=["Assignment saved."])

    @delete(
        path="/ingredients/{ingredient_id:int}",
        summary="Delete unused ingredient",
        status_code=200,
    )
    async def delete_ingredient(self, request: Request, ingredient_id: int) -> Template:
        """Delete an owned ingredient that is not used in any recipe."""
        owner_id = await self._owner_id(request)
        deleted = await delete_unused_ingredient(owner_id, ingredient_id)
        if not deleted:
            raise NotFoundException()
        logger.info(f"Deleted unused ingredient: {ingredient_id}")
        if request.headers.get("HX-Request"):
            return await self._render_assignments_partial(request)
        return await self._render_manage_page(request, messages=["Ingredient deleted."])

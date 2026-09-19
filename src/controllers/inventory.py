"""Inventory management endpoints."""

from litestar import Controller, Request, delete, get, post
from litestar.exceptions import NotFoundException
from litestar.response import Template
from loguru import logger

from src.auth import get_current_user
from src.i18n.service import t
from src.inventory import (
    INVENTORY_SORTS,
    add_inventory_item,
    delete_inventory_item,
    load_inventory,
    normalize_inventory_sort,
    update_inventory_item,
)
from src.models import Unit


class InventoryController(Controller):
    """Manage what a user has in stock at home."""

    path = "/inventory"
    tags = ["inventory"]

    @staticmethod
    async def _owner_id(request: Request) -> int:
        """Return the logged-in user's id or raise when unauthenticated."""
        user = await get_current_user(request)
        if user is None:
            raise NotFoundException()
        return user.id

    async def _render_page(
        self,
        request: Request,
        *,
        sort: object = None,
        messages: list[str] | None = None,
        warnings: list[str] | None = None,
    ) -> Template:
        """Render the inventory management page."""
        owner_id = await self._owner_id(request)
        active_sort = normalize_inventory_sort(sort)
        return Template(
            template_name="manage-inventory.html",
            context={
                "request": request,
                "inventory_items": await load_inventory(owner_id, active_sort),
                "units": await Unit.filter(owner_id=owner_id).order_by("abbrev"),
                "sort": active_sort,
                "sort_options": INVENTORY_SORTS,
                "messages": messages or [],
                "warnings": warnings or [],
            },
        )

    @get(summary="Manage inventory")
    async def manage_page(self, request: Request) -> Template:
        """Show the user's inventory in the requested order."""
        return await self._render_page(request, sort=request.query_params.get("sort"))

    @post(summary="Add an inventory item")
    async def create_inventory_item(self, request: Request) -> Template:
        """Add stock, merging into an existing ingredient/unit item."""
        owner_id = await self._owner_id(request)
        form_data = await request.form()
        success, message = await add_inventory_item(
            owner_id,
            form_data.get("ingredient"),
            form_data.get("quantity"),
            form_data.get("unit"),
        )
        sort = form_data.get("sort")
        if not success:
            return await self._render_page(request, sort=sort, warnings=[message])
        logger.info("Inventory item added")
        return await self._render_page(request, sort=sort, messages=[message])

    @post(path="/{item_id:int}", summary="Update an inventory item")
    async def edit_inventory_item(self, request: Request, item_id: int) -> Template:
        """Update an owned inventory item, merging duplicates."""
        owner_id = await self._owner_id(request)
        form_data = await request.form()
        success, message = await update_inventory_item(
            owner_id,
            item_id,
            form_data.get("ingredient"),
            form_data.get("quantity"),
            form_data.get("unit"),
        )
        sort = form_data.get("sort")
        if not success:
            return await self._render_page(request, sort=sort, warnings=[message])
        return await self._render_page(request, sort=sort, messages=[message])

    @delete(path="/{item_id:int}", summary="Delete an inventory item", status_code=200)
    async def remove_inventory_item(self, request: Request, item_id: int) -> Template:
        """Delete an owned inventory item."""
        owner_id = await self._owner_id(request)
        if not await delete_inventory_item(owner_id, item_id):
            raise NotFoundException()
        logger.info(f"Deleted inventory item: {item_id}")
        return await self._render_page(
            request,
            sort=request.query_params.get("sort"),
            messages=[t("message.inventory.deleted")],
        )

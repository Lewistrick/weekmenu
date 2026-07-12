"""Weekly grocery management endpoints (settings page)."""

from litestar import Controller, Request, delete, get, post
from litestar.exceptions import NotFoundException
from litestar.response import Template
from loguru import logger

from src.auth import get_current_user
from src.i18n.service import t
from src.models import Unit
from src.weekly_groceries import (
    add_weekly_grocery,
    delete_weekly_grocery,
    load_weekly_groceries,
    update_weekly_grocery,
)


class WeeklyGroceryController(Controller):
    """Manage a per-user list of recurring weekly groceries."""

    path = "/weekly-groceries"
    tags = ["weekly-groceries"]

    @staticmethod
    async def _owner_id(request: Request) -> int:
        """Return the logged-in user's id or raise when unauthenticated."""
        user = await get_current_user(request)
        if user is None:
            raise NotFoundException()
        return user.id

    async def _build_context(
        self,
        request: Request,
        *,
        messages: list[str] | None = None,
        warnings: list[str] | None = None,
    ) -> dict[str, object]:
        """Build template context for the weekly groceries page."""
        owner_id = await self._owner_id(request)
        return {
            "request": request,
            "weekly_groceries": await load_weekly_groceries(owner_id),
            "units": await Unit.filter(owner_id=owner_id).order_by("abbrev"),
            "messages": messages or [],
            "warnings": warnings or [],
        }

    async def _render_page(
        self,
        request: Request,
        *,
        messages: list[str] | None = None,
        warnings: list[str] | None = None,
    ) -> Template:
        """Render the weekly groceries management page."""
        return Template(
            template_name="manage-weekly-groceries.html",
            context=await self._build_context(
                request, messages=messages, warnings=warnings
            ),
        )

    @get(path="/manage", summary="Manage weekly groceries")
    async def manage_page(self, request: Request) -> Template:
        """Show the weekly groceries the user buys every week."""
        return await self._render_page(request)

    @post(summary="Add a weekly grocery")
    async def create_weekly_grocery(self, request: Request) -> Template:
        """Create a weekly grocery for the current user."""
        owner_id = await self._owner_id(request)
        form_data = await request.form()
        success, message = await add_weekly_grocery(
            owner_id,
            form_data.get("ingredient"),
            form_data.get("quantity"),
            form_data.get("unit"),
        )
        if not success:
            return await self._render_page(request, warnings=[message])
        logger.info("Weekly grocery added")
        return await self._render_page(request, messages=[message])

    @post(path="/{weekly_id:int}", summary="Update a weekly grocery")
    async def edit_weekly_grocery(self, request: Request, weekly_id: int) -> Template:
        """Update an owned weekly grocery."""
        owner_id = await self._owner_id(request)
        form_data = await request.form()
        success, message = await update_weekly_grocery(
            owner_id,
            weekly_id,
            form_data.get("ingredient"),
            form_data.get("quantity"),
            form_data.get("unit"),
        )
        if not success:
            return await self._render_page(request, warnings=[message])
        return await self._render_page(request, messages=[message])

    @delete(path="/{weekly_id:int}", summary="Delete a weekly grocery", status_code=200)
    async def remove_weekly_grocery(self, request: Request, weekly_id: int) -> Template:
        """Delete an owned weekly grocery."""
        owner_id = await self._owner_id(request)
        if not await delete_weekly_grocery(owner_id, weekly_id):
            raise NotFoundException()
        logger.info(f"Deleted weekly grocery: {weekly_id}")
        return await self._render_page(
            request, messages=[t("message.weekly_groceries.deleted")]
        )

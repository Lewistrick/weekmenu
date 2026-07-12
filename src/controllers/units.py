"""Unit management endpoints (settings page)."""

from litestar import Controller, Request, delete, get, post
from litestar.exceptions import NotFoundException
from litestar.response import Template
from loguru import logger

from src.auth import get_current_user
from src.i18n.service import t
from src.units import add_unit, delete_unit, load_units, update_unit


class UnitController(Controller):
    """Manage measurement units for the logged-in user."""

    path = "/units"
    tags = ["units"]

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
        """Build template context for the units management page."""
        owner_id = await self._owner_id(request)
        return {
            "request": request,
            "units": await load_units(owner_id),
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
        """Render the units management page."""
        return Template(
            template_name="manage-units.html",
            context=await self._build_context(
                request, messages=messages, warnings=warnings
            ),
        )

    @get(path="/manage", summary="Manage units")
    async def manage_page(self, request: Request) -> Template:
        """Show units and their abbreviation, singular, and plural labels."""
        return await self._render_page(request)

    @post(summary="Add a unit")
    async def create_unit(self, request: Request) -> Template:
        """Create a unit for the current user."""
        owner_id = await self._owner_id(request)
        form_data = await request.form()
        success, message = await add_unit(
            owner_id,
            form_data.get("abbrev"),
            form_data.get("single"),
            form_data.get("plural"),
        )
        if not success:
            return await self._render_page(request, warnings=[message])
        logger.info("Unit added")
        return await self._render_page(request, messages=[message])

    @post(path="/{unit_id:int}", summary="Update a unit")
    async def edit_unit(self, request: Request, unit_id: int) -> Template:
        """Update an owned unit."""
        owner_id = await self._owner_id(request)
        form_data = await request.form()
        success, message = await update_unit(
            owner_id,
            unit_id,
            form_data.get("abbrev"),
            form_data.get("single"),
            form_data.get("plural"),
        )
        if not success:
            if message == t("message.units.not_found"):
                raise NotFoundException()
            return await self._render_page(request, warnings=[message])
        return await self._render_page(request, messages=[message])

    @delete(path="/{unit_id:int}", summary="Delete a unit", status_code=200)
    async def remove_unit(self, request: Request, unit_id: int) -> Template:
        """Delete an owned unit that is not in use."""
        owner_id = await self._owner_id(request)
        success, message = await delete_unit(owner_id, unit_id)
        if not success:
            if message == t("message.units.not_found"):
                raise NotFoundException()
            return await self._render_page(request, warnings=[message])
        logger.info(f"Deleted unit: {unit_id}")
        return await self._render_page(request, messages=[message])

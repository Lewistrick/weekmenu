"""Ingredient category management endpoints (settings page)."""

from litestar import Controller, Request, delete, get, post
from litestar.exceptions import NotFoundException
from litestar.response import Response, Template
from litestar.status_codes import HTTP_204_NO_CONTENT, HTTP_409_CONFLICT
from loguru import logger

from src.auth import get_current_user
from src.categories import (
    add_category,
    delete_category,
    ensure_default_categories,
    load_assignment_groups,
    load_categories,
    reorder_categories,
    set_ingredient_category,
    update_category,
)
from src.i18n.service import t


class CategoryController(Controller):
    """Manage a user's ingredient categories and which ingredient has which."""

    path = "/categories"
    tags = ["categories"]

    @staticmethod
    async def _owner_id(request: Request) -> int:
        """Return the logged-in user's id or raise when unauthenticated."""
        user = await get_current_user(request)
        if user is None:
            raise NotFoundException()
        return user.id

    @staticmethod
    async def _assignment_context(owner_id: int) -> dict[str, object]:
        """Build the context shared by the page and the assignments partial."""
        categories = await load_categories(owner_id)
        return {
            "categories": categories,
            "assignment_groups": await load_assignment_groups(owner_id, categories),
        }

    async def _render_page(
        self,
        request: Request,
        *,
        messages: list[str] | None = None,
        warnings: list[str] | None = None,
    ) -> Template:
        """Render the categories management page."""
        owner_id = await self._owner_id(request)
        return Template(
            template_name="manage-categories.html",
            context={
                "request": request,
                **await self._assignment_context(owner_id),
                "messages": messages or [],
                "warnings": warnings or [],
            },
        )

    @get(path="/manage", summary="Manage ingredient categories")
    async def manage_page(self, request: Request) -> Template:
        """Show the categories, seeding the starter set on the first visit."""
        owner_id = await self._owner_id(request)
        if await ensure_default_categories(owner_id):
            logger.info("Seeded default ingredient categories")
        return await self._render_page(request)

    @post(summary="Add an ingredient category")
    async def create_category(self, request: Request) -> Template:
        """Add a category at the end of the order."""
        owner_id = await self._owner_id(request)
        form_data = await request.form()
        success, message = await add_category(
            owner_id, form_data.get("name"), form_data.get("icon")
        )
        if not success:
            return await self._render_page(request, warnings=[message])
        return await self._render_page(request, messages=[message])

    @post(path="/{category_id:int}", summary="Rename an ingredient category")
    async def edit_category(self, request: Request, category_id: int) -> Template:
        """Rename an owned category."""
        owner_id = await self._owner_id(request)
        form_data = await request.form()
        success, message = await update_category(
            owner_id, category_id, form_data.get("name"), form_data.get("icon")
        )
        if not success:
            return await self._render_page(request, warnings=[message])
        return await self._render_page(request, messages=[message])

    @post(path="/order", summary="Reorder ingredient categories")
    async def reorder(self, request: Request) -> Response:
        """Save the order of all categories after a drag (``ids`` = "3,1,2")."""
        owner_id = await self._owner_id(request)
        form_data = await request.form()
        try:
            category_ids = [
                int(part)
                for part in str(form_data.get("ids", "")).split(",")
                if part.strip()
            ]
        except ValueError as error:
            raise NotFoundException() from error
        if not await reorder_categories(owner_id, category_ids):
            # Stale page (a category was added or removed elsewhere): the
            # page reloads to show the current list.
            return Response(content="", status_code=HTTP_409_CONFLICT)
        return Response(content="", status_code=HTTP_204_NO_CONTENT)

    @delete(
        path="/{category_id:int}",
        summary="Delete an ingredient category",
        status_code=200,
    )
    async def remove_category(self, request: Request, category_id: int) -> Template:
        """Delete an owned category; its ingredients become uncategorised."""
        owner_id = await self._owner_id(request)
        if not await delete_category(owner_id, category_id):
            raise NotFoundException()
        logger.info(f"Deleted ingredient category: {category_id}")
        return await self._render_page(
            request, messages=[t("message.categories.deleted")]
        )

    @post(
        path="/ingredient/{ingredient_id:int}",
        summary="Set an ingredient's category",
    )
    async def assign_ingredient(self, request: Request, ingredient_id: int) -> Template:
        """Assign or clear one ingredient's category; re-render the assignments."""
        owner_id = await self._owner_id(request)
        form_data = await request.form()
        raw = str(form_data.get("category_id", "")).strip()
        try:
            category_id = int(raw) if raw else None
        except ValueError as error:
            raise NotFoundException() from error
        if not await set_ingredient_category(owner_id, ingredient_id, category_id):
            raise NotFoundException()
        return Template(
            template_name="partials/category-assignments.html",
            context={"request": request, **await self._assignment_context(owner_id)},
        )

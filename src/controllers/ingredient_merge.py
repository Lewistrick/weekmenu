"""Ingredient merge management endpoints."""

from litestar import Controller, Request, get, post
from litestar.exceptions import NotFoundException
from litestar.response import Template

from src.auth import get_current_user
from src.i18n.service import t
from src.ingredient_merge import (
    IngredientMergeResult,
    load_ingredient_options,
    log_ingredient_usages,
    merge_ingredients,
    search_ingredient_options,
)
from src.models import Ingredient


class IngredientMergeController(Controller):
    """Merge ingredients that share the same meaning but different names."""

    path = "/ingredients/merge"
    tags = ["ingredients"]

    _FIELD_LABELS = {
        "source": "ingredient_merge.form.source",
        "target": "ingredient_merge.form.target",
    }

    @staticmethod
    async def _owner_id(request: Request) -> int:
        """Return the logged-in user's id or raise when unauthenticated."""
        user = await get_current_user(request)
        if user is None:
            raise NotFoundException()
        return user.id

    @staticmethod
    async def _ingredient_name(owner_id: int, ingredient_id: int | None) -> str:
        """Return the display name for a selected ingredient id."""
        if ingredient_id is None:
            return ""
        ingredient = await Ingredient.get_or_none(id=ingredient_id, owner_id=owner_id)
        return ingredient.name if ingredient is not None else ""

    async def _build_context(
        self,
        request: Request,
        *,
        merge_result: IngredientMergeResult | None = None,
        warnings: list[str] | None = None,
        selected_source_id: int | None = None,
        selected_target_id: int | None = None,
    ) -> dict[str, object]:
        """Build template context for the ingredient merge page."""
        owner_id = await self._owner_id(request)
        return {
            "request": request,
            "ingredients": await load_ingredient_options(owner_id),
            "merge_result": merge_result,
            "warnings": warnings or [],
            "selected_source_id": selected_source_id,
            "selected_target_id": selected_target_id,
            "selected_source_name": await self._ingredient_name(
                owner_id, selected_source_id
            ),
            "selected_target_name": await self._ingredient_name(
                owner_id, selected_target_id
            ),
        }

    async def _render_page(
        self,
        request: Request,
        *,
        merge_result: IngredientMergeResult | None = None,
        warnings: list[str] | None = None,
        selected_source_id: int | None = None,
        selected_target_id: int | None = None,
    ) -> Template:
        """Render the ingredient merge page."""
        return Template(
            template_name="manage-ingredient-merge.html",
            context=await self._build_context(
                request,
                merge_result=merge_result,
                warnings=warnings,
                selected_source_id=selected_source_id,
                selected_target_id=selected_target_id,
            ),
        )

    @get(path="/manage", summary="Merge ingredients by name")
    async def manage_page(self, request: Request) -> Template:
        """Show the form for merging two ingredients."""
        return await self._render_page(request)

    @get(path="/search", summary="Search ingredients for merge form")
    async def search_ingredients(
        self,
        request: Request,
        field: str,
        search: str | None = None,
    ) -> Template:
        """Return ingredient autocomplete results for one merge field."""
        if field not in self._FIELD_LABELS:
            raise NotFoundException()

        owner_id = await self._owner_id(request)
        query = (search or "").strip()
        ingredients = await search_ingredient_options(owner_id, query) if query else []
        return Template(
            template_name="partials/ingredient-merge-search-results.html",
            context={
                "field": field,
                "search": search or "",
                "ingredients": ingredients,
            },
        )

    @post(path="/select", summary="Select an ingredient from autocomplete")
    async def select_ingredient(self, request: Request) -> Template:
        """Log usages and populate the matching merge field."""
        form_data = await request.form()
        field = str(form_data.get("field", "")).strip()
        if field not in self._FIELD_LABELS:
            raise NotFoundException()

        try:
            ingredient_id = int(str(form_data.get("ingredient_id", "")).strip())
        except ValueError:
            raise NotFoundException() from None

        owner_id = await self._owner_id(request)
        ingredient = await Ingredient.get_or_none(id=ingredient_id, owner_id=owner_id)
        if ingredient is None:
            raise NotFoundException()

        await log_ingredient_usages(owner_id, ingredient_id, field)
        return Template(
            template_name="partials/ingredient-merge-select-response.html",
            context={
                "field": field,
                "label_key": self._FIELD_LABELS[field],
                "ingredient": ingredient,
            },
        )

    @post(summary="Merge two ingredients")
    async def merge(self, request: Request) -> Template:
        """Merge the source ingredient into the target ingredient."""
        owner_id = await self._owner_id(request)
        form_data = await request.form()

        try:
            source_ingredient_id = int(
                str(form_data.get("source_ingredient_id", "")).strip()
            )
            target_ingredient_id = int(
                str(form_data.get("target_ingredient_id", "")).strip()
            )
        except ValueError:
            return await self._render_page(
                request,
                warnings=[t("message.ingredient_merge.invalid_selection")],
            )

        result = await merge_ingredients(
            owner_id,
            source_ingredient_id,
            target_ingredient_id,
        )
        if not result.ok:
            return await self._render_page(
                request,
                warnings=[result.error_message],
                selected_source_id=source_ingredient_id,
                selected_target_id=target_ingredient_id,
            )

        return await self._render_page(
            request,
            merge_result=result,
            selected_source_id=None,
            selected_target_id=None,
        )

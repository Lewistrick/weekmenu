"""Ingredient unit merge management endpoints."""

from litestar import Controller, Request, get, post
from litestar.exceptions import NotFoundException
from litestar.response import Template

from src.auth import get_current_user
from src.i18n.service import t
from src.ingredient_units import (
    IngredientUnitConversionResult,
    IngredientUnitPairRow,
    convert_ingredient_unit,
    load_multi_unit_pairs,
    log_pair_usage_for_edit,
)


class IngredientUnitMergeController(Controller):
    """List and convert ingredients that use multiple units."""

    path = "/ingredients/merge-units"
    tags = ["ingredients"]

    @staticmethod
    async def _owner_id(request: Request) -> int:
        """Return the logged-in user's id or raise when unauthenticated."""
        user = await get_current_user(request)
        if user is None:
            raise NotFoundException()
        return user.id

    @staticmethod
    def _ordered_unit_ids(unit_a_id: int, unit_b_id: int) -> tuple[int, int]:
        """Return unit ids in ascending order for stable URLs."""
        return (
            (unit_a_id, unit_b_id) if unit_a_id < unit_b_id else (unit_b_id, unit_a_id)
        )

    async def _build_context(
        self,
        request: Request,
        *,
        conversion_result: IngredientUnitConversionResult | None = None,
        warnings: list[str] | None = None,
    ) -> dict[str, object]:
        """Build template context for the merge-units page."""
        owner_id = await self._owner_id(request)
        return {
            "request": request,
            "pairs": await load_multi_unit_pairs(owner_id),
            "conversion_result": conversion_result,
            "warnings": warnings or [],
        }

    async def _render_page(
        self,
        request: Request,
        *,
        conversion_result: IngredientUnitConversionResult | None = None,
        warnings: list[str] | None = None,
    ) -> Template:
        """Render the ingredient unit merge page."""
        return Template(
            template_name="manage-ingredient-units.html",
            context=await self._build_context(
                request,
                conversion_result=conversion_result,
                warnings=warnings,
            ),
        )

    async def _render_pair_row(
        self,
        request: Request,
        pair: IngredientUnitPairRow,
        *,
        conversion_result: IngredientUnitConversionResult | None = None,
    ) -> Template:
        """Render one ingredient/unit pair row."""
        return Template(
            template_name="partials/ingredient-unit-pair-row.html",
            context={
                "request": request,
                "pair": pair,
                "conversion_result": conversion_result,
            },
        )

    async def _get_pair_or_404(
        self,
        owner_id: int,
        ingredient_id: int,
        unit_a_id: int,
        unit_b_id: int,
    ) -> IngredientUnitPairRow:
        """Load a pair row or raise when it no longer exists."""
        pairs = await load_multi_unit_pairs(owner_id)
        ordered_a, ordered_b = self._ordered_unit_ids(unit_a_id, unit_b_id)
        for pair in pairs:
            if (
                pair.ingredient_id == ingredient_id
                and pair.unit_a.id == ordered_a
                and pair.unit_b.id == ordered_b
            ):
                return pair
        raise NotFoundException()

    @get(path="/manage", summary="Manage ingredient unit conversions")
    async def manage_page(self, request: Request) -> Template:
        """Show ingredients that use more than one unit."""
        return await self._render_page(request)

    @get(
        path="/{ingredient_id:int}/{unit_a_id:int}/{unit_b_id:int}/edit",
        summary="Edit ingredient unit conversion",
    )
    async def edit_form(
        self,
        request: Request,
        ingredient_id: int,
        unit_a_id: int,
        unit_b_id: int,
    ) -> Template:
        """Show the inline conversion form for one ingredient/unit pair."""
        owner_id = await self._owner_id(request)
        pair = await self._get_pair_or_404(
            owner_id, ingredient_id, unit_a_id, unit_b_id
        )
        await log_pair_usage_for_edit(owner_id, pair)
        return Template(
            template_name="partials/ingredient-unit-convert-form.html",
            context={
                "request": request,
                "pair": pair,
                "default_target_unit_id": pair.unit_b.id,
                "default_amount_a": "1",
                "default_amount_b": "1",
            },
        )

    @get(
        path="/{ingredient_id:int}/{unit_a_id:int}/{unit_b_id:int}",
        summary="Show ingredient unit pair row",
    )
    async def pair_row(
        self,
        request: Request,
        ingredient_id: int,
        unit_a_id: int,
        unit_b_id: int,
    ) -> Template:
        """Return the read-only row partial (cancel edit)."""
        owner_id = await self._owner_id(request)
        pair = await self._get_pair_or_404(
            owner_id, ingredient_id, unit_a_id, unit_b_id
        )
        return await self._render_pair_row(request, pair)

    @post(
        path="/{ingredient_id:int}/{unit_a_id:int}/{unit_b_id:int}",
        summary="Convert ingredient unit",
    )
    async def convert_units(
        self,
        request: Request,
        ingredient_id: int,
        unit_a_id: int,
        unit_b_id: int,
    ) -> Template:
        """Convert all uses of one unit to another for an ingredient."""
        owner_id = await self._owner_id(request)
        pair = await self._get_pair_or_404(
            owner_id, ingredient_id, unit_a_id, unit_b_id
        )
        form_data = await request.form()

        try:
            target_unit_id = int(str(form_data.get("target_unit_id", "")).strip())
            amount_a = float(str(form_data.get("amount_a", "")).strip())
            amount_b = float(str(form_data.get("amount_b", "")).strip())
        except ValueError:
            return Template(
                template_name="partials/ingredient-unit-convert-form.html",
                context={
                    "request": request,
                    "pair": pair,
                    "default_target_unit_id": int(
                        str(form_data.get("target_unit_id", pair.unit_b.id)).strip()
                        or pair.unit_b.id
                    ),
                    "default_amount_a": str(form_data.get("amount_a", "1")),
                    "default_amount_b": str(form_data.get("amount_b", "1")),
                    "warnings": [t("message.ingredient_units.invalid_amounts")],
                },
            )

        result = await convert_ingredient_unit(
            owner_id,
            ingredient_id,
            pair.unit_a.id,
            pair.unit_b.id,
            target_unit_id=target_unit_id,
            amount_a=amount_a,
            amount_b=amount_b,
        )
        if not result.ok:
            if request.headers.get("HX-Request"):
                return Template(
                    template_name="partials/ingredient-unit-convert-form.html",
                    context={
                        "request": request,
                        "pair": pair,
                        "default_target_unit_id": target_unit_id,
                        "default_amount_a": str(amount_a),
                        "default_amount_b": str(amount_b),
                        "warnings": [result.error_message],
                    },
                )
            return await self._render_page(request, warnings=[result.error_message])

        if request.headers.get("HX-Request"):
            remaining = await load_multi_unit_pairs(owner_id)
            ordered_a, ordered_b = self._ordered_unit_ids(
                pair.unit_a.id, pair.unit_b.id
            )
            for remaining_pair in remaining:
                if (
                    remaining_pair.ingredient_id == ingredient_id
                    and remaining_pair.unit_a.id == ordered_a
                    and remaining_pair.unit_b.id == ordered_b
                ):
                    return await self._render_pair_row(
                        request, remaining_pair, conversion_result=result
                    )
            return Template(
                template_name="partials/ingredient-unit-pair-empty.html",
                context={"request": request, "conversion_result": result},
            )

        return await self._render_page(request, conversion_result=result)

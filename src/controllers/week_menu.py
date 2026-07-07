"""Week menu planning endpoints."""

from collections import defaultdict

from litestar import Controller, Request, get, post
from litestar.exceptions import NotFoundException
from litestar.response import Template
from loguru import logger

from src.models import Recipe, RecipeTag, Tag, TagCategory
from src.week_menu import (
    TagGroupConstraint,
    build_day_rows,
    is_valid_day,
    load_tag_constraints,
    load_week_menu,
    load_start_day,
    ordered_week_days,
    parse_tag_constraints_from_form,
    randomize_week_menu,
    save_tag_constraints,
    save_week_menu,
    save_start_day,
    set_day_recipe,
    toggle_pin,
)


class WeekMenuController(Controller):
    """Plan dinners for each day of the week."""

    path = "/week-menu"
    tags = ["week-menu"]

    @staticmethod
    async def _tag_groups() -> list[dict]:
        """Load tag groups with values for the options panel."""
        categories = await TagCategory.all().order_by("name")
        groups: list[dict] = []
        for category in categories:
            tags = await Tag.filter(category_id=category.id).order_by("name")
            groups.append({"category": category, "tags": tags})
        return groups

    @staticmethod
    async def _category_ids() -> list[int]:
        """Return all tag group ids in display order."""
        categories = await TagCategory.all().order_by("name").only("id")
        return [category.id for category in categories]

    @staticmethod
    async def _recipe_tag_map(recipe_ids: list[int]) -> dict[int, dict[int, set[int]]]:
        """Map recipe ids to tag ids grouped by tag category."""
        if not recipe_ids:
            return {}

        rows = await RecipeTag.filter(recipe_id__in=recipe_ids).select_related(
            "tag", "recipe"
        )
        tag_map: dict[int, dict[int, set[int]]] = defaultdict(lambda: defaultdict(set))
        for recipe_tag in rows:
            tag_map[recipe_tag.recipe.id][recipe_tag.tag.category_id].add(
                recipe_tag.tag.id
            )
        return {
            recipe_id: dict(categories) for recipe_id, categories in tag_map.items()
        }

    @staticmethod
    def _constraint_for_category(
        constraints: list[TagGroupConstraint], category_id: int
    ) -> TagGroupConstraint | None:
        """Return the saved constraint for one tag group."""
        for constraint in constraints:
            if constraint["category_id"] == category_id:
                return constraint
        return None

    async def _page_context(
        self,
        request: Request,
        *,
        messages: list[str] | None = None,
        warnings: list[str] | None = None,
    ) -> dict:
        """Build template context shared by week menu renders."""
        menu = load_week_menu(request)
        start_day = load_start_day(request)
        tag_groups = await self._tag_groups()
        category_ids = [group["category"].id for group in tag_groups]
        constraints = load_tag_constraints(request, category_ids)
        recipe_ids = [
            slot["recipe_id"] for slot in menu.values() if slot["recipe_id"] is not None
        ]
        recipes_by_id = await self._recipes_by_id(recipe_ids)
        constraint_rows = []
        for group in tag_groups:
            category = group["category"]
            constraint_rows.append(
                {
                    "category": category,
                    "tags": group["tags"],
                    "constraint": self._constraint_for_category(
                        constraints, category.id
                    ),
                }
            )
        return {
            "request": request,
            "days": await build_day_rows(menu, recipes_by_id, start_day),
            "start_day": start_day,
            "day_options": ordered_week_days("monday"),
            "tag_constraint_rows": constraint_rows,
            "messages": messages or [],
            "warnings": warnings or [],
        }

    @staticmethod
    async def _recipes_by_id(recipe_ids: list[int]) -> dict[int, Recipe]:
        """Load recipes referenced by the week menu."""
        if not recipe_ids:
            return {}
        recipes = await Recipe.filter(id__in=recipe_ids)
        return {recipe.id: recipe for recipe in recipes}

    async def _render_page(self, request: Request) -> Template:
        """Render the full week menu page."""
        return await self._render_page_with_feedback(request)

    async def _render_page_with_feedback(
        self,
        request: Request,
        *,
        messages: list[str] | None = None,
        warnings: list[str] | None = None,
    ) -> Template:
        """Render the week menu content partial with optional feedback."""
        return Template(
            template_name="partials/week-menu-content.html",
            context=await self._page_context(
                request, messages=messages, warnings=warnings
            ),
        )

    async def _render_days(self, request: Request) -> Template:
        """Render the week menu day panel."""
        menu = load_week_menu(request)
        start_day = load_start_day(request)
        recipe_ids = [
            slot["recipe_id"] for slot in menu.values() if slot["recipe_id"] is not None
        ]
        recipes_by_id = await self._recipes_by_id(recipe_ids)
        return Template(
            template_name="partials/week-menu-days.html",
            context={
                "request": request,
                "days": await build_day_rows(menu, recipes_by_id, start_day),
            },
        )

    @get(summary="Week menu planner page")
    async def week_menu_page(self, request: Request) -> Template:
        """Show the week menu planner."""
        return Template(
            template_name="week-menu.html",
            context=await self._page_context(request),
        )

    @post(path="/constraints", summary="Save week menu tag constraints")
    async def save_constraints(self, request: Request) -> Template:
        """Persist tag constraint options and re-render the week menu."""
        form_data = await request.form()
        category_ids = await self._category_ids()
        constraints = parse_tag_constraints_from_form(dict(form_data), category_ids)
        save_tag_constraints(request, constraints)
        logger.info("Week menu tag constraints updated")
        return await self._render_page(request)

    @post(path="/start-day", summary="Set week start day")
    async def set_start_day(self, request: Request) -> Template:
        """Persist preferred first day and re-render week menu."""
        form_data = await request.form()
        day = str(form_data.get("start_day", "monday"))
        if not is_valid_day(day):
            raise NotFoundException()
        save_start_day(request, day)
        logger.info(f"Week menu start day updated to: {day}")
        return await self._render_page(request)

    @post(path="/randomize", summary="Randomize unpinned week menu days")
    async def randomize(self, request: Request) -> Template:
        """Pick random enabled recipes for all unpinned days."""
        menu = load_week_menu(request)
        if all(slot["pinned"] for slot in menu.values()):
            return await self._render_page_with_feedback(
                request,
                warnings=["All days are pinned. Unpin at least one day to randomize."],
            )
        category_ids = await self._category_ids()
        constraints = load_tag_constraints(request, category_ids)
        recipe_ids = [
            recipe.id
            for recipe in await Recipe.filter(enabled=True).only("id")
        ]
        recipe_tag_map = await self._recipe_tag_map(recipe_ids)
        menu, warnings = randomize_week_menu(
            menu,
            recipe_ids,
            constraints=constraints,
            recipe_tag_map=recipe_tag_map,
        )
        save_week_menu(request, menu)
        return await self._render_page_with_feedback(request, warnings=warnings)

    @post(path="/{day:str}/pin", summary="Toggle pin for a day")
    async def pin_day(self, request: Request, day: str) -> Template:
        """Toggle whether a day's recipe is kept when randomizing."""
        if not is_valid_day(day):
            raise NotFoundException()

        menu = load_week_menu(request)
        menu = toggle_pin(menu, day)
        save_week_menu(request, menu)
        return await self._render_days(request)

    @post(path="/{day:str}/recipe/{recipe_id:int}", summary="Assign recipe to day")
    async def assign_recipe(
        self, request: Request, day: str, recipe_id: int
    ) -> Template:
        """Set the recipe for a specific day."""
        if not is_valid_day(day):
            raise NotFoundException()

        recipe = await Recipe.get_or_none(id=recipe_id)
        if not recipe:
            raise NotFoundException()

        menu = load_week_menu(request)
        menu = set_day_recipe(menu, day, recipe_id)
        save_week_menu(request, menu)
        return await self._render_days(request)

    @post(path="/{day:str}/clear", summary="Clear recipe for day")
    async def clear_day(self, request: Request, day: str) -> Template:
        """Remove any selected recipe from a day."""
        if not is_valid_day(day):
            raise NotFoundException()

        menu = load_week_menu(request)
        menu = set_day_recipe(menu, day, None)
        save_week_menu(request, menu)
        return await self._render_days(request)

    @get(path="/{day:str}/search", summary="Search recipes for a day")
    async def search_for_day(
        self, request: Request, day: str, search: str | None = None
    ) -> Template:
        """Return recipe search results for assigning to a day."""
        if not is_valid_day(day):
            raise NotFoundException()

        recipes: list[Recipe] = []
        if search:
            recipes = await Recipe.search(search, limit=5)

        return Template(
            template_name="partials/week-menu-day-search-results.html",
            context={
                "request": request,
                "day": day,
                "recipes": recipes,
                "search": search or "",
            },
        )

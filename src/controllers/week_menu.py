"""Week menu planning endpoints."""

from litestar import Controller, Request, get, post
from litestar.exceptions import NotFoundException
from litestar.response import Template
from loguru import logger

from src.models import Recipe
from src.week_menu import (
    build_day_rows,
    is_valid_day,
    load_week_menu,
    load_start_day,
    ordered_week_days,
    randomize_week_menu,
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
    async def _recipes_by_id(recipe_ids: list[int]) -> dict[int, Recipe]:
        """Load recipes referenced by the week menu."""
        if not recipe_ids:
            return {}
        recipes = await Recipe.filter(id__in=recipe_ids)
        return {recipe.id: recipe for recipe in recipes}

    async def _render_page(self, request: Request) -> Template:
        """Render the full week menu page."""
        menu = load_week_menu(request)
        start_day = load_start_day(request)
        recipe_ids = [
            slot["recipe_id"] for slot in menu.values() if slot["recipe_id"] is not None
        ]
        recipes_by_id = await self._recipes_by_id(recipe_ids)
        return Template(
            template_name="week-menu.html",
            context={
                "request": request,
                "days": await build_day_rows(menu, recipes_by_id, start_day),
                "start_day": start_day,
                "day_options": ordered_week_days("monday"),
            },
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
        recipe_ids = await Recipe.filter(enabled=True).values_list("id", flat=True)
        menu = randomize_week_menu(menu, list(recipe_ids))
        save_week_menu(request, menu)
        return await self._render_days(request)

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
            recipes = await Recipe.search(search, limit=10)

        return Template(
            template_name="partials/week-menu-day-search-results.html",
            context={
                "request": request,
                "day": day,
                "recipes": recipes,
                "search": search or "",
            },
        )

"""Week menu planning endpoints."""

from collections import defaultdict

from litestar import Controller, Request, get, post
from litestar.exceptions import NotFoundException
from litestar.response import Redirect, Response, Template
from litestar.status_codes import HTTP_303_SEE_OTHER
from loguru import logger
from tortoise.expressions import Q

from src.auth import get_current_user
from src.catalog import get_or_create_ingredient
from src.grocery import (
    format_grocery_export,
    format_week_menu_export,
    split_grocery_lists,
)
from src.models import (
    Ingredient,
    Recipe,
    RecipeIngredient,
    RecipeTag,
    Tag,
    TagCategory,
    Unit,
)
from src.shops import load_ingredient_shop_ids, load_shops, set_ingredient_shop
from src.plan_store import (
    add_items_to_grocery_list,
    empty_already_have_list,
    empty_to_check_list,
    find_grocery_line_in_store,
    has_grocery_list_items,
    is_grocery_list_initialized,
    load_already_have_line_keys,
    load_grocery_list,
    load_grocery_line_shops,
    load_include_public,
    load_start_day,
    load_tag_constraints,
    load_to_check_line_keys,
    load_week_menu,
    mark_already_have_line,
    mark_shop_already_have,
    mark_to_check_line,
    prune_orphaned_grocery_lines,
    reset_grocery_plan,
    save_grocery_list,
    save_include_public,
    save_start_day,
    save_tag_constraints,
    save_week_menu,
    set_grocery_line_shop,
    unmark_already_have_line,
    unmark_to_check_line,
    update_grocery_line,
)
from src.user_settings import load_user_settings
from src.week_menu import (
    GroceryItem,
    TagGroupConstraint,
    build_day_rows,
    build_grocery_list,
    is_valid_day,
    move_day,
    normalize_servings,
    ordered_week_days,
    parse_tag_constraints_from_form,
    randomize_week_menu,
    hydrate_grocery_item_names,
    merge_grocery_items,
    parse_grocery_quantity,
    pop_grocery_action_flash,
    pop_grocery_suppress_preserve,
    scale_ingredient_quantity,
    set_day_recipe,
    set_day_servings,
    set_grocery_action_flash,
    set_grocery_suppress_preserve,
    toggle_pin,
)
from src.weekly_groceries import (
    weekly_groceries_as_items,
    weekly_groceries_missing_from_list,
)


class WeekMenuController(Controller):
    """Plan dinners for each day of the week."""

    path = "/week-menu"
    tags = ["week-menu"]

    @staticmethod
    async def _default_servings(request: Request) -> int:
        """Return the current user's preferred default servings."""
        user_id = await WeekMenuController._viewer_id(request)
        return (await load_user_settings(user_id))["servings"]

    @staticmethod
    async def _viewer_id(request: Request) -> int:
        """Return the logged-in user's id or raise when unauthenticated."""
        user = await get_current_user(request)
        if user is None:
            raise NotFoundException()
        return user.id

    @staticmethod
    def _visible_filter(user_id: int) -> Q:
        """Match recipes visible to a user: their own plus public recipes."""
        return Q(owner_id=user_id) | Q(private=False)

    @staticmethod
    def _wants_public(request: Request) -> bool:
        """Return whether the request opts in to including public recipes."""
        value = request.query_params.get("include_public")
        return value is not None and value.lower() in {"on", "1", "true", "yes"}

    @staticmethod
    def _form_wants_public(form_data: dict) -> bool:
        """Return whether form data opts in to including public recipes."""
        value = form_data.get("include_public")
        if value is None:
            return False
        return str(value).lower() in {"on", "1", "true", "yes"}

    @staticmethod
    async def _tag_groups(owner_id: int) -> list[dict]:
        """Load tag groups with values for the options panel."""
        categories = await TagCategory.filter(owner_id=owner_id).order_by("name")
        groups: list[dict] = []
        for category in categories:
            tags = await Tag.filter(
                owner_id=owner_id, category_id=category.id
            ).order_by("name")
            groups.append({"category": category, "tags": tags})
        return groups

    @staticmethod
    async def _category_ids(owner_id: int) -> list[int]:
        """Return all tag group ids in display order for one user."""
        categories = (
            await TagCategory.filter(owner_id=owner_id).order_by("name").only("id")
        )
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
        user_id = await self._viewer_id(request)
        default_servings = await self._default_servings(request)
        menu = await load_week_menu(user_id, default_servings=default_servings)
        start_day = await load_start_day(user_id)
        tag_groups = await self._tag_groups(user_id)
        category_ids = [group["category"].id for group in tag_groups]
        constraints = await load_tag_constraints(user_id, category_ids)
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
            "include_public": await load_include_public(user_id),
            "tag_constraint_rows": constraint_rows,
            "messages": messages or [],
            "warnings": warnings or [],
            "grocery_list_has_items": await has_grocery_list_items(user_id),
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
        user_id = await self._viewer_id(request)
        default_servings = await self._default_servings(request)
        menu = await load_week_menu(user_id, default_servings=default_servings)
        start_day = await load_start_day(user_id)
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

    async def _grocery_items_from_week_menu(
        self, request: Request
    ) -> list[GroceryItem]:
        """Build a fresh aggregated grocery list from the current week menu."""
        user_id = await self._viewer_id(request)
        default_servings = await self._default_servings(request)
        menu = await load_week_menu(user_id, default_servings=default_servings)
        recipe_ids = [
            slot["recipe_id"] for slot in menu.values() if slot["recipe_id"] is not None
        ]
        recipes_by_id = await self._recipes_by_id(recipe_ids)

        ingredients_by_recipe: dict[int, list[RecipeIngredient]] = defaultdict(list)
        if recipe_ids:
            recipe_ingredients = await RecipeIngredient.filter(
                recipe_id__in=recipe_ids
            ).select_related("recipe", "ingredient", "unit")
            for recipe_ingredient in recipe_ingredients:
                ingredients_by_recipe[recipe_ingredient.recipe.id].append(
                    recipe_ingredient
                )

        entries: list[GroceryItem] = []
        for slot in menu.values():
            recipe = recipes_by_id.get(slot["recipe_id"]) if slot["recipe_id"] else None
            if recipe is None:
                continue
            recipe_servings = normalize_servings(recipe.servings)
            for recipe_ingredient in ingredients_by_recipe.get(recipe.id, []):
                entries.append(
                    GroceryItem(
                        ingredient_id=recipe_ingredient.ingredient.id,
                        name=recipe_ingredient.ingredient.name,
                        unit=recipe_ingredient.unit.abbrev,
                        quantity=scale_ingredient_quantity(
                            recipe_ingredient.quantity,
                            slot["servings"],
                            recipe_servings,
                        ),
                    )
                )

        return build_grocery_list(entries)

    async def _build_grocery_context(
        self,
        request: Request,
        *,
        preserve_existing: bool = True,
        action_message: str | None = None,
        grocery_add_reset_form: bool = False,
    ) -> dict:
        """Build shared grocery-list context for HTML and plaintext export."""
        user_id = await self._viewer_id(request)
        default_servings = await self._default_servings(request)
        menu = await load_week_menu(user_id, default_servings=default_servings)
        start_day = await load_start_day(user_id)
        recipe_ids = [
            slot["recipe_id"] for slot in menu.values() if slot["recipe_id"] is not None
        ]
        recipes_by_id = await self._recipes_by_id(recipe_ids)

        grocery_message: str | None = None
        if preserve_existing and await is_grocery_list_initialized(user_id):
            grocery_items = await prune_orphaned_grocery_lines(
                user_id,
                await hydrate_grocery_item_names(
                    user_id, await load_grocery_list(user_id)
                ),
            )
            if grocery_items and not pop_grocery_suppress_preserve(request):
                grocery_message = (
                    "Your grocery list is preserved and was not regenerated "
                    "from the week menu."
                )
        else:
            grocery_items = await self._grocery_items_from_week_menu(request)
            await reset_grocery_plan(user_id)
            await save_grocery_list(user_id, grocery_items)

        if action_message is None:
            action_message = pop_grocery_action_flash(request)

        ingredient_shop_ids = await load_ingredient_shop_ids(user_id)
        shops = await load_shops(user_id)
        already_have_line_keys = await load_already_have_line_keys(user_id)
        to_check_line_keys = await load_to_check_line_keys(user_id)
        line_shop_ids = await load_grocery_line_shops(user_id)
        unassigned_items, to_check_items, already_have_items, grocery_groups = (
            split_grocery_lists(
                grocery_items,
                ingredient_shop_ids,
                shops,
                already_have_line_keys,
                to_check_line_keys,
                line_shop_ids,
            )
        )
        days = await build_day_rows(menu, recipes_by_id, start_day)
        units = await Unit.filter(owner_id=user_id).order_by("abbrev")
        return {
            "request": request,
            "days": days,
            "unassigned_items": unassigned_items,
            "to_check_items": to_check_items,
            "already_have_items": already_have_items,
            "grocery_groups": grocery_groups,
            "grocery_export_text": format_grocery_export(
                unassigned_items, to_check_items, grocery_groups
            ),
            "week_menu_export_text": format_week_menu_export(days),
            "shops": shops,
            "ingredient_shop_ids": ingredient_shop_ids,
            "line_shop_ids": line_shop_ids,
            "already_have_line_keys": already_have_line_keys,
            "to_check_line_keys": to_check_line_keys,
            "units": units,
            "grocery_message": grocery_message,
            "grocery_action_message": action_message,
            "grocery_add_reset_form": grocery_add_reset_form,
        }

    async def _grocery_add_response(
        self,
        request: Request,
        *,
        action_message: str | None = None,
        grocery_add_reset_form: bool = False,
    ) -> Template | Redirect:
        """Return an HTMX partial update or redirect after adding groceries."""
        if request.headers.get("HX-Request"):
            return Template(
                template_name="partials/grocery-list-htmx-update.html",
                context=await self._build_grocery_context(
                    request,
                    action_message=action_message,
                    grocery_add_reset_form=grocery_add_reset_form,
                ),
            )
        if action_message:
            set_grocery_action_flash(request, action_message)
        return Redirect(path="/week-menu/grocery-list", status_code=HTTP_303_SEE_OTHER)

    async def _render_grocery_panel(
        self, request: Request, *, action_message: str | None = None
    ) -> Template:
        """Render the sortable grocery list panel for HTMX swaps."""
        return Template(
            template_name="partials/grocery-list-panel.html",
            context=await self._build_grocery_context(
                request, action_message=action_message
            ),
        )

    async def _grocery_list_response(
        self, request: Request, *, action_message: str | None = None
    ) -> Template:
        """Return a partial or full grocery list response."""
        if request.headers.get("HX-Request"):
            return await self._render_grocery_panel(
                request, action_message=action_message
            )
        return await self._render_grocery_list(request, action_message=action_message)

    async def _refresh_grocery_list_response(
        self, request: Request, *, action_message: str | None = None
    ) -> Response | Template:
        """Return a full grocery list refresh, using HX-Refresh for HTMX requests."""
        if request.headers.get("HX-Request"):
            if action_message:
                set_grocery_action_flash(request, action_message)
            return Response(content="", status_code=200, headers={"HX-Refresh": "true"})
        return await self._render_grocery_list(request, action_message=action_message)

    async def _render_grocery_list(
        self, request: Request, *, action_message: str | None = None
    ) -> Template:
        """Render the grocery list page."""
        return Template(
            template_name="grocery-list.html",
            context=await self._build_grocery_context(
                request, action_message=action_message
            ),
        )

    async def _require_grocery_line(
        self, user_id: int, ingredient_id: int, unit: str
    ) -> GroceryItem:
        """Raise when a grocery line is not on the current list."""
        item = await find_grocery_line_in_store(user_id, ingredient_id, unit)
        if item is None:
            raise NotFoundException()
        return item

    @staticmethod
    async def _hydrated_grocery_line(
        user_id: int, ingredient_id: int, unit: str
    ) -> GroceryItem:
        """Return one grocery line from the database with a display name."""
        item = await find_grocery_line_in_store(user_id, ingredient_id, unit)
        if item is None:
            raise NotFoundException()
        return (await hydrate_grocery_item_names(user_id, [item]))[0]

    @staticmethod
    def _grocery_line_count_for_ingredient(
        items: list[GroceryItem], ingredient_id: int
    ) -> int:
        """Return how many grocery lines exist for one ingredient."""
        return sum(1 for item in items if item["ingredient_id"] == ingredient_id)

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
        user_id = await self._viewer_id(request)
        form_data = await request.form()
        category_ids = await self._category_ids(user_id)
        constraints = parse_tag_constraints_from_form(dict(form_data), category_ids)
        await save_tag_constraints(user_id, constraints)
        logger.info("Week menu tag constraints updated")
        return await self._render_page(request)

    @post(path="/start-day", summary="Set week start day")
    async def set_start_day(self, request: Request) -> Template:
        """Persist preferred first day and re-render week menu."""
        user_id = await self._viewer_id(request)
        form_data = await request.form()
        day = str(form_data.get("start_day", "monday"))
        if not is_valid_day(day):
            raise NotFoundException()
        await save_start_day(user_id, day)
        logger.info(f"Week menu start day updated to: {day}")
        return await self._render_page(request)

    @post(path="/randomize", summary="Randomize unpinned week menu days")
    async def randomize(self, request: Request) -> Template:
        """Pick random enabled recipes for all unpinned days."""
        user_id = await self._viewer_id(request)
        default_servings = await self._default_servings(request)
        menu = await load_week_menu(user_id, default_servings=default_servings)
        if all(slot["pinned"] for slot in menu.values()):
            return await self._render_page_with_feedback(
                request,
                warnings=["All days are pinned. Unpin at least one day to randomize."],
            )
        form_data = await request.form()
        include_public = self._form_wants_public(dict(form_data))
        await save_include_public(user_id, include_public)
        category_ids = await self._category_ids(user_id)
        constraints = await load_tag_constraints(user_id, category_ids)
        recipe_query = Recipe.filter(enabled=True)
        if include_public:
            recipe_query = recipe_query.filter(self._visible_filter(user_id))
        else:
            recipe_query = recipe_query.filter(owner_id=user_id)
        recipe_ids = [recipe.id for recipe in await recipe_query.only("id")]
        recipe_tag_map = await self._recipe_tag_map(recipe_ids)
        menu, warnings = randomize_week_menu(
            menu,
            recipe_ids,
            constraints=constraints,
            recipe_tag_map=recipe_tag_map,
        )
        logger.debug("Randomized week menu, saving...")
        await save_week_menu(user_id, menu)
        return await self._render_page_with_feedback(request, warnings=warnings)

    @post(path="/{day:str}/pin", summary="Toggle pin for a day")
    async def pin_day(self, request: Request, day: str) -> Template:
        """Toggle whether a day's recipe is kept when randomizing."""
        if not is_valid_day(day):
            raise NotFoundException()

        user_id = await self._viewer_id(request)
        default_servings = await self._default_servings(request)
        menu = await load_week_menu(user_id, default_servings=default_servings)
        menu = toggle_pin(menu, day)
        await save_week_menu(user_id, menu)
        return await self._render_days(request)

    @post(path="/{day:str}/recipe/{recipe_id:int}", summary="Assign recipe to day")
    async def assign_recipe(
        self, request: Request, day: str, recipe_id: int
    ) -> Template:
        """Set the recipe for a specific day."""
        if not is_valid_day(day):
            raise NotFoundException()

        user_id = await self._viewer_id(request)
        recipe = await Recipe.filter(
            self._visible_filter(user_id), id=recipe_id
        ).first()
        if recipe is None:
            raise NotFoundException()

        default_servings = await self._default_servings(request)
        menu = await load_week_menu(user_id, default_servings=default_servings)
        menu = set_day_recipe(menu, day, recipe_id)
        await save_week_menu(user_id, menu)
        return await self._render_days(request)

    @post(
        path="/{day:str}/move/{direction:str}", summary="Move a day's recipe up or down"
    )
    async def move_day_recipe(
        self, request: Request, day: str, direction: str
    ) -> Template:
        """Swap a day's meal with the neighbouring day in display order."""
        if not is_valid_day(day) or direction not in {"up", "down"}:
            raise NotFoundException()

        user_id = await self._viewer_id(request)
        default_servings = await self._default_servings(request)
        menu = await load_week_menu(user_id, default_servings=default_servings)
        start_day = await load_start_day(user_id)
        menu = move_day(menu, day, direction, start_day=start_day)
        await save_week_menu(user_id, menu)
        return await self._render_days(request)

    @post(path="/{day:str}/servings", summary="Set planned servings for a day")
    async def set_servings(self, request: Request, day: str) -> Template:
        """Persist the number of servings planned for a specific day."""
        if not is_valid_day(day):
            raise NotFoundException()

        user_id = await self._viewer_id(request)
        default_servings = await self._default_servings(request)
        form_data = await request.form()
        servings = normalize_servings(
            form_data.get("servings"), default_servings=default_servings
        )
        menu = await load_week_menu(user_id, default_servings=default_servings)
        menu = set_day_servings(menu, day, servings, default_servings=default_servings)
        await save_week_menu(user_id, menu)
        return await self._render_days(request)

    @get(path="/grocery-list", summary="Generate grocery list for the week menu")
    async def grocery_list(self, request: Request) -> Template:
        """Build an aggregated grocery list scaled to each day's servings."""
        return await self._render_grocery_list(request)

    @post(path="/grocery-list/generate", summary="Generate grocery list from week menu")
    async def generate_grocery_list(self, request: Request) -> Redirect:
        """Create or update the grocery list from the current week menu."""
        user_id = await self._viewer_id(request)
        form_data = await request.form()
        mode = str(form_data.get("mode", "")).strip()
        if mode == "replace":
            items = await self._grocery_items_from_week_menu(request)
            await reset_grocery_plan(user_id)
            await save_grocery_list(user_id, items)
            set_grocery_suppress_preserve(request)
        elif mode == "merge":
            existing = await load_grocery_list(user_id)
            new_items = await self._grocery_items_from_week_menu(request)
            await save_grocery_list(user_id, merge_grocery_items(existing, new_items))
            set_grocery_suppress_preserve(request)
        else:
            raise NotFoundException()
        return Redirect(path="/week-menu/grocery-list", status_code=HTTP_303_SEE_OTHER)

    @post(path="/grocery-list/add", summary="Add a custom grocery to the list")
    async def add_custom_grocery(self, request: Request) -> Template | Redirect:
        """Add a user-entered ingredient, amount, and unit to the grocery list."""
        user_id = await self._viewer_id(request)
        set_grocery_suppress_preserve(request)
        form_data = await request.form()
        name = str(form_data.get("ingredient", "")).strip()
        quantity = parse_grocery_quantity(form_data.get("quantity"))
        unit_abbrev = str(form_data.get("unit", "")).strip()

        unit = await Unit.find(unit_abbrev, owner_id=user_id) if unit_abbrev else None
        action_message: str | None
        reset_form = False
        if not name:
            action_message = "Enter an ingredient name."
        elif quantity is None:
            action_message = "Enter a positive amount."
        elif unit is None:
            action_message = f"Could not find unit: {unit_abbrev}"
        else:
            ingredient, _ = await get_or_create_ingredient(user_id, name)
            await add_items_to_grocery_list(
                user_id,
                [
                    GroceryItem(
                        ingredient_id=ingredient.id,
                        name=ingredient.name,
                        unit=unit.abbrev,
                        quantity=quantity,
                    )
                ],
            )
            action_message = f"Added {ingredient.name} to your grocery list."
            reset_form = True
        return await self._grocery_add_response(
            request,
            action_message=action_message,
            grocery_add_reset_form=reset_form,
        )

    @post(
        path="/grocery-list/add-weekly",
        summary="Add weekly groceries to the list",
    )
    async def add_weekly_groceries_to_list(
        self, request: Request
    ) -> Template | Redirect:
        """Add saved weekly groceries that are not yet on the grocery list."""
        user_id = await self._viewer_id(request)
        set_grocery_suppress_preserve(request)
        weekly_items = await weekly_groceries_as_items(user_id)
        if not weekly_items:
            action_message = (
                "You have no weekly groceries yet. Add some in Settings first."
            )
        else:
            current_items = (
                await hydrate_grocery_item_names(
                    user_id, await load_grocery_list(user_id)
                )
                if await is_grocery_list_initialized(user_id)
                else []
            )
            missing_items = weekly_groceries_missing_from_list(
                weekly_items, current_items
            )
            if not missing_items:
                action_message = (
                    "Your weekly groceries are already on the grocery list."
                )
            else:
                await add_items_to_grocery_list(user_id, missing_items)
                count = len(missing_items)
                noun = "grocery" if count == 1 else "groceries"
                action_message = f"Added {count} weekly {noun} to your grocery list."
        return await self._grocery_add_response(request, action_message=action_message)

    @get(path="/grocery-list/export", summary="Export grocery list as plaintext")
    async def grocery_list_export(self, request: Request) -> Response[str]:
        """Return the grocery list grouped by shop as plain text."""
        context = await self._build_grocery_context(request)
        return Response(
            content=context["grocery_export_text"],
            media_type="text/plain; charset=utf-8",
        )

    @post(path="/grocery-list/assign", summary="Assign grocery ingredient to shop")
    async def assign_grocery_ingredient(self, request: Request) -> Template:
        """Assign or reassign a shop for one grocery line."""
        user_id = await self._viewer_id(request)
        form_data = await request.form()
        ingredient_id = int(form_data.get("ingredient_id", 0))
        unit = str(form_data.get("unit", "")).strip()
        shop_value = str(form_data.get("shop_id", "")).strip()
        await self._require_grocery_line(user_id, ingredient_id, unit)
        if not shop_value:
            raise NotFoundException()
        shop_id = int(shop_value)
        shops = await load_shops(user_id)
        if shop_id not in {shop["id"] for shop in shops}:
            raise NotFoundException()

        hydrated_items = await hydrate_grocery_item_names(
            user_id, await load_grocery_list(user_id)
        )
        await set_grocery_line_shop(user_id, ingredient_id, unit, shop_id)
        if (
            self._grocery_line_count_for_ingredient(hydrated_items, ingredient_id) == 1
            and await Ingredient.get_or_none(id=ingredient_id, owner_id=user_id)
            is not None
        ):
            await set_ingredient_shop(user_id, ingredient_id, shop_id)

        await unmark_already_have_line(user_id, ingredient_id, unit)
        await unmark_to_check_line(user_id, ingredient_id, unit)
        return await self._grocery_list_response(request)

    @post(path="/grocery-list/already-have", summary="Mark ingredient as already owned")
    async def mark_grocery_already_have(self, request: Request) -> Template:
        """Move one grocery line to the already-have list for this grocery plan."""
        user_id = await self._viewer_id(request)
        form_data = await request.form()
        ingredient_id = int(form_data.get("ingredient_id", 0))
        unit = str(form_data.get("unit", "")).strip()
        await self._require_grocery_line(user_id, ingredient_id, unit)
        await mark_already_have_line(user_id, ingredient_id, unit)
        await unmark_to_check_line(user_id, ingredient_id, unit)
        return await self._grocery_list_response(request)

    @post(
        path="/grocery-list/already-have/remove",
        summary="Remove ingredient from already-have list",
    )
    async def unmark_grocery_already_have(self, request: Request) -> Template:
        """Return one grocery line from the already-have list to the active grocery plan."""
        user_id = await self._viewer_id(request)
        form_data = await request.form()
        ingredient_id = int(form_data.get("ingredient_id", 0))
        unit = str(form_data.get("unit", "")).strip()
        await self._require_grocery_line(user_id, ingredient_id, unit)
        await unmark_already_have_line(user_id, ingredient_id, unit)
        return await self._grocery_list_response(request)

    @post(path="/grocery-list/to-check", summary="Mark grocery line for checking")
    async def mark_grocery_to_check(self, request: Request) -> Template:
        """Move one grocery line to the to-check list."""
        user_id = await self._viewer_id(request)
        form_data = await request.form()
        ingredient_id = int(form_data.get("ingredient_id", 0))
        unit = str(form_data.get("unit", "")).strip()
        await self._require_grocery_line(user_id, ingredient_id, unit)
        await mark_to_check_line(user_id, ingredient_id, unit)
        await unmark_already_have_line(user_id, ingredient_id, unit)
        return await self._grocery_list_response(request)

    @post(
        path="/grocery-list/to-check/remove",
        summary="Remove grocery line from to-check list",
    )
    async def unmark_grocery_to_check(self, request: Request) -> Template:
        """Return one grocery line from the to-check list to active sorting."""
        user_id = await self._viewer_id(request)
        form_data = await request.form()
        ingredient_id = int(form_data.get("ingredient_id", 0))
        unit = str(form_data.get("unit", "")).strip()
        await self._require_grocery_line(user_id, ingredient_id, unit)
        await unmark_to_check_line(user_id, ingredient_id, unit)
        return await self._grocery_list_response(request)

    @post(
        path="/grocery-list/shop/{shop_id:int}/already-have",
        summary="Mark all shop groceries as already owned",
    )
    async def mark_shop_groceries_already_have(
        self, request: Request, shop_id: int
    ) -> Template:
        """Mark every ingredient in one shop section as already available."""
        user_id = await self._viewer_id(request)
        shops = await load_shops(user_id)
        if shop_id not in {shop["id"] for shop in shops}:
            raise NotFoundException()
        items = await load_grocery_list(user_id)
        ingredient_shop_ids = await load_ingredient_shop_ids(user_id)
        line_shop_ids = await load_grocery_line_shops(user_id)
        await mark_shop_already_have(
            user_id, shop_id, items, ingredient_shop_ids, line_shop_ids
        )
        return await self._grocery_list_response(request)

    @post(
        path="/grocery-list/already-have/clear",
        summary="Clear the already-have list",
    )
    async def clear_grocery_already_have(self, request: Request) -> Template:
        """Remove every already-have grocery from the plan."""
        user_id = await self._viewer_id(request)
        await empty_already_have_list(user_id)
        return await self._grocery_list_response(request)

    @post(
        path="/grocery-list/to-check/clear",
        summary="Clear the to-check list",
    )
    async def clear_grocery_to_check(self, request: Request) -> Template:
        """Remove every to-check grocery from the plan."""
        user_id = await self._viewer_id(request)
        await empty_to_check_list(user_id)
        return await self._grocery_list_response(request)

    @get(
        path="/grocery-list/item/{ingredient_id:int}/{unit:str}/display",
        summary="Show grocery amount display",
    )
    async def grocery_item_display(
        self, request: Request, ingredient_id: int, unit: str
    ) -> Template:
        """Return the read-only amount display for one grocery line."""
        user_id = await self._viewer_id(request)
        item = await self._hydrated_grocery_line(user_id, ingredient_id, unit)
        return Template(
            template_name="partials/grocery-amount-display.html",
            context={"request": request, "item": item},
        )

    @get(
        path="/grocery-list/item/{ingredient_id:int}/{unit:str}/edit",
        summary="Show grocery amount editor",
    )
    async def grocery_item_editor(
        self, request: Request, ingredient_id: int, unit: str
    ) -> Template:
        """Show inline editors for one grocery line's quantity and unit."""
        user_id = await self._viewer_id(request)
        item = await self._hydrated_grocery_line(user_id, ingredient_id, unit)
        units = await Unit.filter(owner_id=user_id).order_by("abbrev")
        return Template(
            template_name="partials/grocery-amount-editor.html",
            context={"request": request, "item": item, "units": units},
        )

    @post(
        path="/grocery-list/item/{ingredient_id:int}/{unit:str}",
        summary="Save grocery amount",
    )
    async def update_grocery_item_amount(
        self, request: Request, ingredient_id: int, unit: str
    ) -> Response | Template:
        """Persist edited quantity and unit for one grocery line."""
        user_id = await self._viewer_id(request)
        await self._require_grocery_line(user_id, ingredient_id, unit)
        form_data = await request.form()
        quantity = parse_grocery_quantity(form_data.get("quantity"))
        new_unit = str(form_data.get("unit", "")).strip()
        if quantity is None or not new_unit:
            raise NotFoundException()
        hydrated_items = await hydrate_grocery_item_names(
            user_id, await load_grocery_list(user_id)
        )
        success, merge_message = await update_grocery_line(
            user_id,
            ingredient_id,
            unit,
            quantity=quantity,
            unit=new_unit,
            items=hydrated_items,
        )
        if not success:
            raise NotFoundException()
        if merge_message or new_unit != unit:
            return await self._refresh_grocery_list_response(
                request, action_message=merge_message
            )
        item = await self._hydrated_grocery_line(user_id, ingredient_id, new_unit)
        return Template(
            template_name="partials/grocery-amount-display.html",
            context={"request": request, "item": item},
        )

    @get(path="/export", summary="Export week menu as plaintext")
    async def week_menu_export(self, request: Request) -> Response[str]:
        """Return the week menu as plain text lines."""
        context = await self._build_grocery_context(request)
        return Response(
            content=context["week_menu_export_text"],
            media_type="text/plain; charset=utf-8",
        )

    @post(path="/{day:str}/clear", summary="Clear recipe for day")
    async def clear_day(self, request: Request, day: str) -> Template:
        """Remove any selected recipe from a day."""
        if not is_valid_day(day):
            raise NotFoundException()

        user_id = await self._viewer_id(request)
        default_servings = await self._default_servings(request)
        menu = await load_week_menu(user_id, default_servings=default_servings)
        menu = set_day_recipe(menu, day, None)
        await save_week_menu(user_id, menu)
        return await self._render_days(request)

    @get(path="/{day:str}/search", summary="Search recipes for a day")
    async def search_for_day(
        self, request: Request, day: str, search: str | None = None
    ) -> Template:
        """Return recipe search results for assigning to a day."""
        if not is_valid_day(day):
            raise NotFoundException()

        user_id = await self._viewer_id(request)
        query_preference = self._wants_public(request)
        include_public = (
            query_preference
            if "include_public" in request.query_params
            else await load_include_public(user_id)
        )
        await save_include_public(user_id, include_public)
        recipes: list[Recipe] = []
        if search:
            recipes = await Recipe.search(
                search, limit=5, viewer_id=user_id, include_public=include_public
            )

        return Template(
            template_name="partials/week-menu-day-search-results.html",
            context={
                "request": request,
                "day": day,
                "recipes": recipes,
                "search": search or "",
                "include_public": include_public,
            },
        )

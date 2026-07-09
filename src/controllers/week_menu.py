"""Week menu planning endpoints."""

from collections import defaultdict

from litestar import Controller, Request, get, post
from litestar.exceptions import NotFoundException
from litestar.response import Redirect, Response, Template
from loguru import logger
from tortoise.expressions import Q

from src.auth import get_current_user
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
from src.user_settings import load_user_settings
from src.week_menu import (
    GroceryItem,
    TagGroupConstraint,
    build_day_rows,
    build_grocery_list,
    is_valid_day,
    load_start_day,
    load_tag_constraints,
    load_week_menu,
    move_day,
    normalize_servings,
    ordered_week_days,
    parse_tag_constraints_from_form,
    randomize_week_menu,
    load_include_public,
    load_already_have_ids,
    empty_already_have_list,
    ingredient_in_grocery_list,
    find_grocery_line,
    has_grocery_list_items,
    is_grocery_list_initialized,
    load_grocery_list,
    mark_already_have,
    mark_shop_already_have,
    merge_grocery_items,
    parse_grocery_quantity,
    pop_grocery_action_flash,
    pop_grocery_suppress_preserve,
    reset_grocery_plan,
    save_grocery_list,
    set_grocery_action_flash,
    set_grocery_suppress_preserve,
    unmark_already_have,
    update_grocery_line,
    save_start_day,
    save_tag_constraints,
    save_include_public,
    save_week_menu,
    scale_ingredient_quantity,
    set_day_recipe,
    set_day_servings,
    toggle_pin,
)


class WeekMenuController(Controller):
    """Plan dinners for each day of the week."""

    path = "/week-menu"
    tags = ["week-menu"]

    @staticmethod
    async def _default_servings(request: Request) -> int:
        """Return the current user's preferred default servings."""
        user_id = await WeekMenuController._viewer_id(request)
        return load_user_settings(user_id)["servings"]

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
        menu = load_week_menu(request, default_servings=default_servings)
        start_day = load_start_day(request)
        tag_groups = await self._tag_groups(user_id)
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
            "include_public": load_include_public(request),
            "tag_constraint_rows": constraint_rows,
            "messages": messages or [],
            "warnings": warnings or [],
            "grocery_list_has_items": has_grocery_list_items(request),
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
        default_servings = await self._default_servings(request)
        menu = load_week_menu(request, default_servings=default_servings)
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

    async def _grocery_items_from_week_menu(
        self, request: Request
    ) -> list[GroceryItem]:
        """Build a fresh aggregated grocery list from the current week menu."""
        default_servings = await self._default_servings(request)
        menu = load_week_menu(request, default_servings=default_servings)
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
    ) -> dict:
        """Build shared grocery-list context for HTML and plaintext export."""
        user_id = await self._viewer_id(request)
        default_servings = await self._default_servings(request)
        menu = load_week_menu(request, default_servings=default_servings)
        start_day = load_start_day(request)
        recipe_ids = [
            slot["recipe_id"] for slot in menu.values() if slot["recipe_id"] is not None
        ]
        recipes_by_id = await self._recipes_by_id(recipe_ids)

        grocery_message: str | None = None
        if preserve_existing and is_grocery_list_initialized(request):
            grocery_items = load_grocery_list(request)
            if grocery_items and not pop_grocery_suppress_preserve(request):
                grocery_message = (
                    "Your grocery list is preserved and was not regenerated "
                    "from the week menu."
                )
        else:
            grocery_items = await self._grocery_items_from_week_menu(request)
            reset_grocery_plan(request)
            save_grocery_list(request, grocery_items)

        if action_message is None:
            action_message = pop_grocery_action_flash(request)

        ingredient_shop_ids = await load_ingredient_shop_ids(user_id)
        shops = await load_shops(user_id)
        already_have_ids = load_already_have_ids(request)
        unassigned_items, already_have_items, grocery_groups = split_grocery_lists(
            grocery_items, ingredient_shop_ids, shops, already_have_ids
        )
        days = await build_day_rows(menu, recipes_by_id, start_day)
        units = await Unit.filter(owner_id=user_id).order_by("abbrev")
        return {
            "request": request,
            "days": days,
            "unassigned_items": unassigned_items,
            "already_have_items": already_have_items,
            "grocery_groups": grocery_groups,
            "grocery_export_text": format_grocery_export(
                unassigned_items, grocery_groups
            ),
            "week_menu_export_text": format_week_menu_export(days),
            "shops": shops,
            "ingredient_shop_ids": ingredient_shop_ids,
            "already_have_ids": already_have_ids,
            "units": units,
            "grocery_message": grocery_message,
            "grocery_action_message": action_message,
        }

    async def _refresh_grocery_list_response(
        self, request: Request, *, action_message: str | None = None
    ) -> Response | Template:
        """Return a full grocery list refresh, using HX-Refresh for HTMX requests."""
        if request.headers.get("HX-Request"):
            if action_message:
                set_grocery_action_flash(request, action_message)
            return Response(
                content="", status_code=200, headers={"HX-Refresh": "true"}
            )
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

    async def _require_grocery_ingredient(
        self, request: Request, ingredient_id: int
    ) -> None:
        """Raise when an ingredient is not on the current grocery list."""
        user_id = await self._viewer_id(request)
        if await Ingredient.get_or_none(id=ingredient_id, owner_id=user_id) is None:
            raise NotFoundException()
        if not ingredient_in_grocery_list(load_grocery_list(request), ingredient_id):
            raise NotFoundException()

    async def _owned_grocery_line(
        self, request: Request, ingredient_id: int, unit: str
    ) -> GroceryItem:
        """Return one grocery line owned by the current user."""
        await self._require_grocery_ingredient(request, ingredient_id)
        item = find_grocery_line(load_grocery_list(request), ingredient_id, unit)
        if item is None:
            raise NotFoundException()
        return item

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
        default_servings = await self._default_servings(request)
        menu = load_week_menu(request, default_servings=default_servings)
        if all(slot["pinned"] for slot in menu.values()):
            return await self._render_page_with_feedback(
                request,
                warnings=["All days are pinned. Unpin at least one day to randomize."],
            )
        form_data = await request.form()
        include_public = self._form_wants_public(dict(form_data))
        save_include_public(request, include_public)
        user_id = await self._viewer_id(request)
        category_ids = await self._category_ids(user_id)
        constraints = load_tag_constraints(request, category_ids)
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
        save_week_menu(request, menu)
        return await self._render_page_with_feedback(request, warnings=warnings)

    @post(path="/{day:str}/pin", summary="Toggle pin for a day")
    async def pin_day(self, request: Request, day: str) -> Template:
        """Toggle whether a day's recipe is kept when randomizing."""
        if not is_valid_day(day):
            raise NotFoundException()

        default_servings = await self._default_servings(request)
        menu = load_week_menu(request, default_servings=default_servings)
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

        user_id = await self._viewer_id(request)
        recipe = await Recipe.filter(
            self._visible_filter(user_id), id=recipe_id
        ).first()
        if recipe is None:
            raise NotFoundException()

        default_servings = await self._default_servings(request)
        menu = load_week_menu(request, default_servings=default_servings)
        menu = set_day_recipe(menu, day, recipe_id)
        save_week_menu(request, menu)
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

        default_servings = await self._default_servings(request)
        menu = load_week_menu(request, default_servings=default_servings)
        start_day = load_start_day(request)
        menu = move_day(menu, day, direction, start_day=start_day)
        save_week_menu(request, menu)
        return await self._render_days(request)

    @post(path="/{day:str}/servings", summary="Set planned servings for a day")
    async def set_servings(self, request: Request, day: str) -> Template:
        """Persist the number of servings planned for a specific day."""
        if not is_valid_day(day):
            raise NotFoundException()

        default_servings = await self._default_servings(request)
        form_data = await request.form()
        servings = normalize_servings(
            form_data.get("servings"), default_servings=default_servings
        )
        menu = load_week_menu(request, default_servings=default_servings)
        menu = set_day_servings(menu, day, servings, default_servings=default_servings)
        save_week_menu(request, menu)
        return await self._render_days(request)

    @get(path="/grocery-list", summary="Generate grocery list for the week menu")
    async def grocery_list(self, request: Request) -> Template:
        """Build an aggregated grocery list scaled to each day's servings."""
        return await self._render_grocery_list(request)

    @post(path="/grocery-list/generate", summary="Generate grocery list from week menu")
    async def generate_grocery_list(self, request: Request) -> Redirect:
        """Create or update the grocery list from the current week menu."""
        form_data = await request.form()
        mode = str(form_data.get("mode", "")).strip()
        if mode == "replace":
            items = await self._grocery_items_from_week_menu(request)
            reset_grocery_plan(request)
            save_grocery_list(request, items)
            set_grocery_suppress_preserve(request)
        elif mode == "merge":
            existing = load_grocery_list(request)
            new_items = await self._grocery_items_from_week_menu(request)
            save_grocery_list(
                request, merge_grocery_items(existing, new_items)
            )
            set_grocery_suppress_preserve(request)
        else:
            raise NotFoundException()
        return Redirect(path="/week-menu/grocery-list")

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
        """Assign or reassign a shop for one grocery ingredient."""
        user_id = await self._viewer_id(request)
        form_data = await request.form()
        ingredient_id = int(form_data.get("ingredient_id", 0))
        shop_value = str(form_data.get("shop_id", "")).strip()
        await self._require_grocery_ingredient(request, ingredient_id)
        if not shop_value:
            raise NotFoundException()
        shop_id = int(shop_value)
        shops = await load_shops(user_id)
        if shop_id not in {shop["id"] for shop in shops}:
            raise NotFoundException()
        await set_ingredient_shop(user_id, ingredient_id, shop_id)
        unmark_already_have(request, ingredient_id)
        return await self._render_grocery_list(request)

    @post(path="/grocery-list/already-have", summary="Mark ingredient as already owned")
    async def mark_grocery_already_have(self, request: Request) -> Template:
        """Move an ingredient to the already-have list for this grocery plan."""
        form_data = await request.form()
        ingredient_id = int(form_data.get("ingredient_id", 0))
        await self._require_grocery_ingredient(request, ingredient_id)
        mark_already_have(request, ingredient_id)
        return await self._render_grocery_list(request)

    @post(
        path="/grocery-list/already-have/remove",
        summary="Remove ingredient from already-have list",
    )
    async def unmark_grocery_already_have(self, request: Request) -> Template:
        """Return an ingredient from the already-have list to the active grocery plan."""
        form_data = await request.form()
        ingredient_id = int(form_data.get("ingredient_id", 0))
        await self._require_grocery_ingredient(request, ingredient_id)
        unmark_already_have(request, ingredient_id)
        return await self._render_grocery_list(request)

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
        items = load_grocery_list(request)
        ingredient_shop_ids = await load_ingredient_shop_ids(user_id)
        mark_shop_already_have(request, shop_id, items, ingredient_shop_ids)
        return await self._render_grocery_list(request)

    @post(
        path="/grocery-list/already-have/clear",
        summary="Clear the already-have list",
    )
    async def clear_grocery_already_have(self, request: Request) -> Template:
        """Remove every already-have grocery from the plan."""
        empty_already_have_list(request)
        return await self._render_grocery_list(request)

    @get(
        path="/grocery-list/item/{ingredient_id:int}/{unit:str}/display",
        summary="Show grocery amount display",
    )
    async def grocery_item_display(
        self, request: Request, ingredient_id: int, unit: str
    ) -> Template:
        """Return the read-only amount display for one grocery line."""
        item = await self._owned_grocery_line(request, ingredient_id, unit)
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
        item = await self._owned_grocery_line(request, ingredient_id, unit)
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
        await self._owned_grocery_line(request, ingredient_id, unit)
        form_data = await request.form()
        quantity = parse_grocery_quantity(form_data.get("quantity"))
        new_unit = str(form_data.get("unit", "")).strip()
        if quantity is None or not new_unit:
            raise NotFoundException()
        success, merge_message = update_grocery_line(
            request,
            ingredient_id,
            unit,
            quantity=quantity,
            unit=new_unit,
        )
        if not success:
            raise NotFoundException()
        if merge_message or new_unit != unit:
            return await self._refresh_grocery_list_response(
                request, action_message=merge_message
            )
        item = await self._owned_grocery_line(request, ingredient_id, new_unit)
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

        default_servings = await self._default_servings(request)
        menu = load_week_menu(request, default_servings=default_servings)
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

        user_id = await self._viewer_id(request)
        query_preference = self._wants_public(request)
        include_public = (
            query_preference
            if "include_public" in request.query_params
            else load_include_public(request)
        )
        save_include_public(request, include_public)
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

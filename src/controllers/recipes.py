import random
from typing import Annotated, Any

from litestar import Controller, Request, delete, get, post, put
from litestar.enums import RequestEncodingType
from litestar.exceptions import NotFoundException
from litestar.params import Body
from litestar.response import Redirect, Template
from loguru import logger
from pydantic import BaseModel
from tortoise.contrib.pydantic import pydantic_model_creator

from src.models import (
    Ingredient,
    Recipe,
    RecipeIngredient,
    RecipeTag,
    Tag,
    TagCategory,
    Unit,
    User,
)
from src.week_menu import (
    assign_recipe_to_unpinned_day,
    load_start_day,
    load_week_menu,
    save_week_menu,
)

RecipeSchema = pydantic_model_creator(Recipe, name="Recept")
IngredientSchema = pydantic_model_creator(Ingredient, name="Ingredient")


class RecipeIngredientDetail(BaseModel):
    name: str
    quantity: float
    unit: str


class RecipeController(Controller):
    path = "/recipes"
    tags = ["recipes"]

    @staticmethod
    async def _tag_groups() -> list[dict[str, Any]]:
        """Return tag categories with their tag values."""
        groups: list[dict[str, Any]] = []
        categories = await TagCategory.all().order_by("name")
        for category in categories:
            tags = await Tag.filter(category=category.id).order_by("name")
            groups.append({"category": category, "tags": tags})
        return groups

    @staticmethod
    async def _recipe_tag_ids(recipe_id: int) -> set[int]:
        """Return selected tag ids for a recipe."""
        ids = await RecipeTag.filter(recipe_id=recipe_id).values_list(
            "tag_id", flat=True
        )
        return set(ids)

    @staticmethod
    async def _recipe_tags_by_category(
        recipe_id: int,
    ) -> list[dict[str, Any]]:
        """Return a recipe's selected tags grouped by category."""
        groups: dict[int, dict[str, Any]] = {}
        recipe_tags = await RecipeTag.filter(recipe_id=recipe_id).select_related(
            "tag", "tag__category"
        )
        for recipe_tag in recipe_tags:
            tag = await recipe_tag.tag
            category = await tag.category
            category_data = groups.setdefault(
                category.id, {"category": category, "tags": []}
            )
            category_data["tags"].append(tag)
        return sorted(groups.values(), key=lambda group: group["category"].name.lower())

    @staticmethod
    async def _recipes_missing_any_tag_group() -> list[dict[str, Any]]:
        """Return recipes missing at least one tag group with missing group names."""
        categories = await TagCategory.all().order_by("name")
        if not categories:
            return []

        recipes = await Recipe.all().order_by("name")
        missing_rows: list[dict[str, Any]] = []
        for recipe in recipes:
            tagged_category_ids = set(
                await RecipeTag.filter(recipe_id=recipe.id).values_list(
                    "tag__category_id", flat=True
                )
            )
            missing_groups = [
                category
                for category in categories
                if category.id not in tagged_category_ids
            ]
            if missing_groups:
                missing_rows.append(
                    {"recipe": recipe, "missing_groups": missing_groups}
                )

        return missing_rows

    @staticmethod
    def _toggle_recipe_flag(value: Any | None, current_value: bool) -> bool:
        """Translate form input for checkbox-backed boolean flags."""
        if value is None:
            return False
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"false", "0", "off", "no", "none"}:
                return False
            if normalized in {"true", "1", "on", "yes"}:
                return True
        return bool(value)

    @get(path="/add", summary="Get the page to add a new recipe")
    async def add_recipe_page(self, request: Request) -> Template:
        """Show the page for adding a new recipe."""
        return Template(
            template_name="add-recipe.html",
            context={
                "request": request,
                "tag_groups": await self._tag_groups(),
            },
        )

    @get(path="/random", summary="View a random recipe")
    async def random_recipe_page(self) -> Template:
        """Show the page for viewing/editing a recipe."""
        recipes = await Recipe.all()
        random_recipe = random.choice(recipes)
        logger.debug(f"Random recipe: {random_recipe.name}")
        ingredients = await RecipeIngredient.filter(
            recipe=random_recipe.id
        ).select_related("ingredient", "unit")
        await random_recipe.fetch_related("owner")

        return Template(
            template_name="view-recipe.html",
            context={
                "recipe": random_recipe,
                "ingredients": ingredients,
                "recipe_tag_groups": await self._recipe_tags_by_category(
                    random_recipe.id
                ),
            },
        )

    @get(path="/view/{recipe_id:int}", summary="Get the page to view a recipe")
    async def view_recipe_page(self, recipe_id: int) -> Template:
        recipe = await Recipe.get_or_none(id=recipe_id)
        if not recipe:
            raise NotFoundException()

        await recipe.fetch_related("owner")
        ingredients = await RecipeIngredient.filter(recipe=recipe.id).select_related(
            "ingredient", "unit"
        )
        return Template(
            template_name="view-recipe.html",
            context={
                "recipe": recipe,
                "ingredients": ingredients,
                "recipe_tag_groups": await self._recipe_tags_by_category(recipe.id),
            },
        )

    @get(path="/missing-tags", summary="Find recipes missing tag groups")
    async def recipes_missing_tags_page(self, request: Request) -> Template:
        """Show recipes that have no tag in one or more tag groups."""
        return Template(
            template_name="recipes-missing-tags.html",
            context={
                "request": request,
                "rows": await self._recipes_missing_any_tag_group(),
            },
        )

    @post(path="/{recipe_id:int}/add-to-week-menu", summary="Add recipe to week menu")
    async def add_to_week_menu(self, request: Request, recipe_id: int) -> Template:
        """Assign recipe to first unpinned day or return warning when all are pinned."""
        recipe = await Recipe.get_or_none(id=recipe_id)
        if not recipe:
            raise NotFoundException()

        source = str((await request.form()).get("source", "view"))
        menu = load_week_menu(request)
        start_day = load_start_day(request)
        assigned_day = assign_recipe_to_unpinned_day(
            menu, recipe.id, start_day=start_day
        )

        messages: list[str] = []
        warnings: list[str] = []
        if assigned_day is None:
            warnings.append("All days are pinned. Unpin a day before adding a recipe.")
        else:
            save_week_menu(request, menu)
            messages.append(f"Added to week menu: {assigned_day.title()}")

        if source == "missing-tags":
            return Template(
                template_name="recipes-missing-tags.html",
                context={
                    "request": request,
                    "rows": await self._recipes_missing_any_tag_group(),
                    "messages": messages,
                    "warnings": warnings,
                },
            )

        await recipe.fetch_related("owner")
        ingredients = await RecipeIngredient.filter(recipe=recipe.id).select_related(
            "ingredient", "unit"
        )
        return Template(
            template_name="view-recipe.html",
            context={
                "request": request,
                "recipe": recipe,
                "ingredients": ingredients,
                "recipe_tag_groups": await self._recipe_tags_by_category(recipe.id),
                "messages": messages,
                "warnings": warnings,
            },
        )

    @get(path="/edit/{recipe_id:int}", summary="Get the page to edit a recipe")
    async def edit_recipe_page(self, recipe_id: int) -> Template:
        recipe = await Recipe.get_or_none(id=recipe_id)
        if not recipe:
            raise NotFoundException()

        await recipe.fetch_related("owner")
        ingredients = await RecipeIngredient.filter(recipe=recipe.id).select_related(
            "ingredient", "unit"
        )
        return Template(
            template_name="edit-recipe.html",
            context={
                "recipe": recipe,
                "ingredients": ingredients,
                "tag_groups": await self._tag_groups(),
                "selected_tag_ids": await self._recipe_tag_ids(recipe.id),
            },
        )

    @get(path="/delete/{recipe_id:int}", summary="Show the delete confirmation")
    async def delete_recipe_partial(self, recipe_id: int) -> Template:
        return Template(
            template_name="partials/delete-confirmation.html",
            context={"recipe_id": recipe_id},
        )

    @get(path="/title-editor/{recipe_id:int}", summary="Title editor")
    async def title_editor(self, recipe_id: int) -> Template:
        """Just load the element to edit the title."""
        recipe = await Recipe.get_or_none(id=recipe_id)
        if not recipe:
            raise NotFoundException()

        return Template(
            template_name="partials/edit-recipe-title.html", context={"recipe": recipe}
        )

    @get(path="/desc-editor/{recipe_id:int}", summary="Description editor")
    async def desc_editor(self, recipe_id: int) -> Template:
        """Just load the element to edit the description."""
        recipe = await Recipe.get_or_none(id=recipe_id)
        if not recipe:
            raise NotFoundException()

        return Template(
            template_name="partials/edit-recipe-desc.html", context={"recipe": recipe}
        )

    @post(path="/edit-title/{recipe_id:int}", summary="Edit the title")
    async def edit_title(
        self,
        recipe_id: int,
        data: Annotated[
            dict[str, Any], Body(media_type=RequestEncodingType.URL_ENCODED)
        ],
    ) -> Template:
        """Edit the title, and return the updated title element."""
        recipe = await Recipe.get_or_none(id=recipe_id)
        if not recipe:
            raise NotFoundException()

        messages = []
        if new_title := data.get("new_title"):
            recipe.name = new_title
            await recipe.save()
            messages.append("Recipe name updated")
        else:
            messages.append("No recipe name found, not saved.")

        return Template(
            template_name="partials/edited-recipe-title.html",
            context={"recipe": recipe, "messages": messages},
        )

    @post(path="/edit-desc/{recipe_id:int}", summary="Edit the description")
    async def edit_description(
        self,
        recipe_id: int,
        data: Annotated[
            dict[str, Any], Body(media_type=RequestEncodingType.URL_ENCODED)
        ],
    ) -> Template:
        """Edit the description, and return the updated title element."""
        recipe = await Recipe.get_or_none(id=recipe_id)
        if not recipe:
            raise NotFoundException()

        messages = []
        if new_value := data.get("new_desc"):
            recipe.description = new_value
            await recipe.save()
            messages.append("Recipe description updated")
        else:
            messages.append("No recipe description found, not saved.")

        return Template(
            template_name="partials/edited-recipe-desc.html",
            context={"recipe": recipe, "messages": messages},
        )

    @post(path="/{recipe_id:int}/toggle-private", summary="Toggle recipe privacy")
    async def toggle_private(
        self,
        recipe_id: int,
        data: Annotated[
            dict[str, Any], Body(media_type=RequestEncodingType.URL_ENCODED)
        ],
    ) -> Template:
        recipe = await Recipe.get_or_none(id=recipe_id)
        if not recipe:
            raise NotFoundException()

        recipe.private = not self._toggle_recipe_flag(
            data.get("private"), recipe.private
        )
        await recipe.save()
        return Template(
            template_name="partials/recipe-status-controls.html",
            context={"recipe": recipe},
        )

    @post(path="/{recipe_id:int}/toggle-enabled", summary="Toggle recipe enabled state")
    async def toggle_enabled(
        self,
        recipe_id: int,
        data: Annotated[
            dict[str, Any], Body(media_type=RequestEncodingType.URL_ENCODED)
        ],
    ) -> Template:
        recipe = await Recipe.get_or_none(id=recipe_id)
        if not recipe:
            raise NotFoundException()

        recipe.enabled = self._toggle_recipe_flag(data.get("enabled"), recipe.enabled)
        await recipe.save()
        return Template(
            template_name="partials/recipe-status-controls.html",
            context={"recipe": recipe},
        )

    @get(
        path="/{recipe_id:int}/ingredients/{ingredient_id:int}",
        summary="Show ingredient row",
    )
    async def ingredient_row(self, recipe_id: int, ingredient_id: int) -> Template:
        """Return the read-only ingredient row, for example when canceling an edit."""
        recipe_ingredient = await RecipeIngredient.get_or_none(
            id=ingredient_id, recipe=recipe_id
        )
        if not recipe_ingredient:
            raise NotFoundException()

        await recipe_ingredient.fetch_related("ingredient", "unit")

        return Template(
            template_name="partials/ingredient-row.html",
            context={
                "ingredient": recipe_ingredient,
                "recipe_id": recipe_id,
            },
        )

    @get(
        path="/{recipe_id:int}/ingredients/{ingredient_id:int}/edit",
        summary="Show ingredient edit form",
    )
    async def ingredient_editor(self, recipe_id: int, ingredient_id: int) -> Template:
        """Show the form to edit an ingredient's quantity, unit, and name."""
        recipe_ingredient = await RecipeIngredient.get_or_none(
            id=ingredient_id, recipe=recipe_id
        )
        if not recipe_ingredient:
            raise NotFoundException()

        await recipe_ingredient.fetch_related("recipe", "ingredient", "unit")

        return Template(
            template_name="partials/edit-ingredient-form.html",
            context={"recipe_ingredient": recipe_ingredient},
        )

    @put(
        path="/{recipe_id:int}/ingredients/{ingredient_id:int}/edit",
        summary="Save ingredient edit",
    )
    async def edit_ingredient(
        self,
        recipe_id: int,
        ingredient_id: int,
        data: Annotated[
            dict[str, Any], Body(media_type=RequestEncodingType.URL_ENCODED)
        ],
    ) -> Template:
        """Save the edited ingredient quantity, unit, and name."""
        recipe_ingredient = await RecipeIngredient.get_or_none(
            id=ingredient_id, recipe=recipe_id
        )
        if not recipe_ingredient:
            raise NotFoundException()

        quantity = data.get("quantity")
        unit_abbrev = data.get("unit")
        ingredient_name = data.get("ingredient")

        messages = []
        valid = True
        if quantity is not None:
            try:
                recipe_ingredient.quantity = float(quantity)
            except (ValueError, TypeError):
                messages.append("Invalid quantity, not saved.")
                valid = False
        else:
            messages.append("No quantity found, not saved.")
            valid = False

        if unit_abbrev is not None:
            unit = await Unit.find(unit_abbrev)
            if unit:
                recipe_ingredient.unit = unit
            else:
                messages.append("Could not find unit, not saved.")
                valid = False
        else:
            messages.append("No unit found, not saved.")
            valid = False

        if ingredient_name is not None and str(ingredient_name).strip():
            ingredient, _ = await Ingredient.get_or_create(
                name=str(ingredient_name).strip()
            )
            duplicate = (
                await RecipeIngredient.filter(
                    recipe=recipe_id, ingredient=ingredient.id
                )
                .exclude(id=ingredient_id)
                .first()
            )
            if duplicate:
                messages.append("Ingredient already in recipe. Not saved.")
                valid = False
            else:
                recipe_ingredient.ingredient = ingredient
        else:
            messages.append("No ingredient name found, not saved.")
            valid = False

        if valid:
            await recipe_ingredient.save()
            messages.append("Ingredient updated")

        # Reload for display
        await recipe_ingredient.fetch_related("ingredient", "unit")

        return Template(
            template_name="partials/edited-ingredient.html",
            context={
                "ingredient": recipe_ingredient,
                "recipe_id": recipe_id,
                "messages": messages,
            },
        )

    @delete(
        path="/{recipe_id:int}/ingredients/{ingredient_id:int}",
        summary="Delete ingredient from recipe",
        status_code=200,
    )
    async def delete_ingredient(self, recipe_id: int, ingredient_id: int) -> Template:
        """Delete an ingredient from a recipe."""
        recipe_ingredient = await RecipeIngredient.get_or_none(
            id=ingredient_id, recipe=recipe_id
        )
        if not recipe_ingredient:
            raise NotFoundException()

        await recipe_ingredient.delete()

        # Reload remaining ingredients for display
        recipe = await Recipe.get_or_none(id=recipe_id)
        if not recipe:
            raise NotFoundException()

        ingredients = await RecipeIngredient.filter(recipe=recipe.id).select_related(
            "ingredient", "unit"
        )

        return Template(
            template_name="partials/edit-ingredient-list.html",
            context={
                "recipe": recipe,
                "ingredients": ingredients,
            },
        )

    @get(path="/{recipe_id:int}/ingredients/add", summary="Show add ingredient form")
    async def add_ingredient_form(self, recipe_id: int) -> Template:
        """Show the form to add a new ingredient to a recipe."""
        recipe = await Recipe.get_or_none(id=recipe_id)
        if not recipe:
            raise NotFoundException()

        return Template(
            template_name="partials/add-ingredient-form.html",
            context={"recipe_id": recipe_id},
        )

    @post(path="/{recipe_id:int}/ingredients/add", summary="Add ingredient to recipe")
    async def add_ingredient(
        self,
        recipe_id: int,
        data: Annotated[
            dict[str, Any], Body(media_type=RequestEncodingType.URL_ENCODED)
        ],
    ) -> Template:
        """Add a new ingredient to a recipe."""
        recipe = await Recipe.get_or_none(id=recipe_id)
        if not recipe:
            raise NotFoundException()

        quantity = data.get("quantity")
        unit_abbrev = data.get("unit")
        ingredient_name = data.get("ingredient")

        messages = []
        if not ingredient_name:
            messages.append("No ingredient selected.")
        elif not quantity:
            messages.append("No quantity provided.")
        elif not unit_abbrev:
            messages.append("No unit selected.")
        else:
            unit = await Unit.find(unit_abbrev)
            if not unit:
                messages.append(f"Could not find unit: {unit_abbrev}")
            else:
                try:
                    ingredient, _ = await Ingredient.get_or_create(name=ingredient_name)
                    existing = await RecipeIngredient.filter(
                        recipe=recipe_id, ingredient=ingredient.id
                    ).first()
                    if existing:
                        messages.append(
                            "Ingredient already in recipe. Edit existing instead."
                        )
                    else:
                        await RecipeIngredient.create(
                            recipe=recipe,
                            ingredient=ingredient,
                            quantity=float(quantity),
                            unit=unit,
                        )
                        messages.append("Ingredient added")
                except (ValueError, TypeError) as e:
                    messages.append(f"Error: {e}")

        # Reload ingredients for display
        ingredients = await RecipeIngredient.filter(recipe=recipe.id).select_related(
            "ingredient", "unit"
        )

        return Template(
            template_name="partials/edit-ingredient-list.html",
            context={
                "recipe": recipe,
                "ingredients": ingredients,
                "messages": messages,
            },
        )

    @post(path="/{recipe_id:int}/tags", summary="Update selected tags for recipe")
    async def update_recipe_tags(self, recipe_id: int, request: Request) -> Template:
        """Replace a recipe's selected tags with submitted values."""
        recipe = await Recipe.get_or_none(id=recipe_id)
        if not recipe:
            raise NotFoundException()

        form_data = await request.form()
        submitted_tag_ids = (
            [int(tag_id) for tag_id in form_data.getall("tag_ids[]")]
            if "tag_ids[]" in form_data
            else []
        )

        valid_tag_ids = set(
            await Tag.filter(id__in=submitted_tag_ids).values_list("id", flat=True)
        )

        await RecipeTag.filter(recipe_id=recipe_id).delete()
        for tag_id in valid_tag_ids:
            await RecipeTag.create(recipe_id=recipe_id, tag_id=tag_id)

        ingredients = await RecipeIngredient.filter(recipe=recipe.id).select_related(
            "ingredient", "unit"
        )
        await recipe.fetch_related("owner")
        return Template(
            template_name="edit-recipe.html",
            context={
                "request": request,
                "recipe": recipe,
                "ingredients": ingredients,
                "tag_groups": await self._tag_groups(),
                "selected_tag_ids": await self._recipe_tag_ids(recipe.id),
                "messages": ["Recipe tags updated"],
            },
        )

    @get(
        path="/delete-confirmation/{recipe_id:int}", summary="Delete the recipe by ID."
    )
    async def delete_recipe_page(self, recipe_id: int) -> Template:
        recipe = await Recipe.get_or_none(id=recipe_id)
        if not recipe:
            raise NotFoundException()
        await recipe.delete()
        return Template(
            "index.html",
            context={"messages": [f"Recipe deleted: {recipe.name}"]},
        )

    @get(path="/new-ingredient-input", summary="Get a new ingredient input field")
    async def new_ingredient_input(self, request: Request) -> Template:
        """Return an HTML snippet for a new ingredient input field."""
        return Template(
            template_name="partials/new-ingredient-input.html",
            context={"request": request},
        )

    @get(path="/search", summary="Search recipe page")
    async def search_page(self, request: Request) -> Template:
        """Show the page for searching a recipe."""

        return Template(
            template_name="search-recipes.html",
            context={"request": request, "tag_groups": await self._tag_groups()},
        )

    @get(path="/search-recipe", summary="Search for recipes")
    async def search_by_query(
        self, request: Request, search: str | None = None
    ) -> Template:
        tag_filters: dict[int, int] = {}
        for key, value in request.query_params.items():
            if not key.startswith("tag_group_") or not value:
                continue
            category_id_str = key.removeprefix("tag_group_")
            if not category_id_str.isdigit() or not value.isdigit():
                continue
            tag_filters[int(category_id_str)] = int(value)

        if not search and not tag_filters:
            recipes: list[Recipe] = []
        else:
            recipes = await Recipe.search(search, tag_filters=tag_filters)

        return Template(
            template_name="search-results.html",
            context={"request": request, "recipes": recipes},
        )

    @get(summary="Show all recipes")
    async def showall(self) -> list[RecipeSchema]:  # type: ignore
        """Show all recipes."""
        return await RecipeSchema.from_queryset(Recipe.all())

    @get(path="/count", summary="Count the number of recipes")
    async def count(self) -> int:
        """Count recipes."""
        q = await Recipe.all().count()
        return q

    @get(path="/{recipe_id:int}/detail", summary="Get recipe details as HTML")
    async def get_recipe_detail(
        self, request: Request, recipe_id: int, search: str | None = None
    ) -> Template:
        """Get recipe details and re-render the search results with the selection."""
        recipe = await Recipe.get_or_none(id=recipe_id)
        if not recipe:
            raise NotFoundException()

        ingredients = await RecipeIngredient.filter(recipe=recipe_id).select_related(
            "ingredient", "unit"
        )

        search_results: list[Recipe] = []
        if search:
            search_results = await Recipe.search(search, limit=10)

        return Template(
            template_name="partials/recipe-detail-and-search-results.html",
            context={
                "request": request,
                "recipe": recipe,
                "ingredients": ingredients,
                "recipes": search_results,
                "selected_id": recipe_id,
            },
        )

    @get(path="/{recipe_id:int}", summary="Get one recipe by id")
    async def from_id(self, recipe_id: int) -> RecipeSchema | None:  # type: ignore
        recipe = await Recipe.get_or_none(id=recipe_id)
        if not recipe:
            raise NotFoundException()
        return await RecipeSchema.from_tortoise_orm(recipe)

    @get(path="/user-profile", summary="Get the user profile page")
    async def user_profile_page(self, request: Request) -> Template:
        """Show the user profile page."""
        return Template(template_name="user-profile.html", context={"request": request})

    @delete(path="/{recipe_id:int}", summary="Remove one recipe by id")
    async def delete(self, recipe_id: int) -> None:
        recipe = await Recipe.get_or_none(id=recipe_id)
        if not recipe:
            raise NotFoundException()
        await recipe.delete()

    @post(name="Add a recipe")
    async def add(self, request: Request) -> Redirect:
        """Create a new recipe, user-style.

        Accepts
        - a name of the recipe
        - the number of servings
        - a description (preparation steps)
        - the number of minutes it takes to prep the food
        - the number of minutes it takes to cook the food
        - a list of ingredients like this: quantity|unit|ingredient, e.g. 200|g|potatoes

        For any ingredient or unit:
        - will check if it exists (note the web UI should do fuzzy matching to not get similar records)
        - add if it doesn't exist or select if it does
        - select the corresponding ID
        - link it to the new recipe
        """
        form_data = await request.form()
        name = form_data.get("name")
        servings = form_data.get("servings")
        description = form_data.get("description")
        prep_time_minutes_str = form_data.get("prep_time_minutes")
        prep_time_minutes = (
            int(prep_time_minutes_str) if prep_time_minutes_str else None
        )
        cook_time_minutes_str = form_data.get("cook_time_minutes")
        cook_time_minutes = (
            int(cook_time_minutes_str) if cook_time_minutes_str else None
        )

        quantities = form_data.getall("quantity[]") if "quantity[]" in form_data else []
        units = form_data.getall("unit[]") if "unit[]" in form_data else []
        ingredient_names = (
            form_data.getall("ingredient_name[]")
            if "ingredient_name[]" in form_data
            else []
        )
        tag_ids = (
            [int(tag_id) for tag_id in form_data.getall("tag_ids[]")]
            if "tag_ids[]" in form_data
            else []
        )

        ingredients = [
            {"quantity": q, "unit": u, "name": n}
            for q, u, n in zip(quantities, units, ingredient_names)
        ]

        logger.debug(f"Adding recipe: {name}")
        owner = await User.get_default()
        recipe = await Recipe.create(
            name=name,
            description=description or name,
            prep_time_minutes=prep_time_minutes,
            cook_time_minutes=cook_time_minutes,
            servings=servings,
            owner=owner,
            private=True,
            enabled=True,
        )
        logger.debug(f"Added - {recipe.id=}")

        valid_tag_ids = await Tag.filter(id__in=tag_ids).values_list("id", flat=True)
        for tag_id in set(valid_tag_ids):
            await RecipeTag.create(recipe=recipe, tag_id=tag_id)

        messages = []
        for ing_dict in ingredients:
            logger.debug(f"Adding ingredient: {ing_dict['name']}")
            ingredient, ing_created = await Ingredient.get_or_create(
                name=ing_dict["name"]
            )
            if ing_created:
                messages.append(f"Hey, I didn't know {ingredient.name} yet!")

            logger.debug(
                f"Finding unit by abbreviation/singular/plural: {ing_dict['unit']}"
            )
            unit = await Unit.find(ing_dict["unit"])
            if unit is None:
                messages.append(
                    f"Ingredient not added: {ingredient.name} (could not find unit: {ing_dict['unit']})"
                )
                continue

            quantity = ing_dict["quantity"]

            logger.debug("Listing ingredient in recipe")
            recipe_ing = await RecipeIngredient.create(
                recipe=recipe,
                ingredient=ingredient,
                quantity=quantity,
                unit=unit,
            )
            logger.info(f"Added ingredient to recipe: {recipe_ing}")

        return Redirect(path=f"/recipes/view/{recipe.id}")

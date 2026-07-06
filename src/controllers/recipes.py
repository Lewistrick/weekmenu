import random
from typing import Annotated, Any

from litestar import Controller, Request, delete, get, post, put
from litestar.enums import RequestEncodingType
from litestar.exceptions import NotFoundException
from litestar.params import Body
from litestar.response import Template
from loguru import logger
from pydantic import BaseModel
from tortoise.contrib.pydantic import pydantic_model_creator

from src.models import Ingredient, Recipe, RecipeIngredient, Unit, User

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
        return Template(template_name="add-recipe.html", context={"request": request})

    @get(path="/random", summary="View a random recipe")
    async def random_recipe_page(self) -> Template:
        """Show the page for viewing/editing a recipe."""
        recipes = await Recipe.all()
        random_recipe = random.choice(recipes)
        logger.debug(f"Random recipe: {random_recipe.name}")
        ingredients = await RecipeIngredient.filter(
            recipe=random_recipe.id
        ).select_related("ingredient", "unit")

        return Template(
            template_name="view-recipe.html",
            context={
                "recipe": random_recipe,
                "ingredients": ingredients,
            },
        )

    @get(path="/view/{recipe_id:int}", summary="Get the page to view a recipe")
    async def view_recipe_page(self, recipe_id: int) -> Template:
        recipe = await Recipe.get_or_none(id=recipe_id)
        if not recipe:
            breakpoint()
            raise NotFoundException()

        ingredients = await RecipeIngredient.filter(recipe=recipe.id).select_related(
            "ingredient", "unit"
        )
        return Template(
            template_name="view-recipe.html",
            context={
                "recipe": recipe,
                "ingredients": ingredients,
            },
        )

    @get(path="/edit/{recipe_id:int}", summary="Get the page to edit a recipe")
    async def edit_recipe_page(self, recipe_id: int) -> Template:
        recipe = await Recipe.get_or_none(id=recipe_id)
        if not recipe:
            raise NotFoundException()

        ingredients = await RecipeIngredient.filter(recipe=recipe.id).select_related(
            "ingredient", "unit"
        )
        return Template(
            template_name="edit-recipe.html",
            context={
                "recipe": recipe,
                "ingredients": ingredients,
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
        path="/{recipe_id:int}/ingredients/{ingredient_id:int}/edit",
        summary="Show ingredient edit form",
    )
    async def ingredient_editor(self, recipe_id: int, ingredient_id: int) -> Template:
        """Show the form to edit an ingredient's quantity and unit."""
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
        """Save the edited ingredient quantity and unit."""
        recipe_ingredient = await RecipeIngredient.get_or_none(
            id=ingredient_id, recipe=recipe_id
        )
        if not recipe_ingredient:
            raise NotFoundException()

        quantity = data.get("quantity")
        unit_abbrev = data.get("unit")

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
            context={"request": request},
        )

    @get(path="/search-recipe", summary="Search for recipes")
    async def search_by_query(
        self, request: Request, search: str | None = None
    ) -> Template:
        recipes: list[Recipe] = []
        if not search:
            # At some point this could show recent/popular recipes
            pass
        else:
            recipes = await Recipe.filter(name__icontains=search)

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
            search_results = await Recipe.filter(name__icontains=search).limit(10)

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
    async def add(self, request: Request) -> Template:
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

        return Template(
            template_name="partials/add-recipe-response.html",
            context={"request": request, "recipe": recipe, "messages": messages},
        )

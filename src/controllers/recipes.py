"""Recipe browsing, editing, search, and import endpoints."""

import random
from typing import Annotated, Any, cast

from litestar import Controller, Request, delete, get, post, put
from litestar.enums import RequestEncodingType
from litestar.exceptions import NotFoundException
from litestar.params import Body
from litestar.response import Redirect, Template
from loguru import logger
from pydantic import BaseModel
from tortoise.contrib.pydantic import pydantic_model_creator
from tortoise.expressions import Q

from src.auth import get_current_user
from src.catalog import copy_recipe_catalog, get_or_create_ingredient
from src.models import (
    Ingredient,
    Recipe,
    RecipeIngredient,
    RecipeTag,
    Tag,
    TagCategory,
    Unit,
)
from src.plan_store import load_start_day, load_week_menu, save_week_menu
from src.week_menu import assign_recipe_to_unpinned_day

RecipeSchema = pydantic_model_creator(Recipe, name="Recept")
IngredientSchema = pydantic_model_creator(Ingredient, name="Ingredient")


class RecipeIngredientDetail(BaseModel):
    """One ingredient line submitted when creating a recipe."""

    name: str
    quantity: float
    unit: str


class RecipeController(Controller):
    """HTTP routes for recipes, ingredients, tags, and search."""

    path = "/recipes"
    tags = ["recipes"]

    @staticmethod
    async def _current_user_id(request: Request) -> int:
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

    @classmethod
    async def _get_visible_recipe(cls, request: Request, recipe_id: int) -> Recipe:
        """Return a recipe if the current user may view it, else 404."""
        user_id = await cls._current_user_id(request)
        recipe = await Recipe.filter(cls._visible_filter(user_id), id=recipe_id).first()
        if recipe is None:
            raise NotFoundException()
        return recipe

    @classmethod
    async def _get_owned_recipe(cls, request: Request, recipe_id: int) -> Recipe:
        """Return a recipe only if the current user owns it, else 404."""
        user_id = await cls._current_user_id(request)
        recipe = await Recipe.get_or_none(id=recipe_id, owner_id=user_id)
        if recipe is None:
            raise NotFoundException()
        return recipe

    @staticmethod
    async def _user_owns(recipe_id: int, user_id: int) -> bool:
        """Return whether a user owns the given recipe."""
        return await Recipe.filter(id=recipe_id, owner_id=user_id).exists()

    @staticmethod
    async def _already_imported(user_id: int, source_recipe_id: int) -> bool:
        """Return whether the user already imported the given public recipe."""
        return await Recipe.filter(
            owner_id=user_id, imported_from_id=source_recipe_id
        ).exists()

    @staticmethod
    def _form_wants_public(form_data: dict[str, Any]) -> bool:
        """Return whether form data opts in to including public recipes."""
        value = form_data.get("include_public")
        if value is None:
            return False
        if isinstance(value, bool):
            return value
        return str(value).lower() in {"on", "1", "true", "yes"}

    @staticmethod
    async def _tag_groups(owner_id: int) -> list[dict[str, Any]]:
        """Return tag categories with their tag values for one user."""
        groups: list[dict[str, Any]] = []
        categories = await TagCategory.filter(owner_id=owner_id).order_by("name")
        for category in categories:
            tags = await Tag.filter(owner_id=owner_id, category=category.id).order_by(
                "name"
            )
            groups.append({"category": category, "tags": tags})
        return groups

    @staticmethod
    async def _recipe_tag_ids(recipe_id: int) -> set[int]:
        """Return selected tag ids for a recipe."""
        ids = await RecipeTag.filter(recipe_id=recipe_id).values_list(
            "tag_id", flat=True
        )
        return cast("set[int]", set(ids))

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
    async def _recipes_missing_any_tag_group(owner_id: int) -> list[dict[str, Any]]:
        """Return the owner's recipes missing at least one tag group.

        Args:
            owner_id: Only inspect recipes owned by this user.

        Returns:
            Rows pairing each recipe with the tag groups it is missing.
        """
        categories = await TagCategory.filter(owner_id=owner_id).order_by("name")
        if not categories:
            return []

        recipes = await Recipe.filter(owner_id=owner_id).order_by("name")
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

    @get(path="/add", summary="Get the page to add a new recipe")
    async def add_recipe_page(self, request: Request) -> Template:
        """Show the page for adding a new recipe."""
        owner_id = await self._current_user_id(request)
        return Template(
            template_name="add-recipe.html",
            context={
                "request": request,
                "tag_groups": await self._tag_groups(owner_id),
            },
        )

    @get(path="/random", summary="View a random recipe")
    async def random_recipe_page(self, request: Request) -> Template:
        """Show a random recipe from the current user's own collection."""
        user_id = await self._current_user_id(request)
        recipes = await Recipe.filter(owner_id=user_id)
        if not recipes:
            raise NotFoundException()
        random_recipe = random.choice(recipes)
        logger.debug(f"Random recipe: {random_recipe.name}")
        ingredients = await RecipeIngredient.filter(
            recipe=random_recipe.id
        ).select_related("ingredient", "unit")
        await random_recipe.fetch_related("owner", "creator")

        return Template(
            template_name="view-recipe.html",
            context={
                "request": request,
                "recipe": random_recipe,
                "ingredients": ingredients,
                "can_edit": await self._user_owns(random_recipe.id, user_id),
                "can_import": False,
                "already_imported": False,
                "recipe_tag_groups": await self._recipe_tags_by_category(
                    random_recipe.id
                ),
            },
        )

    @get(path="/random-public", summary="View a random public recipe")
    async def random_public_recipe_page(self, request: Request) -> Template:
        """Show a random public recipe from other users."""
        user_id = await self._current_user_id(request)
        recipes = await Recipe.filter(private=False).exclude(owner_id=user_id)
        if not recipes:
            raise NotFoundException()
        random_recipe = random.choice(recipes)
        logger.debug(f"Random public recipe: {random_recipe.name}")
        ingredients = await RecipeIngredient.filter(
            recipe=random_recipe.id
        ).select_related("ingredient", "unit")
        await random_recipe.fetch_related("owner", "creator")

        return Template(
            template_name="view-recipe.html",
            context={
                "request": request,
                "recipe": random_recipe,
                "ingredients": ingredients,
                "can_edit": False,
                "can_import": True,
                "already_imported": await self._already_imported(
                    user_id, random_recipe.id
                ),
                "recipe_tag_groups": await self._recipe_tags_by_category(
                    random_recipe.id
                ),
            },
        )

    @get(path="/view/{recipe_id:int}", summary="Get the page to view a recipe")
    async def view_recipe_page(self, request: Request, recipe_id: int) -> Template:
        """Render the read-only recipe detail page."""
        user_id = await self._current_user_id(request)
        recipe = await Recipe.filter(
            self._visible_filter(user_id), id=recipe_id
        ).first()
        if recipe is None:
            raise NotFoundException()

        await recipe.fetch_related("owner", "creator")
        ingredients = await RecipeIngredient.filter(recipe=recipe.id).select_related(
            "ingredient", "unit"
        )
        can_edit = await self._user_owns(recipe.id, user_id)
        return Template(
            template_name="view-recipe.html",
            context={
                "request": request,
                "recipe": recipe,
                "ingredients": ingredients,
                "can_edit": can_edit,
                "can_import": not can_edit,
                "already_imported": await self._already_imported(user_id, recipe.id),
                "recipe_tag_groups": await self._recipe_tags_by_category(recipe.id),
            },
        )

    @post(
        path="/{recipe_id:int}/import",
        summary="Import a public recipe into your collection",
    )
    async def import_recipe(
        self, request: Request, recipe_id: int
    ) -> Template | Redirect:
        """Create a private editable copy of a public recipe owned by someone else."""
        user_id = await self._current_user_id(request)
        source = await Recipe.filter(
            self._visible_filter(user_id), id=recipe_id, private=False
        ).first()
        if source is None or await self._user_owns(recipe_id, user_id):
            raise NotFoundException()

        await source.fetch_related("owner", "creator")
        ingredients = await RecipeIngredient.filter(recipe=source.id).select_related(
            "ingredient", "unit"
        )
        can_edit = False
        can_import = True
        already_imported = await self._already_imported(user_id, recipe_id)
        view_context = {
            "request": request,
            "recipe": source,
            "ingredients": ingredients,
            "can_edit": can_edit,
            "can_import": can_import,
            "already_imported": already_imported,
            "recipe_tag_groups": await self._recipe_tags_by_category(source.id),
        }

        if already_imported:
            return Template(
                template_name="view-recipe.html",
                context={
                    **view_context,
                    "warnings": ["You already imported this recipe."],
                },
            )

        creator = source.creator or source.owner
        copy = await Recipe.create(
            name=source.name,
            description=source.description,
            prep_time_minutes=source.prep_time_minutes,
            cook_time_minutes=source.cook_time_minutes,
            servings=source.servings,
            owner_id=user_id,
            creator=creator,
            imported_from=source,
            private=True,
            enabled=source.enabled,
        )
        await copy_recipe_catalog(source, user_id, copy)

        logger.info(f"User {user_id} imported recipe {recipe_id} as {copy.id}")
        return Redirect(path=f"/recipes/view/{copy.id}")

    @get(path="/missing-tags", summary="Find recipes missing tag groups")
    async def recipes_missing_tags_page(self, request: Request) -> Template:
        """Show recipes that have no tag in one or more tag groups."""
        user_id = await self._current_user_id(request)
        return Template(
            template_name="recipes-missing-tags.html",
            context={
                "request": request,
                "rows": await self._recipes_missing_any_tag_group(user_id),
            },
        )

    @post(path="/{recipe_id:int}/add-to-week-menu", summary="Add recipe to week menu")
    async def add_to_week_menu(self, request: Request, recipe_id: int) -> Template:
        """Assign recipe to first unpinned day or return warning when all are pinned."""
        user_id = await self._current_user_id(request)
        recipe = await Recipe.filter(
            self._visible_filter(user_id), id=recipe_id
        ).first()
        if recipe is None:
            raise NotFoundException()

        source = str((await request.form()).get("source", "view"))
        menu = await load_week_menu(user_id)
        start_day = await load_start_day(user_id)
        assigned_day = assign_recipe_to_unpinned_day(
            menu, recipe.id, start_day=start_day
        )

        messages: list[str] = []
        warnings: list[str] = []
        if assigned_day is None:
            warnings.append("All days are pinned. Unpin a day before adding a recipe.")
        else:
            await save_week_menu(user_id, menu)
            messages.append(f"Added to week menu: {assigned_day.title()}")

        if source == "missing-tags":
            return Template(
                template_name="recipes-missing-tags.html",
                context={
                    "request": request,
                    "rows": await self._recipes_missing_any_tag_group(user_id),
                    "messages": messages,
                    "warnings": warnings,
                },
            )

        await recipe.fetch_related("owner", "creator")
        ingredients = await RecipeIngredient.filter(recipe=recipe.id).select_related(
            "ingredient", "unit"
        )
        can_edit = await self._user_owns(recipe.id, user_id)
        return Template(
            template_name="view-recipe.html",
            context={
                "request": request,
                "recipe": recipe,
                "ingredients": ingredients,
                "can_edit": can_edit,
                "can_import": not can_edit,
                "already_imported": await self._already_imported(user_id, recipe.id),
                "recipe_tag_groups": await self._recipe_tags_by_category(recipe.id),
                "messages": messages,
                "warnings": warnings,
            },
        )

    @get(path="/edit/{recipe_id:int}", summary="Get the page to edit a recipe")
    async def edit_recipe_page(self, request: Request, recipe_id: int) -> Template:
        """Render the recipe editor for an owned recipe."""
        user_id = await self._current_user_id(request)
        recipe = await self._get_owned_recipe(request, recipe_id)

        await recipe.fetch_related("owner")
        ingredients = await RecipeIngredient.filter(recipe=recipe.id).select_related(
            "ingredient", "unit"
        )
        return Template(
            template_name="edit-recipe.html",
            context={
                "recipe": recipe,
                "ingredients": ingredients,
                "tag_groups": await self._tag_groups(user_id),
                "selected_tag_ids": await self._recipe_tag_ids(recipe.id),
            },
        )

    @get(path="/delete/{recipe_id:int}", summary="Show the delete confirmation")
    async def delete_recipe_partial(self, request: Request, recipe_id: int) -> Template:
        """Return the inline delete-confirmation partial."""
        await self._get_owned_recipe(request, recipe_id)
        return Template(
            template_name="partials/delete-confirmation.html",
            context={"recipe_id": recipe_id},
        )

    @get(path="/title-editor/{recipe_id:int}", summary="Title editor")
    async def title_editor(self, request: Request, recipe_id: int) -> Template:
        """Just load the element to edit the title."""
        recipe = await self._get_owned_recipe(request, recipe_id)

        return Template(
            template_name="partials/edit-recipe-title.html", context={"recipe": recipe}
        )

    @get(path="/desc-editor/{recipe_id:int}", summary="Description editor")
    async def desc_editor(self, request: Request, recipe_id: int) -> Template:
        """Just load the element to edit the description."""
        recipe = await self._get_owned_recipe(request, recipe_id)

        return Template(
            template_name="partials/edit-recipe-desc.html", context={"recipe": recipe}
        )

    @post(path="/edit-title/{recipe_id:int}", summary="Edit the title")
    async def edit_title(
        self,
        request: Request,
        recipe_id: int,
        data: Annotated[
            dict[str, Any], Body(media_type=RequestEncodingType.URL_ENCODED)
        ],
    ) -> Template:
        """Edit the title, and return the updated title element."""
        recipe = await self._get_owned_recipe(request, recipe_id)

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
        request: Request,
        recipe_id: int,
        data: Annotated[
            dict[str, Any], Body(media_type=RequestEncodingType.URL_ENCODED)
        ],
    ) -> Template:
        """Edit the description, and return the updated title element."""
        recipe = await self._get_owned_recipe(request, recipe_id)

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
        request: Request,
        recipe_id: int,
        data: Annotated[
            dict[str, Any], Body(media_type=RequestEncodingType.URL_ENCODED)
        ],
    ) -> Template:
        """Toggle whether an owned recipe is public."""
        recipe = await self._get_owned_recipe(request, recipe_id)

        # The "Public recipe" switch is checked when the recipe is public.
        recipe.private = data.get("private") is None
        await recipe.save()
        return Template(
            template_name="partials/recipe-status-controls.html",
            context={"recipe": recipe},
        )

    @post(path="/{recipe_id:int}/toggle-enabled", summary="Toggle recipe enabled state")
    async def toggle_enabled(
        self,
        request: Request,
        recipe_id: int,
        data: Annotated[
            dict[str, Any], Body(media_type=RequestEncodingType.URL_ENCODED)
        ],
    ) -> Template:
        """Toggle whether an owned recipe is enabled for week-menu use."""
        recipe = await self._get_owned_recipe(request, recipe_id)

        recipe.enabled = data.get("enabled") is not None
        await recipe.save()
        return Template(
            template_name="partials/recipe-status-controls.html",
            context={"recipe": recipe},
        )

    @get(
        path="/{recipe_id:int}/ingredients/{ingredient_id:int}",
        summary="Show ingredient row",
    )
    async def ingredient_row(
        self, request: Request, recipe_id: int, ingredient_id: int
    ) -> Template:
        """Return the read-only ingredient row, for example when canceling an edit."""
        await self._get_owned_recipe(request, recipe_id)
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
    async def ingredient_editor(
        self, request: Request, recipe_id: int, ingredient_id: int
    ) -> Template:
        """Show the form to edit an ingredient's quantity, unit, and name."""
        await self._get_owned_recipe(request, recipe_id)
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
        request: Request,
        recipe_id: int,
        ingredient_id: int,
        data: Annotated[
            dict[str, Any], Body(media_type=RequestEncodingType.URL_ENCODED)
        ],
    ) -> Template:
        """Save the edited ingredient quantity, unit, and name."""
        user_id = await self._current_user_id(request)
        await self._get_owned_recipe(request, recipe_id)
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
            unit = await Unit.find(unit_abbrev, owner_id=user_id)
            if unit:
                recipe_ingredient.unit = unit
            else:
                messages.append("Could not find unit, not saved.")
                valid = False
        else:
            messages.append("No unit found, not saved.")
            valid = False

        if ingredient_name is not None and str(ingredient_name).strip():
            ingredient, _ = await get_or_create_ingredient(
                user_id, str(ingredient_name).strip()
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
    async def delete_ingredient(
        self, request: Request, recipe_id: int, ingredient_id: int
    ) -> Template:
        """Delete an ingredient from a recipe."""
        recipe = await self._get_owned_recipe(request, recipe_id)
        recipe_ingredient = await RecipeIngredient.get_or_none(
            id=ingredient_id, recipe=recipe_id
        )
        if not recipe_ingredient:
            raise NotFoundException()

        await recipe_ingredient.delete()

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
    async def add_ingredient_form(self, request: Request, recipe_id: int) -> Template:
        """Show the form to add a new ingredient to a recipe."""
        await self._get_owned_recipe(request, recipe_id)

        return Template(
            template_name="partials/add-ingredient-form.html",
            context={"recipe_id": recipe_id},
        )

    @post(path="/{recipe_id:int}/ingredients/add", summary="Add ingredient to recipe")
    async def add_ingredient(
        self,
        request: Request,
        recipe_id: int,
        data: Annotated[
            dict[str, Any], Body(media_type=RequestEncodingType.URL_ENCODED)
        ],
    ) -> Template:
        """Add a new ingredient to a recipe."""
        user_id = await self._current_user_id(request)
        recipe = await self._get_owned_recipe(request, recipe_id)

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
            unit = await Unit.find(unit_abbrev, owner_id=user_id)
            if not unit:
                messages.append(f"Could not find unit: {unit_abbrev}")
            else:
                try:
                    ingredient, _ = await get_or_create_ingredient(
                        user_id, str(ingredient_name)
                    )
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
        user_id = await self._current_user_id(request)
        recipe = await self._get_owned_recipe(request, recipe_id)

        form_data = await request.form()
        submitted_tag_ids = (
            [int(tag_id) for tag_id in form_data.getall("tag_ids[]")]
            if "tag_ids[]" in form_data
            else []
        )

        valid_tag_ids = set(
            await Tag.filter(id__in=submitted_tag_ids, owner_id=user_id).values_list(
                "id", flat=True
            )
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
                "tag_groups": await self._tag_groups(user_id),
                "selected_tag_ids": await self._recipe_tag_ids(recipe.id),
                "messages": ["Recipe tags updated"],
            },
        )

    @get(
        path="/delete-confirmation/{recipe_id:int}", summary="Delete the recipe by ID."
    )
    async def delete_recipe_page(self, request: Request, recipe_id: int) -> Template:
        """Delete an owned recipe and return to the home page."""
        recipe = await self._get_owned_recipe(request, recipe_id)
        await recipe.delete()
        return Template(
            "index.html",
            context={
                "request": request,
                "messages": [f"Recipe deleted: {recipe.name}"],
            },
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
        owner_id = await self._current_user_id(request)
        return Template(
            template_name="search-recipes.html",
            context={
                "request": request,
                "tag_groups": await self._tag_groups(owner_id),
            },
        )

    @get(path="/search-recipe", summary="Search for recipes")
    async def search_by_query(
        self, request: Request, search: str | None = None
    ) -> Template:
        """Search recipes by text and optional tag-group filters."""
        tag_filters: dict[int, int] = {}
        for key, value in request.query_params.items():
            if not key.startswith("tag_group_") or not value:
                continue
            category_id_str = key.removeprefix("tag_group_")
            if not category_id_str.isdigit() or not value.isdigit():
                continue
            tag_filters[int(category_id_str)] = int(value)

        user_id = await self._current_user_id(request)
        include_public = self._wants_public(request)
        if not search and not tag_filters:
            recipes: list[Recipe] = []
        else:
            recipes = await Recipe.search(
                search,
                tag_filters=tag_filters,
                viewer_id=user_id,
                include_public=include_public,
            )

        return Template(
            template_name="search-results.html",
            context={
                "request": request,
                "recipes": recipes,
                "include_public": include_public,
            },
        )

    @get(summary="Show all recipes")
    async def showall(self, request: Request) -> list[RecipeSchema]:  # type: ignore
        """Show the current user's own recipes."""
        user_id = await self._current_user_id(request)
        return await RecipeSchema.from_queryset(Recipe.filter(owner_id=user_id))

    @get(path="/count", summary="Count the number of recipes")
    async def count(self, request: Request) -> int:
        """Count the current user's own recipes."""
        user_id = await self._current_user_id(request)
        return await Recipe.filter(owner_id=user_id).count()

    @get(path="/{recipe_id:int}/detail", summary="Get recipe details as HTML")
    async def get_recipe_detail(
        self, request: Request, recipe_id: int, search: str | None = None
    ) -> Template:
        """Get recipe details and re-render the search results with the selection."""
        user_id = await self._current_user_id(request)
        recipe = await Recipe.filter(
            self._visible_filter(user_id), id=recipe_id
        ).first()
        if recipe is None:
            raise NotFoundException()

        ingredients = await RecipeIngredient.filter(recipe=recipe_id).select_related(
            "ingredient", "unit"
        )

        include_public = self._wants_public(request)
        search_results: list[Recipe] = []
        if search:
            search_results = await Recipe.search(
                search, limit=10, viewer_id=user_id, include_public=include_public
            )

        return Template(
            template_name="partials/recipe-detail-and-search-results.html",
            context={
                "request": request,
                "recipe": recipe,
                "ingredients": ingredients,
                "recipes": search_results,
                "selected_id": recipe_id,
                "include_public": include_public,
            },
        )

    @get(path="/{recipe_id:int}", summary="Get one recipe by id")
    async def from_id(self, request: Request, recipe_id: int) -> RecipeSchema | None:  # type: ignore
        """Return one visible recipe as JSON."""
        recipe = await self._get_visible_recipe(request, recipe_id)
        return await RecipeSchema.from_tortoise_orm(recipe)

    @delete(path="/{recipe_id:int}", summary="Remove one recipe by id")
    async def delete(self, request: Request, recipe_id: int) -> None:
        """Delete an owned recipe via the JSON API."""
        recipe = await self._get_owned_recipe(request, recipe_id)
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
        owner_id = await self._current_user_id(request)
        owner = await get_current_user(request)
        recipe = await Recipe.create(
            name=name,
            description=description or name,
            prep_time_minutes=prep_time_minutes,
            cook_time_minutes=cook_time_minutes,
            servings=servings,
            owner=owner,
            creator=owner,
            private=True,
            enabled=True,
        )
        logger.debug(f"Added - {recipe.id=}")

        valid_tag_ids = await Tag.filter(id__in=tag_ids, owner_id=owner_id).values_list(
            "id", flat=True
        )
        for tag_id in set(valid_tag_ids):
            await RecipeTag.create(recipe=recipe, tag_id=tag_id)

        messages = []
        for ing_dict in ingredients:
            logger.debug(f"Adding ingredient: {ing_dict['name']}")
            ingredient, ing_created = await get_or_create_ingredient(
                owner_id, ing_dict["name"]
            )
            if ing_created:
                messages.append(f"Hey, I didn't know {ingredient.name} yet!")

            logger.debug(
                f"Finding unit by abbreviation/singular/plural: {ing_dict['unit']}"
            )
            unit = await Unit.find(ing_dict["unit"], owner_id=owner_id)
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

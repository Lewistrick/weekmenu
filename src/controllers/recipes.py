import random

from litestar import Controller, Request, delete, get, post
from litestar.exceptions import NotFoundException
from litestar.response import Template
from loguru import logger
from pydantic import BaseModel
from tortoise.contrib.pydantic import pydantic_model_creator

from src.models import Ingredient, Recipe, RecipeIngredient, Unit

RecipeSchema = pydantic_model_creator(Recipe, name="Recept")
IngredientSchema = pydantic_model_creator(Ingredient, name="Ingredient")


class RecipeIngredientDetail(BaseModel):
    name: str
    quantity: float
    unit: str


class RecipeController(Controller):
    path = "/recipes"
    tags = ["recipes"]

    @get(path="/search", summary="Search for recipes by name")
    async def search(self, request: Request, search: str | None = None) -> Template:
        if not search:
            recipes = []
        else:
            recipes = await Recipe.filter(name__icontains=search).limit(5)
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
    async def get_recipe_detail(self, request: Request, recipe_id: int) -> Template:
        recipe = await Recipe.get_or_none(id=recipe_id)
        if not recipe:
            raise NotFoundException()

        ingredients = await RecipeIngredient.filter(recipe=recipe_id).select_related("ingredient", "unit")

        return Template(
            template_name="recipe-detail.html",
            context={"request": request, "recipe": recipe, "ingredients": ingredients},
        )

    @get(path="/{recipe_id:int}", summary="Get one recipe by id")
    async def from_id(self, recipe_id: int) -> RecipeSchema | None:  # type: ignore
        recipe = await Recipe.get_or_none(id=recipe_id)
        if not recipe:
            raise NotFoundException()
        return await RecipeSchema.from_tortoise_orm(recipe)

    @get(path="/random-recipe", summary="Get a random recipe page")
    async def random_recipe_page(self, request: Request) -> Template:
        """Select one random recipe and show it."""
        recipes = await Recipe.all()
        random_recipe = random.choice(recipes)
        ingredients = await RecipeIngredient.filter(recipe=random_recipe.id).select_related("ingredient", "unit")

        return Template(
            template_name="recipe-detail.html",
            context={"request": request, "recipe": random_recipe, "ingredients": ingredients},
        )

    @get(path="/user-profile", summary="Get the user profile page")
    async def user_profile_page(self, request: Request) -> Template:
        """Show the user profile page."""
        return Template(template_name="user-profile.html", context={"request": request})

    @get(path="/{recipe_id:int}/ingredients", summary="Get detailed ingredient list.")
    async def ingredient_list(self, request: Request, recipe_id: int) -> Template:
        """Get the ingredient list for one recipe."""
        if not await Recipe.exists(id=recipe_id):
            raise NotFoundException()

        logger.debug(f"Getting ingredients for {recipe_id=}")
        ingredient_listing = await RecipeIngredient.filter(recipe=recipe_id).select_related("ingredient", "unit")

        return Template(
            template_name="ingredient-list.html",
            context={"request": request, "ingredients": ingredient_listing},
        )

    @delete(path="/{recipe_id:int}", summary="Remove one recipe by id")
    async def delete(self, recipe_id: int) -> None:
        recipe = await Recipe.get_or_none(id=recipe_id)
        if not recipe:
            raise NotFoundException()
        await recipe.delete()

    @post(name="Add a recipe")
    async def add(
        self,
        name: str,
        servings: int,
        description: str | None = None,
        prep_time_minutes: int | None = None,
        cook_time_minutes: int | None = None,
        ingredient_strings: list[str] | None = None,
    ) -> RecipeSchema:  # type: ignore
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

        logger.debug(f"Adding recipe: {name}")
        recipe = await Recipe.create(
            name=name,
            description=description or name,
            prep_time_minutes=prep_time_minutes,
            cook_time_minutes=cook_time_minutes,
            servings=servings,
        )
        logger.debug(f"Added - {recipe.id=}")

        if ingredient_strings:
            for ingredient_str in ingredient_strings:
                quantity, unit_abbrev, ing_name = ingredient_str.split("|", 2)

                logger.debug(f"Adding ingredient: {ing_name}")
                ingredient, ing_created = await Ingredient.get_or_create(name=ing_name)

                logger.debug(f"Adding unit by abbreviation: {unit_abbrev}")
                unit, unit_created = await Unit.get_or_create(abbrev=unit_abbrev)

                logger.debug("Listing ingredient in recipe")
                recipe_ing = await RecipeIngredient.create(
                    recipe_id=recipe,
                    ingredient_id=ingredient,
                    quantity=quantity,
                    unit_id=unit,
                )
                logger.info(f"Added ingredient to recipe: {recipe_ing}")

        logger.success("Created recipe")
        return await RecipeSchema.from_tortoise_orm(recipe)

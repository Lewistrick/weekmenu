from litestar import Controller, delete, get, post
from litestar.exceptions import NotFoundException
from loguru import logger
from tortoise.contrib.pydantic import pydantic_model_creator

from src.models import CarbType, Ingredient, Recipe, RecipeIngredient, Season, Unit

RecipeSchema = pydantic_model_creator(Recipe, name="Recept")


class RecipeController(Controller):
    path = "/recipes"
    tags = ["recipes"]

    @get(summary="Show all recipes")
    async def showall(self) -> list[RecipeSchema]:  # type: ignore
        """Show all recipes."""
        return await RecipeSchema.from_queryset(Recipe.all())

    @get(path="/count", summary="Count the number of recipes")
    async def count(self) -> int:
        """Count recipes."""
        q = await Recipe.all().count()
        return q

    @get(path="/{recipe_id:int}", summary="Get one recipe by id")
    async def from_id(self, recipe_id: int) -> RecipeSchema | None:  # type: ignore
        recipe = await Recipe.get_or_none(id=recipe_id)
        if not recipe:
            raise NotFoundException()
        return await RecipeSchema.from_tortoise_orm(recipe)

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
        season_name: str = "",
        carb_type_name: str = "",
    ) -> RecipeSchema:  # type: ignore
        """Create a new recipe, user-style.

        Accepts
        - a list of ingredients like this: quantity|unit|ingredient, e.g. 200|g|potatoes
        - season (e.g. summer, winter)
        - carb type (e.g. potato, pasta, rice)

        For any ingredient, unit, season or carbtype:
        - will check if it exists (note the web UI should do fuzzy matching to not get similar records)
        - add if it doesn't exist or select if it does
        - select the corresponding ID
        - link it to the new recipe
        """

        logger.debug(f"Adding season: {season_name}")
        season, season_created = await Season.get_or_create(name=season_name)
        logger.debug(f"Adding carbtype: {carb_type_name}")
        carbtype, carbtype_created = await CarbType.get_or_create(name=carb_type_name)

        logger.debug(f"Adding recipe: {name}")
        recipe = await Recipe.create(
            name=name,
            description=description or name,
            prep_time_minutes=prep_time_minutes,
            cook_time_minutes=cook_time_minutes,
            servings=servings,
            season_id=season,
            carbtype_id=carbtype,
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

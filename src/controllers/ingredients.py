from litestar import Controller, get, post
from litestar.exceptions import NotFoundException
from tortoise.contrib.pydantic import pydantic_model_creator

from src.models import Ingredient

IngredientSchema = pydantic_model_creator(Ingredient, name="Ingredient")


class IngredientController(Controller):
    path = "/ingredients"
    tags=["ingredients"]

    @get(summary="Show all ingredients.")
    async def show_all(self) -> list[IngredientSchema]: # type:ignore
        """Show all ingredients."""
        return await IngredientSchema.from_queryset(Ingredient.all())

    @get(path="/{id:int}", summary="Get an ingredient by id.")
    async def by_id(self, id: int) -> IngredientSchema: # type: ignore
        """Get a ingredient given an id."""
        record = await Ingredient.get_or_none(id=id)
        if not record:
            raise NotFoundException()
        return await IngredientSchema.from_tortoise_orm(record)

    @post(summary="Add an ingredient using name.")
    async def add(self, name: str) -> IngredientSchema: # type: ignore
        """Create a new ingredient by name."""
        record = await Ingredient.create(name=name)
        return await IngredientSchema.from_tortoise_orm(record)

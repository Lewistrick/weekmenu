"""Ingredient lookup and creation endpoints."""

from litestar import Controller, Request, get, post
from litestar.exceptions import NotFoundException
from tortoise.contrib.pydantic import pydantic_model_creator

from src.auth import get_current_user
from src.catalog import get_or_create_ingredient
from src.models import Ingredient

IngredientSchema = pydantic_model_creator(Ingredient, name="Ingredient")


class IngredientController(Controller):
    """List and create ingredients for the logged-in user."""

    path = "/ingredients"
    tags = ["ingredients"]

    @staticmethod
    async def _current_user_id(request: Request) -> int:
        """Return the logged-in user's id or raise when unauthenticated."""
        user = await get_current_user(request)
        if user is None:
            raise NotFoundException()
        return user.id

    @get(summary="Show all ingredients")
    async def showall(self, request: Request) -> list[IngredientSchema]:  # type: ignore
        """Show the current user's ingredients."""
        owner_id = await self._current_user_id(request)
        return await IngredientSchema.from_queryset(
            Ingredient.filter(owner_id=owner_id)
        )

    @get(path="/{id:int}", summary="Get an ingredient by id")
    async def from_id(self, request: Request, id: int) -> IngredientSchema:  # type: ignore
        """Get an ingredient owned by the current user."""
        owner_id = await self._current_user_id(request)
        record = await Ingredient.get_or_none(id=id, owner_id=owner_id)
        if not record:
            raise NotFoundException()
        return await IngredientSchema.from_tortoise_orm(record)

    @post(summary="Add an ingredient")
    async def add(self, request: Request, name: str) -> IngredientSchema:  # type: ignore
        """Create a new ingredient for the current user."""
        owner_id = await self._current_user_id(request)
        record, _ = await get_or_create_ingredient(owner_id, name)
        return await IngredientSchema.from_tortoise_orm(record)

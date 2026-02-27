from litestar import Controller, get, post
from litestar.exceptions import NotFoundException
from loguru import logger
from tortoise.contrib.pydantic import pydantic_model_creator

from src.models import Tag, TagCategory

TagSchema = pydantic_model_creator(Tag, name="Tag")


class TagController(Controller):
    path = "/tags"
    tags=["tags"]

    @get(summary="Show all tags.")
    async def show_all(self) -> list[TagSchema]: # type:ignore
        """Show all tags."""
        return await TagSchema.from_queryset(Tag.all())

    @get(path="/{id:int}", summary="Get a tag by id.")
    async def by_id(self, id: int) -> TagSchema: # type: ignore
        """Get a tag given an id."""
        record = await Tag.get_or_none(id=id)
        if not record:
            raise NotFoundException()
        return await TagSchema.from_tortoise_orm(record)

    @post(summary="Add a tag using name.")
    async def add(self, name: str, category: str) -> TagSchema: # type: ignore
        """Create a new tag, adding it to a category, by name."""
        cat, created = await TagCategory.get_or_create(name=category)
        if created:
            logger.info(f"Created tag category: {category}")

        record = await Tag.create(name=name, category=cat)
        return await TagSchema.from_tortoise_orm(record)

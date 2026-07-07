from litestar import Controller, Request, delete, get, post
from litestar.exceptions import NotFoundException
from litestar.response import Template
from loguru import logger
from tortoise.contrib.pydantic import pydantic_model_creator

from src.models import Tag, TagCategory

TagSchema = pydantic_model_creator(Tag, name="Tag")


class TagController(Controller):
    path = "/tags"
    tags = ["tags"]

    @staticmethod
    async def _groups() -> list[dict[str, object]]:
        """Return tag categories and their tags for template rendering."""
        groups: list[dict[str, object]] = []
        categories = await TagCategory.all().order_by("name")
        for category in categories:
            tags = await Tag.filter(category=category.id).order_by("name")
            groups.append({"category": category, "tags": tags})
        return groups

    @get(summary="Show all tags.")
    async def show_all(self) -> list[TagSchema]:  # type:ignore
        """Show all tags."""
        return await TagSchema.from_queryset(Tag.all())

    @get(path="/manage", summary="Manage tag groups")
    async def manage_page(self, request: Request) -> Template:
        """Show a page to add and edit tag groups and tag values."""
        return Template(
            template_name="manage-tags.html",
            context={"request": request, "groups": await self._groups()},
        )

    @get(path="/{id:int}", summary="Get a tag by id.")
    async def by_id(self, id: int) -> TagSchema:  # type: ignore
        """Get a tag given an id."""
        record = await Tag.get_or_none(id=id)
        if not record:
            raise NotFoundException()
        return await TagSchema.from_tortoise_orm(record)

    @post(summary="Add a tag using name.")
    async def add(self, name: str, category: str) -> TagSchema:  # type: ignore
        """Create a new tag, adding it to a category, by name."""
        cat, created = await TagCategory.get_or_create(name=category)
        if created:
            logger.info(f"Created tag category: {category}")

        record = await Tag.create(name=name, category=cat)
        return await TagSchema.from_tortoise_orm(record)

    @post(path="/groups", summary="Create a new tag group")
    async def add_group(self, request: Request) -> Template:
        """Create a tag group from form input."""
        form_data = await request.form()
        group_name = str(form_data.get("group_name", "")).strip()
        messages: list[str] = []
        if group_name:
            _, created = await TagCategory.get_or_create(name=group_name)
            if created:
                messages.append(f"Tag group added: {group_name}")
            else:
                messages.append(f"Tag group already exists: {group_name}")
        else:
            messages.append("Tag group name is required.")

        return Template(
            template_name="manage-tags.html",
            context={
                "request": request,
                "groups": await self._groups(),
                "messages": messages,
            },
        )

    @post(path="/groups/{group_id:int}", summary="Rename a tag group")
    async def edit_group(self, request: Request, group_id: int) -> Template:
        """Update a tag group's name from form input."""
        group = await TagCategory.get_or_none(id=group_id)
        if not group:
            raise NotFoundException()

        form_data = await request.form()
        new_name = str(form_data.get("group_name", "")).strip()
        messages: list[str] = []
        if new_name:
            group.name = new_name
            await group.save()
            messages.append(f"Updated tag group to: {new_name}")
        else:
            messages.append("Tag group name is required.")

        return Template(
            template_name="manage-tags.html",
            context={
                "request": request,
                "groups": await self._groups(),
                "messages": messages,
            },
        )

    @post(path="/groups/{group_id:int}/tags", summary="Add tag value to group")
    async def add_group_tag(self, request: Request, group_id: int) -> Template:
        """Create a new tag value in the provided group."""
        group = await TagCategory.get_or_none(id=group_id)
        if not group:
            raise NotFoundException()

        form_data = await request.form()
        tag_name = str(form_data.get("tag_name", "")).strip()
        messages: list[str] = []
        if tag_name:
            _, created = await Tag.get_or_create(name=tag_name, category=group)
            if created:
                messages.append(f"Added tag '{tag_name}' to {group.name}.")
            else:
                messages.append(f"Tag '{tag_name}' already exists in {group.name}.")
        else:
            messages.append("Tag name is required.")

        return Template(
            template_name="manage-tags.html",
            context={
                "request": request,
                "groups": await self._groups(),
                "messages": messages,
            },
        )

    @post(path="/values/{tag_id:int}", summary="Rename a tag value")
    async def edit_tag(self, request: Request, tag_id: int) -> Template:
        """Rename a tag value."""
        tag = await Tag.filter(id=tag_id).select_related("category").first()
        if not tag:
            raise NotFoundException()

        form_data = await request.form()
        new_name = str(form_data.get("tag_name", "")).strip()
        messages: list[str] = []
        if new_name:
            tag.name = new_name
            await tag.save()
            messages.append(f"Updated tag to: {new_name}")
        else:
            messages.append("Tag name is required.")

        return Template(
            template_name="manage-tags.html",
            context={
                "request": request,
                "groups": await self._groups(),
                "messages": messages,
            },
        )

    @delete(path="/values/{tag_id:int}", summary="Delete a tag value", status_code=200)
    async def delete_tag(self, request: Request, tag_id: int) -> Template:
        """Delete a tag value."""
        tag = await Tag.get_or_none(id=tag_id)
        if not tag:
            raise NotFoundException()

        tag_name = tag.name
        await tag.delete()
        return Template(
            template_name="manage-tags.html",
            context={
                "request": request,
                "groups": await self._groups(),
                "messages": [f"Deleted tag: {tag_name}"],
            },
        )

    @delete(
        path="/groups/{group_id:int}", summary="Delete empty tag group", status_code=200
    )
    async def delete_group(self, request: Request, group_id: int) -> Template:
        """Delete a tag group only when it has no tags."""
        group = await TagCategory.get_or_none(id=group_id)
        if not group:
            raise NotFoundException()

        tag_count = await Tag.filter(category_id=group_id).count()
        if tag_count > 0:
            warnings = [
                f"Cannot delete tag group '{group.name}' while it still has tags."
            ]
            messages: list[str] = []
        else:
            group_name = group.name
            await group.delete()
            messages = [f"Deleted tag group: {group_name}"]
            warnings = []

        return Template(
            template_name="manage-tags.html",
            context={
                "request": request,
                "groups": await self._groups(),
                "messages": messages,
                "warnings": warnings,
            },
        )

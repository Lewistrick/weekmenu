"""Tag and tag-category management endpoints."""

from litestar import Controller, Request, delete, get, post
from litestar.exceptions import NotFoundException
from litestar.response import Template
from loguru import logger
from tortoise.contrib.pydantic import pydantic_model_creator

from src.auth import get_current_user
from src.catalog import get_or_create_tag, get_or_create_tag_category
from src.i18n.service import t
from src.models import Tag, TagCategory

TagSchema = pydantic_model_creator(Tag, name="Tag")


def _parse_color(value: object, *, fallback: str) -> str:
    """Return a normalized hex color from form input."""
    text = str(value or "").strip()
    if len(text) == 7 and text.startswith("#"):
        return text.lower()
    return fallback


class TagController(Controller):
    """Manage tag groups and individual tags."""

    path = "/tags"
    tags = ["tags"]

    @staticmethod
    async def _current_user_id(request: Request) -> int:
        """Return the logged-in user's id or raise when unauthenticated."""
        user = await get_current_user(request)
        if user is None:
            raise NotFoundException()
        return user.id

    @classmethod
    async def _groups(cls, owner_id: int) -> list[dict[str, object]]:
        """Return tag categories and their tags for template rendering."""
        groups: list[dict[str, object]] = []
        categories = await TagCategory.filter(owner_id=owner_id).order_by("name")
        for category in categories:
            tags = await Tag.filter(owner_id=owner_id, category=category.id).order_by(
                "name"
            )
            groups.append({"category": category, "tags": tags})
        return groups

    @get(summary="Show all tags.")
    async def show_all(self, request: Request) -> list[TagSchema]:  # type:ignore
        """Show the current user's tags."""
        owner_id = await self._current_user_id(request)
        return await TagSchema.from_queryset(Tag.filter(owner_id=owner_id))

    @get(path="/manage", summary="Manage tag groups")
    async def manage_page(self, request: Request) -> Template:
        """Show a page to add and edit tag groups and tag values."""
        owner_id = await self._current_user_id(request)
        return Template(
            template_name="manage-tags.html",
            context={"request": request, "groups": await self._groups(owner_id)},
        )

    @get(path="/{id:int}", summary="Get a tag by id.")
    async def by_id(self, request: Request, id: int) -> TagSchema:  # type: ignore
        """Get a tag owned by the current user."""
        owner_id = await self._current_user_id(request)
        record = await Tag.get_or_none(id=id, owner_id=owner_id)
        if not record:
            raise NotFoundException()
        return await TagSchema.from_tortoise_orm(record)

    @post(summary="Add a tag using name.")
    async def add(self, request: Request, name: str, category: str) -> TagSchema:  # type: ignore
        """Create a new tag in a category for the current user."""
        owner_id = await self._current_user_id(request)
        cat, created = await get_or_create_tag_category(owner_id, category)
        if created:
            logger.info(f"Created tag category: {category}")

        tag, _ = await get_or_create_tag(owner_id, name, cat)
        return await TagSchema.from_tortoise_orm(tag)

    @post(path="/groups", summary="Create a new tag group")
    async def add_group(self, request: Request) -> Template:
        """Create a tag group from form input."""
        owner_id = await self._current_user_id(request)
        form_data = await request.form()
        group_name = str(form_data.get("group_name", "")).strip()
        background_color = _parse_color(
            form_data.get("background_color"), fallback="#2563eb"
        )
        foreground_color = _parse_color(
            form_data.get("foreground_color"), fallback="#ffffff"
        )
        messages: list[str] = []
        if group_name:
            group, created = await get_or_create_tag_category(
                owner_id,
                group_name,
                background_color=background_color,
                foreground_color=foreground_color,
            )
            if not created:
                group.background_color = background_color
                group.foreground_color = foreground_color
                await group.save()
            if created:
                messages.append(t("message.tags.group_added", name=group_name))
            else:
                messages.append(t("message.tags.group_exists", name=group_name))
        else:
            messages.append(t("message.tags.group_name_required"))

        return Template(
            template_name="manage-tags.html",
            context={
                "request": request,
                "groups": await self._groups(owner_id),
                "messages": messages,
            },
        )

    @post(path="/groups/{group_id:int}", summary="Rename a tag group")
    async def edit_group(self, request: Request, group_id: int) -> Template:
        """Update a tag group's name from form input."""
        owner_id = await self._current_user_id(request)
        group = await TagCategory.get_or_none(id=group_id, owner_id=owner_id)
        if not group:
            raise NotFoundException()

        form_data = await request.form()
        new_name = str(form_data.get("group_name", "")).strip()
        background_color = _parse_color(
            form_data.get("background_color"),
            fallback=group.background_color,
        )
        foreground_color = _parse_color(
            form_data.get("foreground_color"),
            fallback=group.foreground_color,
        )
        messages: list[str] = []
        if new_name:
            group.name = new_name
        group.background_color = background_color
        group.foreground_color = foreground_color
        await group.save()
        if new_name:
            messages.append(t("message.tags.group_renamed", name=new_name))
        else:
            messages.append(t("message.tags.group_name_required"))

        return Template(
            template_name="manage-tags.html",
            context={
                "request": request,
                "groups": await self._groups(owner_id),
                "messages": messages,
            },
        )

    @post(path="/groups/{group_id:int}/tags", summary="Add tag value to group")
    async def add_group_tag(self, request: Request, group_id: int) -> Template:
        """Create a new tag value in the provided group."""
        owner_id = await self._current_user_id(request)
        group = await TagCategory.get_or_none(id=group_id, owner_id=owner_id)
        if not group:
            raise NotFoundException()

        form_data = await request.form()
        tag_name = str(form_data.get("tag_name", "")).strip()
        messages: list[str] = []
        if tag_name:
            _, created = await get_or_create_tag(owner_id, tag_name, group)
            if created:
                messages.append(
                    t("message.tags.tag_added", tag=tag_name, group=group.name)
                )
            else:
                messages.append(
                    t("message.tags.tag_exists", tag=tag_name, group=group.name)
                )
        else:
            messages.append(t("message.tags.tag_name_required"))

        return Template(
            template_name="manage-tags.html",
            context={
                "request": request,
                "groups": await self._groups(owner_id),
                "messages": messages,
            },
        )

    @post(path="/values/{tag_id:int}", summary="Rename a tag value")
    async def edit_tag(self, request: Request, tag_id: int) -> Template:
        """Rename a tag value."""
        owner_id = await self._current_user_id(request)
        tag = (
            await Tag.filter(id=tag_id, owner_id=owner_id)
            .select_related("category")
            .first()
        )
        if not tag:
            raise NotFoundException()

        form_data = await request.form()
        new_name = str(form_data.get("tag_name", "")).strip()
        messages: list[str] = []
        if new_name:
            tag.name = new_name
            await tag.save()
            messages.append(t("message.tags.tag_renamed", name=new_name))
        else:
            messages.append(t("message.tags.tag_name_required"))

        return Template(
            template_name="manage-tags.html",
            context={
                "request": request,
                "groups": await self._groups(owner_id),
                "messages": messages,
            },
        )

    @delete(path="/values/{tag_id:int}", summary="Delete a tag value", status_code=200)
    async def delete_tag(self, request: Request, tag_id: int) -> Template:
        """Delete a tag value."""
        owner_id = await self._current_user_id(request)
        tag = await Tag.get_or_none(id=tag_id, owner_id=owner_id)
        if not tag:
            raise NotFoundException()

        tag_name = tag.name
        await tag.delete()
        return Template(
            template_name="manage-tags.html",
            context={
                "request": request,
                "groups": await self._groups(owner_id),
                "messages": [t("message.tags.tag_deleted", name=tag_name)],
            },
        )

    @delete(
        path="/groups/{group_id:int}", summary="Delete empty tag group", status_code=200
    )
    async def delete_group(self, request: Request, group_id: int) -> Template:
        """Delete a tag group only when it has no tags."""
        owner_id = await self._current_user_id(request)
        group = await TagCategory.get_or_none(id=group_id, owner_id=owner_id)
        if not group:
            raise NotFoundException()

        tag_count = await Tag.filter(category_id=group_id, owner_id=owner_id).count()
        if tag_count > 0:
            warnings = [t("message.tags.group_delete_has_tags", name=group.name)]
            messages: list[str] = []
        else:
            group_name = group.name
            await group.delete()
            messages = [t("message.tags.group_deleted", name=group_name)]
            warnings = []

        return Template(
            template_name="manage-tags.html",
            context={
                "request": request,
                "groups": await self._groups(owner_id),
                "messages": messages,
                "warnings": warnings,
            },
        )

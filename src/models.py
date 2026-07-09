from typing import cast

from tortoise.expressions import Q
from tortoise.fields import (
    SET_NULL,
    BooleanField,
    FloatField,
    ForeignKeyField,
    IntField,
    TextField,
)
from tortoise.models import Model


class Recipe(Model):
    """A recipe for your cookbook."""

    id = IntField(primary_key=True)
    name = TextField(required=True)
    description = TextField()
    prep_time_minutes = IntField()
    cook_time_minutes = IntField()
    servings = IntField()
    owner = ForeignKeyField("models.User", related_name="recipes")
    creator = ForeignKeyField(
        "models.User",
        related_name="created_recipes",
        null=True,
        on_delete=SET_NULL,
    )
    imported_from = ForeignKeyField(
        "models.Recipe",
        related_name="imports",
        null=True,
        on_delete=SET_NULL,
    )
    private = BooleanField(default=True)
    enabled = BooleanField(default=True)

    @classmethod
    async def search(
        cls,
        query: str | None = None,
        *,
        tag_filters: dict[int, int] | None = None,
        limit: int | None = None,
        viewer_id: int | None = None,
        include_public: bool = False,
    ) -> list["Recipe"]:
        """Return recipes matching text and optional tag-group filters.

        Args:
            query: Optional text to match case-insensitively.
            tag_filters: Mapping of tag-category id to selected tag id.
            limit: Optional maximum number of recipes to return.
            viewer_id: When given, restrict results to recipes owned by this
                user (plus public recipes when ``include_public`` is set).
            include_public: When ``True`` and ``viewer_id`` is given, also
                include other users' public (non-private) recipes.

        Returns:
            Distinct recipes that match the query.
        """
        queryset = cls.all()
        if viewer_id is not None:
            visibility = Q(owner_id=viewer_id)
            if include_public:
                visibility |= Q(private=False)
            queryset = queryset.filter(visibility)
        if query:
            filters = (
                Q(name__icontains=query)
                | Q(description__icontains=query)
                | Q(recipe__ingredient__name__icontains=query)
            )
            queryset = queryset.filter(filters)

        if tag_filters:
            for _category_id, tag_id in tag_filters.items():
                matching_recipe_ids = await RecipeTag.filter(tag_id=tag_id).values_list(
                    "recipe_id", flat=True
                )
                queryset = queryset.filter(Q(id__in=matching_recipe_ids))

        queryset = queryset.distinct()
        if limit is not None:
            queryset = queryset.limit(limit)
        return cast("list[Recipe]", await queryset)


class Ingredient(Model):
    """Any ingredient (to add quantity and unit, see RecipeIngredient)."""

    id = IntField(primary_key=True)
    name = TextField(required=True)
    owner = ForeignKeyField("models.User", related_name="ingredients")


class TagCategory(Model):
    """A category of tags."""

    id = IntField(primary_key=True)
    name = TextField(required=True)
    owner = ForeignKeyField("models.User", related_name="tag_categories")


class Tag(Model):
    """A tag belonging to a recipe.

    A tag has a name and a category.

    category  | example tags
    --------- | -------------------------
    season    | summer, winter, any, etc.
    carb_type | potato, rice, pasta, etc.
    diet      | vegan, fodmap, etc.
    """

    id = IntField(primary_key=True)
    category = ForeignKeyField("models.TagCategory", "category")
    name = TextField(required=True)
    owner = ForeignKeyField("models.User", related_name="tags")


class RecipeTag(Model):
    """A tag linked to a category."""

    id = IntField(primary_key=True)
    recipe = ForeignKeyField("models.Recipe", "tagged_recipe")
    tag = ForeignKeyField("models.Tag", name="recipe_tag")


class RecipeIngredient(Model):
    """An ingredient in a recipe listing, including quantity and unit."""

    id = IntField(primary_key=True)
    recipe = ForeignKeyField("models.Recipe", "recipe")
    ingredient = ForeignKeyField("models.Ingredient", "ingredient")
    quantity = FloatField(required=True)
    unit = ForeignKeyField("models.Unit", "unit")

    def __str__(self):
        unit_name = Unit.get(id=self.unit).values("abbrev")
        ingredient_name = Ingredient.get(id=self.ingredient).values("name")
        return f"{self.quantity} {unit_name} {ingredient_name}"


class User(Model):
    """An application user who owns recipes and shopping preferences."""

    id = IntField(primary_key=True)
    username = TextField(required=True)
    email = TextField(null=True)
    password_hash = TextField(null=True)

    @classmethod
    async def get_by_username(cls, username: str) -> "User | None":
        """Return the user with the given username, if any.

        Args:
            username: Case-sensitive username to look up.

        Returns:
            The matching user, or ``None`` when no user has that username.
        """
        return await cls.filter(username=username).first()


class Shop(Model):
    id = IntField(primary_key=True)
    name = TextField(required=True)
    owner = ForeignKeyField("models.User", related_name="shops")


class UserIngredientShop(Model):
    id = IntField(primary_key=True)
    user = ForeignKeyField("models.User", related_name="ingredient_shops")
    ingredient = ForeignKeyField("models.Ingredient", related_name="user_shops")
    shop = ForeignKeyField("models.Shop", related_name="user_ingredients", null=True)


class Unit(Model):
    """A unit of measurement for an ingredient in a recipe, e.g. pieces, grams, liters."""

    id = IntField(primary_key=True)
    abbrev = TextField(required=True)
    single = TextField(null=True)
    plural = TextField(null=True)
    owner = ForeignKeyField("models.User", related_name="units")

    @classmethod
    async def find(cls, query: str, *, owner_id: int) -> "Unit | None":
        """Find a unit abbreviation or label for a specific user."""
        return await cls.filter(
            Q(owner_id=owner_id)
            & (Q(abbrev=query) | Q(single=query) | Q(plural=query)),
        ).first()

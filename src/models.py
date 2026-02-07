from tortoise.fields import FloatField, ForeignKeyField, IntField, TextField
from tortoise.models import Model


class Recipe(Model):
    """A recipe for your cookbook."""

    id = IntField(primary_key=True)
    name = TextField(required=True)
    description = TextField()
    prep_time_minutes = IntField()
    cook_time_minutes = IntField()
    servings = IntField()


class Ingredient(Model):
    """Any ingredient (to add quantity and unit, see RecipeIngredient)."""

    id = IntField(primary_key=True)
    name = TextField(required=True)


class TagCategory(Model):
    """A category of tags."""

    id = IntField(primary_key=True)
    name = TextField(required=True)


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
    category = ForeignKeyField("models.Category", "")
    name = TextField(required=True)


class RecipeTag:
    """A tag linked to a category."""

    id = IntField(primary_key=True)
    recipe = ForeignKeyField("models.Recipe", "recipe")
    tag = ForeignKeyField("models.Tag", name="tag")


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


class Unit(Model):
    """A unit of measurement for an ingredient in a recipe, e.g. pieces, grams, liters."""

    id = IntField(primary_key=True)
    abbrev = TextField(required=True)
    single = TextField(null=True)
    plural = TextField(null=True)

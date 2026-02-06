from tortoise.fields import FloatField, ForeignKeyField, IntField, TextField
from tortoise.models import Model


class Season(Model):
    """A season a recipe belongs in, e.g. summer, winter, all."""

    id = IntField(primary_key=True)
    name = TextField(required=True)


class CarbType(Model):
    """The carb type of a model, e.g. potato, pasta, rice."""

    id = IntField(primary_key=True)
    name = TextField(required=True)


class Recipe(Model):
    """A recipe for your cookbook."""

    id = IntField(primary_key=True)
    name = TextField(required=True)
    description = TextField()
    prep_time_minutes = IntField()
    cook_time_minutes = IntField()
    servings = IntField()
    season_id = ForeignKeyField("models.Season")
    carbtype_id = ForeignKeyField("models.CarbType")


class Ingredient(Model):
    """Any ingredient (to add quantity and unit, see RecipeIngredient)."""

    id = IntField(primary_key=True)
    name = TextField(required=True)


class RecipeIngredient(Model):
    """An ingredient in a recipe listing, including quantity and unit."""

    id = IntField(primary_key=True)
    recipe_id = ForeignKeyField("models.Recipe", "recipe")
    ingredient_id = ForeignKeyField("models.Ingredient", "ingredient")
    quantity = FloatField(required=True)
    unit_id = ForeignKeyField("models.Unit", "unit")

    def __str__(self):
        unit_name = Unit.get(id=self.unit_id).values("abbrev")
        ingredient_name = Ingredient.get(id=self.ingredient_id).values("name")
        return f"{self.quantity} {unit_name} {ingredient_name}"


class Unit(Model):
    """A unit of measurement for an ingredient in a recipe, e.g. pieces, grams, liters."""

    id = IntField(primary_key=True)
    abbrev = TextField(required=True)
    single = TextField(null=True)
    plural = TextField(null=True)

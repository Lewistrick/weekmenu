"""Add the weekly grocery table."""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    """Create the weekly grocery table."""
    return """
        CREATE TABLE IF NOT EXISTS "weeklygrocery" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "quantity" REAL NOT NULL,
    "ingredient_id" INT NOT NULL REFERENCES "ingredient" ("id") ON DELETE CASCADE,
    "owner_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE,
    "unit_id" INT NOT NULL REFERENCES "unit" ("id") ON DELETE CASCADE
) /* A recurring grocery a user buys every week, unrelated to the week menu. */;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    """Drop the weekly grocery table."""
    return """
        DROP TABLE IF EXISTS "weeklygrocery";"""


MODELS_STATE = (
    "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"
)

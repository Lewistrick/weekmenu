from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "inventoryitem" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "quantity" REAL NOT NULL DEFAULT 0,
    "created_at" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "ingredient_id" INT NOT NULL REFERENCES "ingredient" ("id") ON DELETE CASCADE,
    "owner_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE,
    "unit_id" INT NOT NULL REFERENCES "unit" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_inventoryit_owner_i_96c3b1" UNIQUE ("owner_id", "ingredient_id", "unit_id")
) /* An amount of one ingredient (in one unit) a user has in stock at home. */;
        ALTER TABLE "grocerylistitem" ADD "inventory_quantity" REAL NOT NULL DEFAULT 0;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "grocerylistitem" DROP COLUMN "inventory_quantity";
        DROP TABLE IF EXISTS "inventoryitem";"""


MODELS_STATE = (
    "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"
)

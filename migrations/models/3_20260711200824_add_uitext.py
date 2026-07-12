from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "uitext" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "language_code" TEXT NOT NULL,
    "key" TEXT NOT NULL,
    "text" TEXT NOT NULL,
    CONSTRAINT "uid_uitext_languag_fc2ab6" UNIQUE ("language_code", "key")
) /* Localized UI string stored in the database catalog. */;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "uitext";"""


MODELS_STATE = (
    "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"
    "OPhhGT/+DymAZU0="
)

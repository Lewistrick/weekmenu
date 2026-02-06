from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "carbtype" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "name" TEXT NOT NULL
) /* The carb type of a model, e.g. potato, pasta, rice. */;
CREATE TABLE IF NOT EXISTS "ingredient" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "name" TEXT NOT NULL
) /* Any ingredient (to add quantity and unit, see RecipeIngredient). */;
CREATE TABLE IF NOT EXISTS "season" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "name" TEXT NOT NULL
) /* A season a recipe belongs in, e.g. summer, winter, all. */;
CREATE TABLE IF NOT EXISTS "recipe" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "name" TEXT NOT NULL,
    "description" TEXT NOT NULL,
    "prep_time_minutes" INT NOT NULL,
    "cook_time_minutes" INT NOT NULL,
    "servings" INT NOT NULL,
    "carbtype_id_id" INT NOT NULL REFERENCES "carbtype" ("id") ON DELETE CASCADE,
    "season_id_id" INT NOT NULL REFERENCES "season" ("id") ON DELETE CASCADE
) /* A recipe for your cookbook. */;
CREATE TABLE IF NOT EXISTS "unit" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "abbrev" TEXT NOT NULL,
    "single" TEXT,
    "plural" TEXT
) /* A unit of measurement for an ingredient in a recipe, e.g. pieces, grams, liters. */;
CREATE TABLE IF NOT EXISTS "recipeingredient" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "quantity" REAL NOT NULL,
    "ingredient_id_id" INT NOT NULL REFERENCES "ingredient" ("id") ON DELETE CASCADE,
    "recipe_id_id" INT NOT NULL REFERENCES "recipe" ("id") ON DELETE CASCADE,
    "unit_id_id" INT NOT NULL REFERENCES "unit" ("id") ON DELETE CASCADE
) /* An ingredient in a recipe listing, including quantity and unit. */;
CREATE TABLE IF NOT EXISTS "aerich" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "version" VARCHAR(255) NOT NULL,
    "app" VARCHAR(100) NOT NULL,
    "content" JSON NOT NULL
);"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        """


MODELS_STATE = (
    "eJztmu9v2jgYx/8Vi1erxFUb627TvaOM3nHrwYmy06RpikxigtXETm2nLZr6v5/tJDgkTm"
    "haWsHIiwr6+Hkc54P99eMfPzsh9VDATweQzWerCHX+AD87BIbqS6msCzowikyJMgg4D7Sz"
    "K71E5jXngkFXSPsCBhxJk4e4y3AkMCXKe7ZEQEUAFQLoAkCg6+wCdOqfgogKKGgXRJAL2A"
    "UMu+hUVexRV9aMif+MOmKCb2LkCOojsURM1vT9hzRj4qF7xLN/o2tngVHgbQDBnqpA2x2R"
    "0OqMiLjQjqp5c8elQRwS4xytxJKStTcmQll9RBCDAqnqBYsVIBIHQcoyY5a01LgkTczFeG"
    "gB40BhVtElypkxBy01uZSoX0i2husX9NVTfuu9O/t49un972efpItuydry8SF5PfPuSaAm"
    "MJ51HnQ5FDDx0BgNN/1ZIjdD9xXoMv8CPNnkIrwMVR29zGDwmU65G341cGbDbzPV6JDzm0"
    "AZxv/1p4O/+tM3//S/neiSVVpyORn/mblTOXyScTUeXE7OJV/VKRfXObzKMIfu9R1knrNR"
    "YsAz5GLVmhL78zTw4ssUBVC/b5l3Ov6nupK9Jm+s6eDQuGiPVvEqF4W9sGiBBPq61erZ6k"
    "kpkBHxGfIw0k8ryWWutFYw8abfVsnskxUwMeCNoAB6HriJIRFYrAAkHpDkRRdwhEDyo5m2"
    "nJT1cxcVtmLaiumxiOnmgH2unm7KxN7+DK+rrOlUY1FVMwlVKyozPtvVFCTeYEEZWNGYAZ"
    "fS67n8swhlvW+rga0GHqAGdnP9MN/MBlgLYS1dO92IocgROEROiEksbPl45aC3xm7XgP0A"
    "vRsZMCCV7D4VpDX2WEFyxG7l85rwy4ccK7Zsj8vBntNo6i4HHitCjiCX790UYDHsmPCVFi"
    "sWmmWUF5Qh7JMvaKWJjmSzIHFtWVCaYV/puvYTY9ViRJoZvFsn1qVuIr/Ld0NCv+egfzXo"
    "fx52qob0Dhjmt8oPl2JZrewcH78D2S6YX3TBXL8hacO3bRHdfHMyv5WICYDZmjnAXMiirj"
    "S6QezJr+UdRtve5LPra5flr74sz34Ii5IGFFbwywcVKC5U1F6Pdhunz5Ov55dD8O90OBhd"
    "jSbjjVVjUqhM0oATQZ0O+5eFNMl0/sapki30mNKlPMZEMxojLIYdKz6lpY3hbQYdE7qaRH"
    "3do3aQZB7ieWwxxSyOsO2J+oas7YDioaaTRZI2ud9OMx2kO+D4VdZ02AQ3BavpUucls/t0"
    "SW7J6c1ivTqT58bnEcdhibfJs+cooMTnMs1O71PxOAwR64I7SVJ9wiCwHZU9uZ42X2+P0Q"
    "7woKe9l7U3myF6KrKIZTZFVUtlnHk8QiiVr7ptGkqhixkK1QaFuhgAq7YssvuoGLmId4HP"
    "YCg/1OKPcZuC7v4BrbS+urTC+Zyh2ybiaiJaebWfo3PZmKDRhGUinsQ07XO/MNIoiBkMmi"
    "A1ES3S5yUB2aTTHoy8QC7QRwy7S1s2kJbU5gPQ+GzLCKoxtLPuq8+6tzLjsd5hGywhs9PL"
    "hRzKvCt7/b0TIOIL1cF7Hz7UMMsETXqdFLQrLeolZZvzghoaDSCm7ocJ8N3bt48AKL0qAe"
    "qy4lU1Iqw3xf++moyrbqitQwog5QKGku8edkVXn3/+2E+sNRTVW9fPtMVJVVGgXMipjWcV"
    "NJxpdz+9PPwPiwd5Yg=="
)

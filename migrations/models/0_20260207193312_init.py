from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "ingredient" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "name" TEXT NOT NULL
) /* Any ingredient (to add quantity and unit, see RecipeIngredient). */;
CREATE TABLE IF NOT EXISTS "recipe" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "name" TEXT NOT NULL,
    "description" TEXT NOT NULL,
    "prep_time_minutes" INT NOT NULL,
    "cook_time_minutes" INT NOT NULL,
    "servings" INT NOT NULL
) /* A recipe for your cookbook. */;
CREATE TABLE IF NOT EXISTS "tagcategory" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "name" TEXT NOT NULL
) /* A category of tags. */;
CREATE TABLE IF NOT EXISTS "tag" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "name" TEXT NOT NULL,
    "category_id" INT NOT NULL REFERENCES "tagcategory" ("id") ON DELETE CASCADE
) /* A tag belonging to a recipe. */;
CREATE TABLE IF NOT EXISTS "unit" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "abbrev" TEXT NOT NULL,
    "single" TEXT,
    "plural" TEXT
) /* A unit of measurement for an ingredient in a recipe, e.g. pieces, grams, liters. */;
CREATE TABLE IF NOT EXISTS "recipeingredient" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "quantity" REAL NOT NULL,
    "ingredient_id" INT NOT NULL REFERENCES "ingredient" ("id") ON DELETE CASCADE,
    "recipe_id" INT NOT NULL REFERENCES "recipe" ("id") ON DELETE CASCADE,
    "unit_id" INT NOT NULL REFERENCES "unit" ("id") ON DELETE CASCADE
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
    "eJztmltv2zYUgP8K4acGUIzWS9dib46bbF4ze3DcoUBTGLR0rAiRSIWkkhhd/vtISrIupm"
    "QrdQJ7UYDAybnw8ok855DWj05AHfB5d0hcBo4HRHR+Qz86BAcg/zBoLdTBYZjplEDgua/N"
    "vaLdnAuGbdXiAvscpMgBbjMvFB4lyr5PlijzQW8ERdhx0G2EifDEEmHioIh4wkIcAE3A9k"
    "LIxnLUVb041JbdyFZ21aDU30YwE9QFcQ1MNvvtu6Xm5sAD8PTf8Ga28MB3Crg8RzWg5TOx"
    "DLVsSMS5NlRjnc9s6kcByYzDpbimZGXtxehcIMCwANW8YJFCRyLfTzinNOORZibxEHM+Di"
    "xw5KsHoLzX+KfCHMFEZFOinp0cDdcTdFUvx713Jx9OPv7y68lHaaJHspJ8eIynl809dtQE"
    "RtPOo9ZjgWMLjTHjpj/XyE3hoQJdal+CJ4dchpeiqqOXCjJ82XLdDb8aONOzr1M16IDzW1"
    "8JRv/0J4M/+pM3f/W/HmnNMtFcjEe/p+ZUbqx4z40GF+NTyVctysVNDq8SzLF9c4+ZMyto"
    "cgu2sGGL+E8T3/PPE/CxnvI68iRAlHfSXj+GTJrsFM2O9mgVvHVV0AvKEkywq0et+lY9Fd"
    "CYomqiqY2oLLPZHE1RbI0WlKEljRiyKb2Zy19DoKy3bWNgGwMPMAZauXWYH2YDrCW3lq6Z"
    "bsggnAkvgFngkUgAb7Dpjb6bY8B+gN5NGMhAqrD7VJBG39cKkgO7k/014Zd3eU3YnlQqZp"
    "VIWyY+W5lYfww34dtUOjY/kucP0B5BOK0UfY8LqbKk0PYjR/65fq42nch/ur22GH3xYjR9"
    "EOv0zn2KK/jlnUoUF8prr3e7idOn8ZfTizP09+RsMLwcjkeFWilWKpEUeEJPc3LWvyilpW"
    "zxz5otxrLfa0pQeYBxtGgGr+DzWsGp+NkMW87jNUFbK4c2Fz3nlIHnks+w1CSHckyY2Kbz"
    "+Npdz/4xrKp3pJjh+1VWLe4qOUU5MYjj3qB/Oeh/OutURL4d8DvUmrHMcC2sb+aoduUOCH"
    "5JmjlcdrnwZKZWfYx5zsp9it2OoVhX4tr6XCQGW9zrSlM0B58SV1XJ6kutpIg2XexWG1+R"
    "KxLrrzGXYjViXWpjZMsV4VK21DbpPwj9i+ABB6EPyotfkeP0R2qOq36uCAfMKUFINcCjIA"
    "BmoXv5YNUnJksLgbC7qh8218tUmoVUYEEtxDxbIgixXM6pmdwuAqG4tTtwMbHQgjoBDmOD"
    "9ojQ3lc/X1R6sRvVdNM1K9lKXm3ZVmC5g7Qpw/gg19r+odw2e5ZWyp5l0BVjcybNP4LajJ"
    "p/8ttk1lWqowud4kwJ1WjTZpw24xxgxnnS1X91OG1y+Z8UxHvL/WXv+/VxzBDs0mNadZRL"
    "z4PbhDdlq8JWIAvyiEGg7uDVGx+46lZeltRdt4tCD2zgFnIZDuSHut9kxti4+w7awPrigR"
    "XP5wzumoTWzKMNruZynsvB+I3SVebxJKbJmvsfIw39iGG/CdLMo0X6cyWA+RKy/e5/J7VA"
    "H5hnX5uqgURTWw/gzGZTRVCNoc26L55172TFY3w5cXCNmZlezuVQ8q5c9Q8zH4gr1ALvvX"
    "9fwywNaNLqqBS7ElUv1hXzgtoaDSAm5ocJ8N3bt1sAlFaVALWu/A4iEcav6f68HI+qXj1c"
    "uZRAygMMJd8czxaWfsXn+35iraGoZl2factJVVGgXMjUxtMGGmba3aeXx/8ArsZbVg=="
)

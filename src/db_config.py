TORTOISE_CONFIG = {
    "connections": {"default": "sqlite://src/recipes.sqlite3"},
    "apps": {
        "models": {
            "models": ["src.models", "aerich.models"],
            "default_connection": "default",
        }
    },
}

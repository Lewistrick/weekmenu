# Weekmenu

## Usage
### To start the app
- `uv run litestar --app src.app:app run -r`
    - (remove `-r` when not editing the code)

### What will it be able to do
- Compose your own cookbook
- Create a random week menu, giving you a random recipe for each day of the week
- Generate a grocery list given a week menu

### To see the API docs
- [http://127.0.0.1:8000/schema/swagger](http://127.0.0.1:8000/schema/swagger)

## Database
### To view the database diagram:
- go to [dbdiagram.io](dbdiagram.io)
- click `create your diagram`
- paste the content of `dbdiagram.txt` inside the left panel

### Basic structure
- The `recipes` table is the center of the database
    - It contains a description, prep and cook time, and number of servings
- Each recipe has a number of ingredients in `recipe_ingredients`
    - foreign key `recipe_ingredients.id` = `recipe.id`
- Each recipe_ingredient points to a food in `ingredients` and a unit in `units`
    - foreign key `ingredients.id` = `recipe_ingredients.ingredient_id`
    - foreign key `units.unit_id` = `recipe_ingredients.unit_id`
- Each recipe has a season and a carb type attached
    - foreign key `seasons.id` = `recipes.season_id`
    - foreign key `carb_types.id` = `recipes.carb_type_id`

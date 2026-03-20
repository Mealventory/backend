from core.supabase_client import supabase

def get_recipes():
    response = (
        supabase.table("recipes")
        .select("""
            *,
            recipe_ingredients(
                food_item_id,
                quantity,
                unit,
                food_items(id, name, category, default_unit, barcode, typical_shelf_life_days)
            )
        """)
        .execute()
    )
    return response.data

def get_recipe_by_id(recipe_id: int):
    response = (
        supabase.table("recipes")
        .select("""
            *,
            recipe_ingredients(
                food_item_id,
                quantity,
                unit,
                food_items(id, name, category, default_unit, barcode, typical_shelf_life_days)
            )
        """)
        .eq("id", recipe_id)
        .execute()
    )
    return response.data

def create_recipe(recipe_data: dict):
    response = supabase.table("recipes").insert(recipe_data).execute()
    return response.data

def update_recipe(recipe_id: int, recipe_data: dict):
    response = supabase.table("recipes").update(recipe_data).eq("id", recipe_id).execute()
    return response.data

def delete_recipe(recipe_id: int):
    response = supabase.table("recipes").delete().eq("id", recipe_id).execute()
    return response.data

def get_recipe_availability(recipe_id: int):
    recipe_response = (
        supabase.table("recipes")
        .select("""
            *,
            recipe_ingredients(
                food_item_id,
                quantity,
                unit,
                food_items(id, name, category, default_unit, barcode, typical_shelf_life_days)
            )
        """)
        .eq("id", recipe_id)
        .execute()
    )

    if not recipe_response.data:
        return None

    recipe = recipe_response.data[0]

    inventory_response = (
        supabase.table("inventory")
        .select("food_item_id, quantity, unit")
        .execute()
    )

    inventory_items = inventory_response.data or []

    inventory_map = {}
    for item in inventory_items:
        food_item_id = item["food_item_id"]
        inventory_map[food_item_id] = inventory_map.get(food_item_id, 0) + item["quantity"]

    available_ingredients = []
    missing_ingredients = []

    for ingredient in recipe.get("recipe_ingredients", []):
        food_item_id = ingredient["food_item_id"]
        required_quantity = ingredient["quantity"]
        available_quantity = inventory_map.get(food_item_id, 0)

        ingredient_result = {
            "food_item_id": food_item_id,
            "name": ingredient["food_items"]["name"] if ingredient.get("food_items") else None,
            "required_quantity": required_quantity,
            "available_quantity": available_quantity,
            "unit": ingredient.get("unit"),
            "enough": available_quantity >= required_quantity,
        }

        if available_quantity >= required_quantity:
            available_ingredients.append(ingredient_result)
        else:
            missing_ingredients.append(ingredient_result)

    return {
        "recipe_id": recipe["id"],
        "title": recipe["title"],
        "available_ingredients": available_ingredients,
        "missing_ingredients": missing_ingredients,
        "can_make_recipe": len(missing_ingredients) == 0,
    }
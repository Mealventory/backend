from core.supabase_client import supabase

def add_recipe_ingredient(recipe_id: int, ingredient_data: dict):
    ingredient_data["recipe_id"] = recipe_id
    response = supabase.table("recipe_ingredients").insert(ingredient_data).execute()
    return response.data

def delete_recipe_ingredient(recipe_id: int, food_item_id: int):
    response = (
        supabase.table("recipe_ingredients")
        .delete()
        .eq("recipe_id", recipe_id)
        .eq("food_item_id", food_item_id)
        .execute()
    )
    return response.data
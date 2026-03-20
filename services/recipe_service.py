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
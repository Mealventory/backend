import os
import json
import httpx
from dotenv import load_dotenv

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openrouter/free")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


async def generate_recipe_suggestions(priority_items, other_items):
    prompt = f"""
You are a meal planning assistant for a food waste reduction app.

Priority ingredients that should be used first:
{json.dumps(priority_items, indent=2)}

Other available ingredients:
{json.dumps(other_items, indent=2)}

Generate 3 realistic and clearly different recipe ideas.

Rules:
- Prioritize the priority ingredients first
- Use as many priority ingredients as possible
- Main ingredients must come from the provided ingredient lists
- Use the ingredient names exactly as provided in the inventory when listing uses_priority_items and uses_other_items
- You may also use common pantry staples and small optional extras only, such as: salt, pepper, oil, water, butter, flour, dried spices, lemon juice, vinegar, and fresh herbs
- These pantry staples may support the recipe, but the main ingredients must still come from the provided inventory
- Do not invent major extra ingredients such as additional proteins, vegetables, dairy products, grains, tortillas, bread, or sauces unless they are listed
- If an ingredient is in the provided inventory, it must appear in uses_priority_items or uses_other_items, not optional_pantry_basics
- Every ingredient mentioned in the steps must appear in one of these fields: uses_priority_items, uses_other_items, or optional_pantry_basics
- Do not suggest side dishes, serving ideas, or additional pairings unless they are already listed in the ingredient fields
- Optional pantry basics and pantry staples must be placed in the optional_pantry_basics field
- Make the 3 recipes clearly different from each other
- Keep recipes simple, practical, and realistic for a student or home cook
- Return valid JSON only

Return this exact structure:
{{
  "recipes": [
    {{
      "title": "string",
      "uses_priority_items": ["string"],
      "uses_other_items": ["string"],
      "optional_pantry_basics": ["string"],
      "prep_time_minutes": 0,
      "cook_time_minutes": 0,
      "difficulty": "Easy",
      "steps": ["string"],
      "waste_reduction_reason": "string"
    }}
  ]
}}
"""

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "You generate practical, realistic recipes using the user's listed ingredients. Prioritize ingredients expiring soon. Common pantry staples and minor extras are allowed, but the recipe must still be primarily based on the provided inventory. If an ingredient is in inventory, it must not be placed in optional_pantry_basics. Every ingredient mentioned in the instructions must appear in the recipe fields. Any pantry staples used must be listed under optional_pantry_basics."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "response_format": {
            "type": "json_object"
        }
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(OPENROUTER_URL, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

    content = data["choices"][0]["message"]["content"]
    return json.loads(content)
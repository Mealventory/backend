"""Deterministic demo identities and food/recipe fixtures; no login credentials."""
from uuid import UUID, uuid5
from pydantic import BaseModel

NAMESPACE = UUID('98ce418f-024e-4eaa-890f-19fda37459e2')


def fixture_id(name):
    return str(uuid5(NAMESPACE, name))


class DemoUser(BaseModel):
    id: UUID
    name: str


USERS = [DemoUser(id=fixture_id(f'user:{i}'), name=name)
         for i, name in enumerate(('Alex Demo', 'Sam Demo', 'Taylor Demo', 'Jordan Student'))]
HOUSEHOLDS = [('Demo Family', 'DEMO01'), ('Single Student', 'STUD02')]
# Name, category, unit, zone. Expiry dates below are UI fixtures, not food safety guidance.
FOODS = [
    ('Milk', 'Dairy', 'litres', 'fridge'), ('Yogurt', 'Dairy', 'cups', 'fridge'),
    ('Carrots', 'Vegetables', 'kg', 'fridge'), ('Spinach', 'Vegetables', 'bags', 'fridge'),
    ('Frozen peas', 'Vegetables', 'bags', 'freezer'), ('Frozen berries', 'Fruit', 'bags', 'freezer'),
    ('Rice', 'Grains', 'kg', 'pantry'), ('Pasta', 'Grains', 'packs', 'pantry'),
    ('Chickpeas', 'Legumes', 'cans', 'pantry'), ('Tomatoes', 'Vegetables', 'cans', 'pantry'),
    ('Cumin', 'Spices', 'jars', 'spicerack'), ('Paprika', 'Spices', 'jars', 'spicerack'),
    ('Oats', 'Grains', 'kg', 'pantry'), ('Bananas', 'Fruit', 'units', 'pantry'),
    ('Eggs', 'Protein', 'units', 'fridge'), ('Cheese', 'Dairy', 'packs', 'fridge'),
]
RECIPES = [
    ('Berry yogurt bowl', [1, 5, 12]), ('Banana oats', [0, 12, 13]),
    ('Tomato pasta', [7, 9, 15]), ('Chickpea rice', [6, 8, 10]),
    ('Spinach eggs', [3, 14, 15]), ('Pea rice', [4, 6, 11]),
    ('Carrot chickpea salad', [2, 8, 10]), ('Spinach pasta', [3, 7, 15]),
    ('Tomato chickpea stew', [8, 9, 11]), ('Cheesy rice', [6, 15, 4]),
]

"""Regression checks for the active v1 service behavior."""
import asyncio
from datetime import date
import os
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

# No test contacts the user's configured database, authentication or AI services.
os.environ.update(
    DATABASE_URL="sqlite://",
    AI_SERVICE_URL="http://127.0.0.1:8001",
    FIREBASE_PROJECT_ID="mealventory-local-check",
)

from fastapi.testclient import TestClient
from app.services.expiry_service import calculate_expiry, predict_expiry_date


class MergeRegressionTests(unittest.TestCase):
    def test_versioned_app_starts_and_exposes_food_route(self):
        from app.main import app
        with TestClient(app) as client:
            self.assertEqual(client.get('/').status_code, 200)
            schema = client.get('/openapi.json').json()
            self.assertIn('/api/v1/food/predict-expiry/{food_id}', schema['paths'])

    def test_zero_day_expiry_is_preserved(self):
        self.assertEqual(calculate_expiry(date(2026, 9, 11), 0), date(2026, 9, 11))
        self.assertIsNone(calculate_expiry(date(2026, 9, 11), None))

    def test_prediction_accepts_iso_purchase_date(self):
        food = SimpleNamespace(purchase_date='2026-09-11', avg_shelf_life_days=7)
        self.assertEqual(predict_expiry_date(food, 20, 50), date(2026, 9, 18))

    def test_recipe_service_falls_back_when_ai_is_unavailable(self):
        from app.services import recipe_service
        fallback = AsyncMock(return_value={'recipes': []})
        with patch.object(recipe_service.httpx, 'AsyncClient', side_effect=OSError('offline')):
            with patch.object(recipe_service, 'generate_recipe_suggestions', fallback):
                result = asyncio.run(recipe_service.get_recipes_for_inventory(['Milk', 'Eggs', 'Rice']))
        self.assertEqual(result, {'recipes': []})
        fallback.assert_awaited_once()
        self.assertEqual(fallback.call_args.args[1], [{'name': 'Rice'}])


if __name__ == '__main__':
    unittest.main()

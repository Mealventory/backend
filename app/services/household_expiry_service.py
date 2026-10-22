from datetime import date, timedelta
import httpx
from sqlalchemy import text
from fastapi import HTTPException
from app.core.config import settings
from app.services.household_inventory_service import get_item
from app.schemas.expiry_prediction import ExpiryPredictionOutput
from app.services.shelf_life_catalogue import catalogue_prediction

async def predict_expiry(db, household_id, request):
    # This endpoint only suggests a date. Saving remains an explicit inventory operation.
    if request.item_id:
        item = get_item(db, household_id, request.item_id)
        if item['status'] != 'active':
            raise HTTPException(400, 'Only active items can request predictions')
    def unavailable(message):
        return ExpiryPredictionOutput(source='unavailable', explanation=message, purchase_date=request.purchase_date)
    guidance = catalogue_prediction(request)
    # Keep curated matches and condition prompts authoritative. When the local
    # guide knows the food but has no freezer entry, try FoodKeeper's freezer
    # quality window before returning its narrower fridge-only message.
    if guidance is not None and (
            guidance.source == 'catalogue' or guidance.food_state_options
            or request.storage_zone != 'freezer'):
        return guidance
    # USDA FoodKeeper is an offline dataset served by the AI service. It uses
    # the request's purchase date and the selected storage zone; unlike the
    # experimental model it also supports freezer quality windows.
    if request.storage_zone in ('pantry', 'fridge', 'freezer'):
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(
                    f"{settings.AI_SERVICE_URL.rstrip('/')}/foodkeeper/predict-expiry",
                    json={'name': request.name, 'storage_zone': request.storage_zone,
                          'purchase_date': request.purchase_date.isoformat()})
                response.raise_for_status()
                foodkeeper = response.json()
                if (foodkeeper.get('predicted_expiry_date')
                        and foodkeeper.get('matched_food')
                        and foodkeeper.get('source_url')):
                    predicted = date.fromisoformat(foodkeeper['predicted_expiry_date'])
                    days = int(foodkeeper['shelf_life_days'])
                    if predicted == request.purchase_date + timedelta(days=days) and days > 0:
                        return ExpiryPredictionOutput(
                            predicted_expiry_date=predicted, source='catalogue',
                            purchase_date=request.purchase_date, baseline_source='catalog',
                            matched_food=foodkeeper['matched_food'],
                            source_name=foodkeeper.get('source_name', 'USDA FoodKeeper (FSIS)'),
                            source_url=foodkeeper['source_url'], shelf_life_days=days,
                            explanation=(
                                f"USDA FoodKeeper estimate: {days} days from the purchase date "
                                f"for {foodkeeper['matched_food']} stored in the {request.storage_zone}. "
                                "This is storage guidance, not a guarantee of safety. Follow the "
                                "package date and discard food that shows signs of spoilage."
                            ),
                        )
        except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError):
            # FoodKeeper is an optional source; keep the established fallback path available.
            pass
    if guidance is not None:
        return guidance
    # The experimental model has no freezer support; USDA estimates above may.
    if request.storage_zone in ('freezer', 'spicerack'):
        return unavailable('Estimates are not available for this storage zone. Use the package date or enter a date manually.')
    baseline = request.avg_shelf_life_days
    source = 'provided'
    if baseline is None:
        # Only inspect food metadata already belonging to this household.
        values = db.execute(text("""SELECT DISTINCT f.avg_shelf_life_days FROM foods f
            JOIN inventory_items i ON i.food_id=f.id
            WHERE i.household_id=:household AND lower(f.name)=lower(:name)
            AND f.avg_shelf_life_days BETWEEN 5 AND 30"""),
            {'household': str(household_id), 'name': request.name}).scalars().all()
        if len(values) != 1:
            return unavailable('This food is not in our storage guide yet. Try a simple food name, use the package date, or enter a known shelf life for an experimental estimate.')
        baseline = values[0]
        source = 'catalog'
    temperature, humidity = (4.0, 50.0) if request.storage_zone == 'fridge' else (20.0, 50.0)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(f"{settings.AI_SERVICE_URL.rstrip('/')}/scan/predict-expiry", params={
                'name': request.name, 'avg_shelf_life_days': baseline,
                'purchase_date': request.purchase_date.isoformat(), 'temperature': temperature, 'humidity': humidity})
            response.raise_for_status()
            predicted = date.fromisoformat(response.json()['predicted_expiry_date'])
            days = (predicted-request.purchase_date).days
            if not 0 <= days <= 30:
                raise ValueError('Prediction outside model range')
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return unavailable('Prediction is unavailable right now. Your date has not changed; retry or enter it manually.')
    return ExpiryPredictionOutput(predicted_expiry_date=predicted, source='model',
        purchase_date=request.purchase_date, temperature=temperature, humidity=humidity, baseline_source=source,
        explanation=f'Experimental estimate using the known shelf life and {request.storage_zone} conditions. Check the label and freshness; this is not a safety guarantee.')

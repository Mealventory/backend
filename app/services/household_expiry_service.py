from datetime import date
import httpx
from sqlalchemy import text
from fastapi import HTTPException
from app.core.config import settings
from app.services.household_inventory_service import get_item
from app.schemas.expiry_prediction import ExpiryPredictionOutput

async def predict_expiry(db, household_id, request):
    # This endpoint only suggests a date. Saving remains an explicit inventory operation.
    if request.item_id:
        item = get_item(db, household_id, request.item_id)
        if item['status'] != 'active':
            raise HTTPException(400, 'Only active items can request predictions')
    def unavailable(message):
        return ExpiryPredictionOutput(source='unavailable', explanation=message, purchase_date=request.purchase_date)
    # The checked-in model was trained at 4–25 C; do not extrapolate to frozen food.
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
            return unavailable('No known shelf life for this food. Enter its usual shelf life if known, or keep a manual expiry date.')
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

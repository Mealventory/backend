"""Reviewed storage guidance. No fuzzy matching or model-generated durations."""
from datetime import timedelta
from functools import lru_cache
import json
from pathlib import Path
import re
import unicodedata

from app.schemas.expiry_prediction import ExpiryPredictionOutput


def normalize_name(name):
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFKC', name).casefold()).strip()


@lru_cache(maxsize=1)
def catalogue():
    data = json.loads((Path(__file__).resolve().parents[1] / 'data/shelf_life_catalogue.json').read_text())
    return data['entries']


def catalogue_prediction(request):
    """None means unknown food; unavailable means known but unsupported conditions."""
    matches = [entry for entry in catalogue() if normalize_name(request.name) in entry['aliases']]
    if not matches:
        return None
    def result(message, **kwargs):
        return ExpiryPredictionOutput(source='unavailable', explanation=message,
                                      purchase_date=request.purchase_date, **kwargs)
    zoned = [entry for entry in matches if entry['zone'] == request.storage_zone]
    if not zoned:
        zones = ', '.join(sorted({entry['zone'] for entry in matches}))
        return result(f'We only have guidance for this food in the {zones}. Choose its actual storage location or enter a date manually.')
    options = list(dict.fromkeys(entry['state'] for entry in zoned))
    selected = [entry for entry in zoned if entry['state'] == request.food_state]
    if len(selected) != 1:
        return result('Choose the food condition below, check the start date, then request the estimate again.', food_state_options=options)
    entry = selected[0]
    metadata = dict(source_name=entry['source_name'], source_url=entry['source_url'],
                    matched_food=entry['name'], food_state_options=options)
    if entry['days'] is None:
        return result(entry['note'], **metadata)
    predicted = request.purchase_date + timedelta(days=entry['days'])
    explanation = (f"Storage guide estimate: {entry['days']} days from the {entry['anchor']} date "
                   f"for {entry['state'].replace('_', ' ')} {entry['name']} in the {entry['zone']}. "
                   + ('Assumes continuous refrigeration at 4°C or below. ' if entry['zone'] == 'fridge' else '')
                   + entry['note'] + ' Follow an earlier package date. This estimate cannot establish whether food is safe to eat.')
    return ExpiryPredictionOutput(source='catalogue', predicted_expiry_date=predicted,
        purchase_date=request.purchase_date, baseline_source='catalog', explanation=explanation,
        shelf_life_days=entry['days'], **metadata)

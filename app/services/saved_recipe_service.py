import hashlib
import json
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from app.models.saved_recipe import SavedRecipe


def recipe_key(recipe):
    identity = [recipe.name.lower(), sorted(name.lower() for name in recipe.uses)]
    return hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()


def list_saved(db, household_id):
    rows = db.query(SavedRecipe).filter_by(household_id=str(household_id)).order_by(
        SavedRecipe.created_at.desc(), SavedRecipe.recipe_key).all()
    return [row.snapshot for row in rows]


def save(db, household_id, recipe):
    snapshot = recipe.model_dump(exclude_none=True)
    key = recipe_key(recipe)
    # Stable IDs keep recipe detail links distinct from transient generated results.
    snapshot['id'] = 'saved-' + key
    insert = sqlite_insert if db.bind.dialect.name == 'sqlite' else pg_insert
    statement = insert(SavedRecipe).values(household_id=str(household_id), recipe_key=key, snapshot=snapshot)
    statement = statement.on_conflict_do_nothing(index_elements=['household_id', 'recipe_key'])
    try:
        db.execute(statement)
        db.commit()
    except Exception:
        db.rollback()
        raise


def remove(db, household_id, recipe):
    try:
        db.query(SavedRecipe).filter_by(household_id=str(household_id), recipe_key=recipe_key(recipe)).delete()
        db.commit()
    except Exception:
        db.rollback()
        raise

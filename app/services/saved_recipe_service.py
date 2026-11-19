import hashlib
import json
from sqlalchemy.exc import IntegrityError
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


def update(db, household_id, previous, recipe):
    household = str(household_id)
    previous_key = recipe_key(previous)
    updated_key = recipe_key(recipe)
    snapshot = recipe.model_dump(exclude_none=True)
    snapshot['id'] = 'saved-' + updated_key

    try:
        row = db.query(SavedRecipe).filter_by(
            household_id=household, recipe_key=previous_key
        ).with_for_update().one_or_none()
        if row is None:
            # A retry after a successful update is safe and does not create another row.
            already_updated = db.query(SavedRecipe).filter_by(
                household_id=household, recipe_key=updated_key
            ).one_or_none()
            db.rollback()
            return 'updated' if already_updated and already_updated.snapshot == snapshot else 'not_found'

        if updated_key != previous_key:
            collision = db.query(SavedRecipe).filter_by(
                household_id=household, recipe_key=updated_key
            ).one_or_none()
            if collision is not None:
                db.rollback()
                return 'duplicate'

        row.recipe_key = updated_key
        row.snapshot = snapshot
        db.commit()
        return 'updated'
    except IntegrityError:
        db.rollback()
        return 'duplicate'
    except Exception:
        db.rollback()
        raise

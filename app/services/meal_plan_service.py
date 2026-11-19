"""Atomic shared meal plan operations. All mutations lock the household row.

A slot's revision is incremented on every assignment, move or removal.
Deleted slots remain as tombstones, so stale editors cannot recreate a slot
after another member removed or replaced it.
"""
from __future__ import annotations

import hashlib
import json

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.household import Household
from app.models.meal_plan import MealPlanImport, MealPlanSlot
from app.schemas.meal_plan import MealPlanImportRequest


def _key(day, slot):
    return f"{day.isoformat()}:{slot}"


def _query_slot(db, household, day, slot):
    return db.get(MealPlanSlot, (str(household), day, slot))


def _version(row):
    return row.revision if row is not None else 0


def _conflict():
    raise HTTPException(status_code=409, detail="This meal plan changed on another device. Refresh and review before trying again.")


def _lock(db, household):
    # PostgreSQL row lock serializes writes, even when the target slot is absent.
    # The membership dependency has already validated the caller's household.
    row = db.query(Household).filter(Household.id == str(household)).with_for_update().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Household not found")


def _write(db, household, day, slot, snapshot):
    row = _query_slot(db, household, day, slot)
    if row is None:
        row = MealPlanSlot(
            household_id=str(household), plan_date=day, slot=slot,
            recipe_snapshot=snapshot, revision=1,
        )
        db.add(row)
    else:
        row.recipe_snapshot = snapshot
        row.revision += 1


def _state(db, household, user):
    rows = db.query(MealPlanSlot).filter_by(household_id=str(household)).order_by(
        MealPlanSlot.plan_date, MealPlanSlot.slot,
    ).all()
    imported = db.query(MealPlanImport).filter_by(
        household_id=str(household), user_id=str(user), import_key="local-v1",
    ).first() is not None
    return {
        "meals": [
            {"date": row.plan_date, "slot": row.slot,
             "recipe": row.recipe_snapshot, "revision": row.revision}
            for row in rows if row.recipe_snapshot is not None
        ],
        "slot_versions": {_key(row.plan_date, row.slot): row.revision for row in rows},
        "imported_local_plan": imported,
    }


def list_plan(db: Session, household, user):
    return _state(db, household, user)


def assign(db: Session, household, user, body):
    try:
        _lock(db, household)
        row = _query_slot(db, household, body.date, body.slot)
        if _version(row) != body.expected_revision:
            _conflict()
        _write(db, household, body.date, body.slot, body.recipe.model_dump(mode="json", exclude_none=True))
        db.commit()
        return _state(db, household, user)
    except Exception:
        db.rollback()
        raise


def remove(db: Session, household, user, body):
    try:
        _lock(db, household)
        row = _query_slot(db, household, body.date, body.slot)
        if _version(row) != body.expected_revision:
            _conflict()
        if row is None or row.recipe_snapshot is None:
            raise HTTPException(status_code=404, detail="Meal slot is empty")
        _write(db, household, body.date, body.slot, None)
        db.commit()
        return _state(db, household, user)
    except Exception:
        db.rollback()
        raise


def move(db: Session, household, user, body):
    if body.source_date == body.target_date and body.source_slot == body.target_slot:
        raise HTTPException(status_code=422, detail="Choose a different destination slot")
    try:
        _lock(db, household)
        source = _query_slot(db, household, body.source_date, body.source_slot)
        target = _query_slot(db, household, body.target_date, body.target_slot)
        if _version(source) != body.source_revision or _version(target) != body.target_revision:
            _conflict()
        if source is None or source.recipe_snapshot is None:
            raise HTTPException(status_code=404, detail="Source meal no longer exists")
        source_snapshot = source.recipe_snapshot
        target_snapshot = target.recipe_snapshot if target else None
        _write(db, household, body.source_date, body.source_slot, target_snapshot)
        _write(db, household, body.target_date, body.target_slot, source_snapshot)
        db.commit()
        return _state(db, household, user)
    except Exception:
        db.rollback()
        raise


def preview_import(db: Session, household, user, body: MealPlanImportRequest):
    seen = set()
    candidates = []
    for meal in body.meals:
        key = _key(meal.date, meal.slot)
        if key in seen:
            raise HTTPException(status_code=422, detail="Duplicate import slot")
        seen.add(key)
        row = _query_slot(db, household, meal.date, meal.slot)
        candidates.append({
            "date": meal.date, "slot": meal.slot,
            "status": "occupied" if row and row.recipe_snapshot is not None else "available",
            "revision": _version(row),
        })
    imported = db.query(MealPlanImport).filter_by(
        household_id=str(household), user_id=str(user), import_key=body.import_key,
    ).first() is not None
    return {"candidates": candidates, "imported_local_plan": imported}


def import_local(db: Session, household, user, body: MealPlanImportRequest):
    # Stable digest makes replay safe, including after an ambiguous network timeout.
    fingerprint = [
        meal.model_dump(mode="json", exclude_none=True)
        for meal in sorted(body.meals, key=lambda value: (value.date, value.slot))
    ]
    digest = hashlib.sha256(json.dumps(
        fingerprint, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")).hexdigest()
    try:
        _lock(db, household)
        receipt = db.get(MealPlanImport, (str(household), str(user), body.import_key))
        if receipt:
            if receipt.request_hash != digest:
                _conflict()
            db.commit()
            return _state(db, household, user)
        keys = set()
        for meal in body.meals:
            key = _key(meal.date, meal.slot)
            if key in keys:
                raise HTTPException(status_code=422, detail="Duplicate import slot")
            keys.add(key)
            row = _query_slot(db, household, meal.date, meal.slot)
            # Never overwrite a shared meal, even when the caller has an old preview.
            if _version(row) != meal.expected_revision or (row and row.recipe_snapshot is not None):
                _conflict()
        for meal in body.meals:
            _write(db, household, meal.date, meal.slot, meal.recipe.model_dump(mode="json", exclude_none=True))
        db.add(MealPlanImport(
            household_id=str(household), user_id=str(user),
            import_key=body.import_key, request_hash=digest,
        ))
        db.commit()
        return _state(db, household, user)
    except Exception:
        db.rollback()
        raise

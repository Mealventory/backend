"""Household-scoped frequently shopped stores."""
from uuid import uuid4

from sqlalchemy import text
from app.core.auth_errors import AuthProblem

COLUMNS = (
    "id, household_id, name, website_url, sort_order, created_at, updated_at"
)


def _url(value):
    return str(value) if value is not None else None


def list_stores(db, household_id):
    return db.execute(
        text(
            f"SELECT {COLUMNS} FROM household_stores "
            "WHERE household_id=:home ORDER BY sort_order, created_at, id"
        ),
        {"home": str(household_id)},
    ).mappings().all()


def add_store(db, household_id, store):
    try:
        next_order = db.execute(
            text(
                "SELECT COALESCE(MAX(sort_order), -1) + 1 "
                "FROM household_stores WHERE household_id=:home"
            ),
            {"home": str(household_id)},
        ).scalar_one()
        row = db.execute(
            text(
                f"""INSERT INTO household_stores
                (id, household_id, name, website_url, sort_order)
                VALUES (:id, :home, :name, :website_url, :sort_order)
                RETURNING {COLUMNS}"""
            ),
            {
                "id": str(uuid4()),
                "home": str(household_id),
                "name": store.name,
                "website_url": _url(store.website_url),
                "sort_order": next_order,
            },
        ).mappings().one()
        result = dict(row)
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


def update_store(db, household_id, store_id, update):
    fields = update.model_dump(exclude_unset=True)
    assignments = []
    params = {"home": str(household_id), "id": str(store_id)}
    if "name" in fields:
        assignments.append("name=:name")
        params["name"] = fields["name"]
    if "website_url" in fields:
        assignments.append("website_url=:website_url")
        params["website_url"] = _url(fields["website_url"])

    try:
        row = db.execute(
            text(
                f"UPDATE household_stores SET {', '.join(assignments)}, "
                f"updated_at=CURRENT_TIMESTAMP "
                f"WHERE household_id=:home AND id=:id RETURNING {COLUMNS}"
            ),
            params,
        ).mappings().first()
        if row is None:
            raise AuthProblem(404, "Store not found in this household")
        result = dict(row)
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


def delete_store(db, household_id, store_id):
    try:
        row = db.execute(
            text(
                "DELETE FROM household_stores "
                "WHERE household_id=:home AND id=:id RETURNING id"
            ),
            {"home": str(household_id), "id": str(store_id)},
        ).first()
        if row is None:
            raise AuthProblem(404, "Store not found in this household")
        db.commit()
    except Exception:
        db.rollback()
        raise


def reorder_stores(db, household_id, store_ids):
    requested = [str(value) for value in store_ids]
    current = [
        str(row[0])
        for row in db.execute(
            text(
                "SELECT id FROM household_stores "
                "WHERE household_id=:home ORDER BY sort_order, created_at, id"
            ),
            {"home": str(household_id)},
        ).all()
    ]
    if len(requested) != len(current) or set(requested) != set(current):
        raise AuthProblem(
            409,
            "Store order is stale; refresh the store list and try again",
        )

    try:
        for sort_order, store_id in enumerate(requested):
            db.execute(
                text(
                    "UPDATE household_stores SET sort_order=:sort_order, "
                    "updated_at=CURRENT_TIMESTAMP "
                    "WHERE household_id=:home AND id=:id"
                ),
                {
                    "sort_order": sort_order,
                    "home": str(household_id),
                    "id": store_id,
                },
            )
        db.commit()
        return list_stores(db, household_id)
    except Exception:
        db.rollback()
        raise

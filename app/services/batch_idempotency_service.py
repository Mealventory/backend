"""Durable idempotency for confirmed scan-review batch saves.

The insert claim and the inventory additions commit in *one* transaction.
PostgreSQL's unique primary key makes concurrent callers of the same key wait:
after the winner commits, losers replay its saved response; if it rolls back,
one waiting caller can take over the claim.
"""
import hashlib
import json

from pydantic import TypeAdapter
from sqlalchemy import text

from app.core.auth_errors import AuthProblem
from app.schemas.household_inventory import ItemOut
from app.services import household_inventory_service as inventory

_RESPONSE_ADAPTER = TypeAdapter(list[ItemOut])


def save_reviewed_batch_once(db, household_id, items, actor, idempotency_key):
    """Return the first batch's original response for same-key retries.

    The caller must have already verified the authenticated user and household.
    Keys are scoped to both; changing the payload under a key is a conflict.
    """
    payload = [item.model_dump(mode="json") for item in items]
    request_hash = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    params = {
        "household_id": str(household_id),
        "user_id": str(actor.id),
        "key": idempotency_key,
        "request_hash": request_hash,
    }
    try:
        # No pending row survives a failed batch. A unique-key conflict waits
        # on an in-flight insert and therefore works across API processes.
        claim = db.execute(text("""
            INSERT INTO batch_idempotency_records
                (household_id, user_id, idempotency_key, request_hash, response_json)
            VALUES (:household_id, :user_id, :key, :request_hash, '[]')
            ON CONFLICT (household_id, user_id, idempotency_key) DO NOTHING
        """), params)
        if claim.rowcount == 0:
            original = db.execute(text("""
                SELECT request_hash, response_json FROM batch_idempotency_records
                WHERE household_id=:household_id AND user_id=:user_id
                  AND idempotency_key=:key
            """), params).mappings().one()
            if original["request_hash"] != request_hash:
                raise AuthProblem(409, "Idempotency key was already used with different items")
            response = json.loads(original["response_json"])
            db.rollback()  # Read-only replay must not leave a transaction open.
            return response

        rows = inventory.add_batch(db, household_id, items, actor=actor, commit=False)
        # Serializing via the route's response model preserves UUID, Decimal,
        # date, and nullable fields exactly for a later replay.
        response_json = _RESPONSE_ADAPTER.dump_json(rows).decode("utf-8")
        db.execute(text("""
            UPDATE batch_idempotency_records SET response_json=:response_json
            WHERE household_id=:household_id AND user_id=:user_id
              AND idempotency_key=:key
        """), {**params, "response_json": response_json})
        db.commit()
        return json.loads(response_json)
    except Exception:
        db.rollback()
        raise

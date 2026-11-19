"""Safe, household-scoped CSV pantry portability operations."""
import base64
import csv
import hashlib
import hmac
import io
import json
import time
from decimal import Decimal
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import text

from app.core.auth_errors import AuthProblem
from app.core.config import settings
from app.schemas.household_inventory import ItemCreate
from app.services import activity_service
from app.services import household_inventory_service as inventory

CSV_COLUMNS = ("schema_version", "food_name", "category", "quantity", "unit", "storage_zone", "expiry_date")
SCHEMA_VERSION = "1"
MAX_FILE_BYTES = 1_048_576
MAX_ROWS = 100
TOKEN_TTL_SECONDS = 30 * 60
_DANGEROUS_CSV_START = "=+-@\t\r\n"


def _csv_text(value):
    value = "" if value is None else str(value)
    if value.startswith("'"):
        value = "'" + value
    significant = value.lstrip(" \t\r\n")
    if significant and significant[0] in _DANGEROUS_CSV_START:
        value = "'" + value
    return value


def _unescape_csv_text(value):
    if value.startswith("''"):
        return value[1:]
    significant = value[1:].lstrip(" \t\r\n") if value.startswith("'") else ""
    if significant and significant[0] in _DANGEROUS_CSV_START:
        return value[1:]
    return value


def export_csv(db, household_id):
    rows = db.execute(text("""
        SELECT f.name AS food_name, COALESCE(f.category, 'Pantry') AS category,
               i.quantity, i.unit, s.zone AS storage_zone, i.expiry_date
        FROM inventory_items i
        JOIN foods f ON f.id=i.food_id
        LEFT JOIN storage_locations s ON s.id=i.storage_location_id AND s.household_id=i.household_id
        WHERE i.household_id=:household_id AND i.status='active'
        ORDER BY i.created_at, i.id
    """), {"household_id": str(household_id)}).mappings().all()
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\r\n")
    writer.writerow(CSV_COLUMNS)
    for row in rows:
        expiry = row["expiry_date"]
        writer.writerow([
            SCHEMA_VERSION, _csv_text(row["food_name"]), _csv_text(row["category"]),
            str(row["quantity"]), _csv_text(row["unit"]), row["storage_zone"] or "pantry",
            expiry.isoformat() if hasattr(expiry, "isoformat") else (str(expiry) if expiry else ""),
        ])
    return output.getvalue()


def _parse_csv(raw):
    if len(raw) > MAX_FILE_BYTES:
        raise AuthProblem(413, "CSV file exceeds the 1 MiB limit")
    try:
        decoded = raw.decode("utf-8-sig", errors="strict")
    except UnicodeDecodeError:
        raise AuthProblem(400, "CSV file must be UTF-8") from None
    reader = csv.reader(io.StringIO(decoded, newline=""), strict=True)
    try:
        header = next(reader, None)
        if tuple(header or ()) != CSV_COLUMNS:
            raise AuthProblem(400, "CSV columns or schema version do not match the documented format")
        entries, errors = [], []
        data_rows = 0
        for cells in reader:
            row_number = reader.line_num
            if not cells or (len(cells) == 1 and not cells[0].strip()):
                continue
            data_rows += 1
            if data_rows > MAX_ROWS:
                raise AuthProblem(413, f"CSV may contain at most {MAX_ROWS} data rows")
            if len(cells) != len(CSV_COLUMNS):
                errors.append({"row": row_number, "errors": [f"Expected {len(CSV_COLUMNS)} columns; found {len(cells)}"]})
                continue
            values = dict(zip(CSV_COLUMNS, cells))
            if values["schema_version"] != SCHEMA_VERSION:
                errors.append({"row": row_number, "errors": ["Unsupported schema_version"]})
                continue
            values["food_name"] = _unescape_csv_text(values["food_name"])
            values["category"] = _unescape_csv_text(values["category"])
            values["unit"] = _unescape_csv_text(values["unit"])
            try:
                payload = ItemCreate(
                    name=values["food_name"], category=values["category"],
                    quantity=values["quantity"], unit=values["unit"],
                    storage_zone=values["storage_zone"],
                    expiry_date=values["expiry_date"] or None,
                )
                entries.append({"row": row_number, "item": payload})
            except (ValidationError, ValueError, AuthProblem) as exc:
                if isinstance(exc, ValidationError):
                    details = exc.errors()
                elif isinstance(exc, AuthProblem):
                    details = [{"msg": exc.detail}]
                else:
                    details = [{"msg": str(exc)}]
                errors.append({"row": row_number, "errors": [str(e.get("msg", "Invalid value")) for e in details]})
        return entries, errors
    except csv.Error as exc:
        raise AuthProblem(400, f"Malformed CSV near line {reader.line_num}: {exc}") from None


def _item_key(item):
    return (item.name.strip().casefold(), item.category.strip().casefold(),
            item.unit.strip().casefold(), item.storage_zone, item.expiry_date)


def _existing_items(db, household_id):
    rows = db.execute(text("""
        SELECT i.id, i.version, f.name, COALESCE(f.category, 'Pantry') AS category,
               i.quantity, i.unit, i.expiry_date, COALESCE(s.zone, 'pantry') AS storage_zone
        FROM inventory_items i JOIN foods f ON f.id=i.food_id
        LEFT JOIN storage_locations s ON s.id=i.storage_location_id AND s.household_id=i.household_id
        WHERE i.household_id=:household_id AND i.status='active'
        ORDER BY i.created_at, i.id
    """), {"household_id": str(household_id)}).mappings().all()
    return [dict(row) for row in rows]


def _token(payload):
    secret = settings.PANTRY_IMPORT_SIGNING_SECRET or settings.SUPABASE_JWT_SECRET
    if secret is None:
        raise AuthProblem(503, "Import preview is unavailable until the signing secret is configured")
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    encoded = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    signature = hmac.new(secret.get_secret_value().encode(), encoded.encode(), hashlib.sha256).digest()
    return encoded + "." + base64.urlsafe_b64encode(signature).decode().rstrip("=")


def _verify_token(token, household_id, user_id):
    try:
        encoded, signature = token.split(".", 1)
        secret = settings.PANTRY_IMPORT_SIGNING_SECRET or settings.SUPABASE_JWT_SECRET
        if secret is None:
            raise ValueError
        expected = hmac.new(secret.get_secret_value().encode(), encoded.encode(), hashlib.sha256).digest()
        supplied = base64.urlsafe_b64decode(signature + "=" * (-len(signature) % 4))
        if not hmac.compare_digest(expected, supplied):
            raise ValueError
        payload = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
        if payload["household_id"] != str(household_id) or payload["user_id"] != str(user_id):
            raise AuthProblem(403, "Import preview belongs to a different user or household")
        return payload
    except AuthProblem:
        raise
    except Exception:
        raise AuthProblem(400, "Invalid import operation ID") from None


def preview_csv(db, household_id, user_id, raw):
    entries, errors = _parse_csv(raw)
    existing = _existing_items(db, household_id)
    exact = {}
    similar = {}
    for row in existing:
        key = _item_key(ItemCreate(name=row["name"], category=row["category"], quantity=row["quantity"],
                                   unit=row["unit"], expiry_date=row["expiry_date"], storage_zone=row["storage_zone"]))
        exact.setdefault(key, row)
        similar.setdefault(key[:4], row)
    preview_rows, plan = [], []
    imported_exact, imported_similar = {}, {}
    for entry in entries:
        row_no, item = entry["row"], entry["item"]
        key = _item_key(item)
        match = exact.get(key)
        conflict = similar.get(key[:4]) if not match else None
        prior_exact = imported_exact.get(key)
        prior_similar = imported_similar.get(key[:4])
        if match:
            status, target, duplicate_of_row = "exact_duplicate", match, None
        elif prior_exact:
            status, target, duplicate_of_row = "duplicate_in_file", None, prior_exact
        elif conflict:
            status, target, duplicate_of_row = "conflict", conflict, None
        elif prior_similar:
            status, target, duplicate_of_row = "conflict_in_file", None, prior_similar
        else:
            status, target, duplicate_of_row = "ready", None, None
        preview_rows.append({
            "row": row_no, "status": status,
            "suggested_action": "skip" if match or prior_exact else "add",
            "existing_item_id": str(target["id"]) if target else None,
            "existing_version": target["version"] if target else None,
            "duplicate_of_row": duplicate_of_row,
            "item": {"name": item.name, "category": item.category, "quantity": str(item.quantity),
                     "unit": item.unit, "storage_zone": item.storage_zone,
                     "expiry_date": item.expiry_date.isoformat() if item.expiry_date else None},
        })
        plan.append({"row": row_no, "item": item.model_dump(mode="json"),
                     "existing_item_id": str(target["id"]) if target else None,
                     "existing_version": target["version"] if target else None,
                     "status": status, "duplicate_of_row": duplicate_of_row})
        imported_exact.setdefault(key, row_no)
        imported_similar.setdefault(key[:4], row_no)
    now = int(time.time())
    op_id = str(uuid4())
    signed_plan = _token({"operation_id": op_id, "household_id": str(household_id), "user_id": str(user_id),
                          "expires_at": now + TOKEN_TTL_SECONDS, "rows": plan, "errors": errors})
    return {"operation_id": signed_plan, "operation_id_label": op_id,
            "expires_at": now + TOKEN_TTL_SECONDS, "rows": preview_rows, "errors": errors}


def _merge_existing(db, household_id, actor, row, item):
    lock = " FOR UPDATE" if db.get_bind().dialect.name == "postgresql" else ""
    current = db.execute(text("""SELECT quantity, initial_quantity, version, name FROM inventory_items i
        JOIN foods f ON f.id=i.food_id
        WHERE i.id=:id AND i.household_id=:household_id AND i.status='active'""" + lock),
        {"id": row["existing_item_id"], "household_id": str(household_id)}).mappings().first()
    if current is None:
        raise AuthProblem(409, f"Row {row['row']} duplicate changed after preview; preview again")
    if current["version"] != row["existing_version"]:
        raise AuthProblem(409, f"Row {row['row']} duplicate changed after preview; preview again")
    qty = Decimal(str(current["quantity"])) + Decimal(str(item.quantity))
    initial = (Decimal(str(current["initial_quantity"])) + Decimal(str(item.quantity))
               if current["initial_quantity"] is not None else qty)
    db.execute(text("""UPDATE inventory_items SET quantity=:quantity, initial_quantity=:initial,
        version=version+1 WHERE id=:id AND household_id=:household_id"""),
        {"quantity": str(qty), "initial": str(initial), "id": row["existing_item_id"],
         "household_id": str(household_id)})
    activity_service.record_event(db, household_id, actor, "added", current["name"],
                                  entity_id=row["existing_item_id"])
    return inventory.get_item(db, household_id, row["existing_item_id"])


def confirm_import(db, household_id, user, operation_id, idempotency_key, choices):
    payload = _verify_token(operation_id, household_id, user.id)
    choices = sorted(choices, key=lambda choice: choice["row"])
    request_doc = {"operation": payload["operation_id"], "choices": choices}
    request_hash = hashlib.sha256(json.dumps(request_doc, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    params = {"household_id": str(household_id), "user_id": str(user.id),
              "key": idempotency_key, "request_hash": request_hash}
    try:
        claim = db.execute(text("""INSERT INTO pantry_import_idempotency_records
            (household_id,user_id,idempotency_key,request_hash,response_json)
            VALUES (:household_id,:user_id,:key,:request_hash,'{}')
            ON CONFLICT (household_id,user_id,idempotency_key) DO NOTHING"""), params)
        if claim.rowcount == 0:
            original = db.execute(text("""SELECT request_hash,response_json FROM pantry_import_idempotency_records
                WHERE household_id=:household_id AND user_id=:user_id AND idempotency_key=:key"""), params).mappings().one()
            if original["request_hash"] != request_hash:
                raise AuthProblem(409, "Idempotency key was already used with a different import")
            response = json.loads(original["response_json"])
            db.rollback()
            return response
        if payload["expires_at"] < int(time.time()):
            raise AuthProblem(410, "Import preview has expired; upload the CSV again")
        choice_map = {choice["row"]: choice["action"] for choice in choices}
        plan = payload["rows"]
        valid_rows = {row["row"] for row in plan}
        if len(choice_map) != len(choices) or set(choice_map) != valid_rows:
            raise AuthProblem(400, "Provide exactly one reviewed choice for every valid CSV row")
        if any(action not in ("skip", "add", "merge") for action in choice_map.values()):
            raise AuthProblem(400, "Choices must be skip, add or merge")
        results = []
        for row in plan:
            action = choice_map[row["row"]]
            item = ItemCreate.model_validate(row["item"])
            if action == "skip":
                results.append({"row": row["row"], "action": "skip"})
            elif action == "merge":
                if not row["existing_item_id"]:
                    raise AuthProblem(400, f"Row {row['row']} has no existing item to merge into")
                saved = _merge_existing(db, household_id, user.id, row, item)
                results.append({"row": row["row"], "action": "merge", "item": saved})
            else:
                saved = inventory.add_item(db, household_id, item, commit=False, actor=user,
                                           stack_existing=False)
                results.append({"row": row["row"], "action": "add", "item": saved})
        response = {"operation_id": payload["operation_id"], "results": results,
                    "errors": payload["errors"]}
        response_json = json.dumps(response, default=str, ensure_ascii=False)
        db.execute(text("""UPDATE pantry_import_idempotency_records SET response_json=:response
            WHERE household_id=:household_id AND user_id=:user_id AND idempotency_key=:key"""),
            {**params, "response": response_json})
        db.commit()
        return json.loads(response_json)
    except Exception:
        db.rollback()
        raise

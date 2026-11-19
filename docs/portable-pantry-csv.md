# Portable pantry CSV format, version 1

The household inventory API exports active items at `GET /api/v1/items/export.csv`.
Upload that file as multipart field `file` to `POST /api/v1/items/import/preview`.
The preview does not write inventory or operation records. Its signed `operation_id`
is bound to the authenticated user and selected household and expires after 30 minutes.

The UTF-8 CSV header and column order are stable:

```csv
schema_version,food_name,category,quantity,unit,storage_zone,expiry_date
```

`schema_version` is `1`. Dates use ISO `YYYY-MM-DD` or an empty value. Quantities
are positive decimal values with at most three fractional digits. Storage zones are
`pantry`, `fridge`, `freezer`, and `spicerack`. Category is included so exports can
round-trip inventory without changing its classification. Image references, storage
paths, credentials, and member details are never exported or accepted from CSV.
Deployments using asymmetric Supabase JWT verification must also configure
`PANTRY_IMPORT_SIGNING_SECRET`; HS256 deployments use their configured JWT secret
when no dedicated secret is set.

Files must be UTF-8 and no larger than 1 MiB, with at most 100 data rows. The preview
reports invalid rows and identifies exact duplicates and likely conflicts. Confirm at
`POST /api/v1/items/import/confirm` with the returned `operation_id`, a choice for
each valid row (`skip`, `add`, or `merge`), and a unique `Idempotency-Key` header.
`add` creates a separate lot. `merge` adds its quantity to the existing item shown in
the preview, retaining that item's expiry date. A repeated confirmation with the same
key replays the original result; reusing that key for different reviewed choices is
rejected.

Export text that begins with spreadsheet formula characters is escaped. The importer
reverses that escaping for Mealventory exports.

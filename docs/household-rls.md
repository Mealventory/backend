# Household row-level security (#41)

Apply `scripts/init_db.sql`, then `scripts/enable_rls.sql` once, using a trusted postgres/BYPASSRLS administrator on the new schema. This is not an upgrade for the legacy per-user database. No live database is changed by tests. Existing policies cause the transaction to fail rather than combine permissive policies silently. Re-running also fails transactionally.

Supabase must supply `auth.uid()`, `authenticated` and `anon`. Keep `mealventory_private` out of exposed API schemas. The membership helper is SECURITY DEFINER with an empty search_path, qualified object references, restricted execution and a caller identity check. Its trusted owner bypasses membership RLS to avoid recursion. Do not change that owner to an ordinary client role.

Authenticated members can read their household and membership roster; update the household name; and create/read/update/delete household storage, inventory, recipes, ingredients and shopping entries. Both old and new rows are checked. Foods are an authenticated read-only shared catalogue. Device tokens are private to their user. Anonymous access is revoked. No client TRUNCATE or schema creation privileges are granted.

Household creation/deletion, invites, membership changes and role changes require trusted server operations that validate the caller. There is intentionally no client self-enrolment or role escalation policy. Implementing that workflow is separate work. The server must create a household and its first owner membership transactionally.

Database owners, superusers and service roles with BYPASSRLS bypass policies by design. Existing backend Firebase auth and direct privileged DATABASE_URL connections do not automatically acquire Supabase user identity. This migration protects Supabase authenticated-role access; it does not replace backend authorization or migrate backend models. Never expose service-role credentials to clients.

Validation: `RUN_POSTGRES_TESTS=1 python -m pytest tests/ -q`. Docker PostgreSQL 16 tests emulate only Supabase roles and auth.uid() from transaction-local JWT settings, then SET ROLE authenticated. No .env or live DATABASE_URL is used. A staging Supabase rollout still needs real JWT/API verification.

Reference: https://supabase.com/docs/guides/database/postgres/row-level-security

# Supabase authentication and household context (#42)

Configure SUPABASE_URL and SUPABASE_JWT_ALGORITHM (HS256, ES256 or RS256). For HS256 supply SUPABASE_JWT_SECRET: this is the signing secret, not the anon/service key or database password. For asymmetric keys leave the secret unset: the verifier fetches public keys only from the configured project's /auth/v1/.well-known/jwks.json endpoint, with caching and a five-second timeout. The configured algorithm is enforced, with no token-driven fallback.

JWT signature, issuer, authenticated audience, expiry, issued-at time, UUID subject, and authenticated role are validated. Missing/malformed/expired tokens return 401 application/problem+json and WWW-Authenticate: Bearer. Missing configuration or a JWKS connection failure returns 503. Revoked sessions may remain valid until token expiry: this is offline JWT verification, not online session introspection.

Send Authorization: Bearer <Supabase access_token> to protected routes. Inventory, recipes and scans (including the development sample route) additionally require X-Household-ID: <UUID>. Missing or malformed household headers return 400; absent membership returns 403 without distinguishing nonexistent households. Membership comes from household_members; a row means active membership because #29 defines no status column. Request state and the route argument contain the verified household ID. No client-supplied role is trusted.

GET /api/v1/users/me returns verified identity without querying the legacy users table. POST /api/v1/users/register remains an optional legacy profile sync, needed by old per-user inventory foreign keys; it is not a Supabase signup endpoint. Sign up/sign in using Supabase Auth. The new #29 schema has no public.users table, so this legacy sync endpoint is only usable with the old schema. Profile email may be null for phone-based identities.

This issue does not convert inventory/scan/recipe storage to the new UUID household schema (#44). Their existing services still scope by user ID after the household guard. Do not claim shared-household inventory or deploy the old ORM against the new schema until that conversion is complete. Database credentials with BYPASSRLS still bypass #41 policies: this code checks membership explicitly and does not SET ROLE or impersonate a Supabase database session.

Apply the #29 schema in an isolated/staging database before testing household membership. Provision membership through trusted code; no self-enrolment endpoint is added here (#43). No real .env, credentials or production database are changed. Firebase startup, verifier and direct package dependency have been removed. Other Google packages remain for existing integrations.

Contract changes: all data endpoints now require a bearer token; household routes require the header; auth errors use RFC 7807; /users/me no longer needs registration; sample persistence cannot choose another user's ID. Existing paths and success inventory shapes remain. The docs/openapi.json and contract snapshot record these deliberate changes.

Run python -m pytest tests/ -q for offline signed-token and API tests. RUN_POSTGRES_TESTS=1 also runs isolated PostgreSQL 16 schema tests. Production verification requires real Supabase tokens and the team's schema rollout.

References: https://supabase.com/docs/guides/auth/jwts and https://pyjwt.readthedocs.io/en/stable/usage.html

# Household management (#43)

This branch builds on #42 (Supabase authentication). Review its diff against feat/supabase-auth-42 until that PR merges, then target main. No live database is changed. The endpoints use the households and household_members tables from #29 without schema changes.

All endpoints require Authorization: Bearer <Supabase user access token>. Creation, joining and GET /me do not require X-Household-ID, so a new user can bootstrap a household. Member endpoints take the household UUID in the path and verify membership for that exact household; a header cannot override it.

| Method | Path | Request / result |
| --- | --- | --- |
| POST | /api/v1/households | {"name":"Smith Family"}; 201 with id, name, invite_code, role=owner |
| POST | /api/v1/households/join | {"invite_code":"ABC123"}; 200 with household and caller role |
| GET | /api/v1/households/me | List all households the caller belongs to; empty list for new users |
| GET | /api/v1/households/{household_id}/members | Member UUIDs and roles; members only |
| PATCH | /api/v1/households/{household_id}/members/{user_id} | {"role":"admin"}; owners only |
| DELETE | /api/v1/households/{household_id}/members/{user_id} | Remove/leave; 204 |

Names are trimmed, nonblank, and at most 120 characters. Invite input is trimmed and uppercased; codes use six uppercase ASCII letters/digits generated with secrets.choice. The unique database constraint resolves collisions, with up to five attempts. Creation and first owner insertion commit together. Joining is idempotent and never downgrades an existing role. Users may belong to multiple households, as supported by #29.

Owners may change any member role and remove members. Admins may remove regular members but cannot change roles or remove other admins/owners. Any user can leave themselves, except the last owner. Multiple owners are allowed; promote another member to owner before the last owner leaves or demotes themselves. created_by remains historical creator metadata, not the authorization source.

PostgreSQL household row locks serialize joins, role changes and removals before checking membership and owner counts. Use the default READ COMMITTED isolation level and a fresh request-scoped session. All trusted membership writers must follow the same locking protocol. The concurrency tests run on PostgreSQL 16, not SQLite.

This is trusted server code: DATABASE_URL must have permission to create households and manage membership, including bypassing the #41 client RLS policies. Client authenticated roles remain unable to write memberships directly. Keep these database credentials server-only. The service obtains the caller UUID solely from the verified token, never from the request body.

Invites are reusable household credentials, visible to members, with no expiry/rotation in this issue. A removed user who still has a valid code can join again. Add gateway rate limiting to the join endpoint before public deployment; distributed rate limiting and invite rotation are separate work. These endpoints do not migrate legacy inventory storage (#44) or create Supabase Auth users.

Validation: python -m pytest tests/ -q. Add RUN_POSTGRES_TESTS=1 for real PostgreSQL schema/concurrency checks. The household integration tests launch postgres:16 with a random password and an ephemeral loopback-only port, load init_db.sql, and remove the container afterward. They never use the configured DATABASE_URL.

Locking reference: https://www.postgresql.org/docs/16/applevel-consistency.html

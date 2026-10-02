"""Opt-in PostgreSQL test for the additive household stores migration."""
from pathlib import Path

from tests.test_init_db_postgres import database, pytestmark

MIGRATION = (
    Path(__file__).resolve().parents[1] / "scripts" / "add_household_stores.sql"
).read_text()


def test_household_stores_migration_bootstraps_missing_rls_helper(database):
    database(
        """
        DO $$ BEGIN
          IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='authenticated') THEN
            CREATE ROLE authenticated NOLOGIN;
          END IF;
          IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='anon') THEN
            CREATE ROLE anon NOLOGIN;
          END IF;
        END $$;

        CREATE SCHEMA auth;
        CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS $$
          SELECT nullif(current_setting('request.jwt.claim.sub', true), '')::uuid
        $$;

        CREATE TABLE public.households (
          id uuid PRIMARY KEY DEFAULT gen_random_uuid()
        );
        CREATE TABLE public.household_members (
          household_id uuid NOT NULL REFERENCES public.households(id) ON DELETE CASCADE,
          user_id uuid NOT NULL,
          PRIMARY KEY (household_id, user_id)
        );

        CREATE FUNCTION public.update_updated_at_column()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          NEW.updated_at = now();
          RETURN NEW;
        END
        $$;
        """
    )

    database(MIGRATION)
    assert database(
        "SELECT count(*) FROM pg_namespace WHERE nspname='mealventory_private'"
    ).stdout.strip() == "1"
    assert database(
        "SELECT count(*) FROM pg_proc "
        "WHERE pronamespace='mealventory_private'::regnamespace "
        "AND proname='is_household_member'"
    ).stdout.strip() == "1"
    assert database(
        "SELECT count(*) FROM pg_tables "
        "WHERE schemaname='public' AND tablename='household_stores'"
    ).stdout.strip() == "1"
    assert database(
        "SELECT count(*) FROM pg_policies "
        "WHERE schemaname='public' AND tablename='household_stores' "
        "AND policyname='household_stores_member'"
    ).stdout.strip() == "1"

    # The migration is safe to rerun after a successful application.
    database(MIGRATION)
    assert database(
        "SELECT count(*) FROM pg_policies "
        "WHERE schemaname='public' AND tablename='household_stores' "
        "AND policyname='household_stores_member'"
    ).stdout.strip() == "1"

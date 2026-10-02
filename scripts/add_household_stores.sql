-- Add frequently shopped stores to an existing Mealventory PostgreSQL database.
-- Run as the same trusted database owner used for the initial schema/RLS setup.
BEGIN;

CREATE TABLE IF NOT EXISTS public.household_stores (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    household_id uuid NOT NULL REFERENCES public.households(id) ON DELETE CASCADE,
    name text NOT NULL CHECK (btrim(name) <> ''),
    website_url text CHECK (website_url IS NULL OR website_url ~* '^https?://'),
    sort_order integer NOT NULL DEFAULT 0 CHECK (sort_order >= 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_household_stores_order
    ON public.household_stores (household_id, sort_order, created_at, id);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'household_stores_updated_at'
          AND tgrelid = 'public.household_stores'::regclass
          AND NOT tgisinternal
    ) THEN
        CREATE TRIGGER household_stores_updated_at
            BEFORE UPDATE ON public.household_stores
            FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
    END IF;
END
$$;

ALTER TABLE public.household_stores ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.household_stores FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.household_stores TO authenticated;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'household_stores'
          AND policyname = 'household_stores_member'
    ) THEN
        CREATE POLICY household_stores_member
            ON public.household_stores
            TO authenticated
            USING (
                mealventory_private.is_household_member(
                    (SELECT auth.uid()), household_id
                )
            )
            WITH CHECK (
                mealventory_private.is_household_member(
                    (SELECT auth.uid()), household_id
                )
            );
    END IF;
END
$$;

COMMIT;

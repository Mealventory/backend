-- Additive migration; preserves existing recipe and inventory tables.
BEGIN;
CREATE TABLE IF NOT EXISTS public.household_saved_recipes (
    household_id uuid NOT NULL REFERENCES public.households(id) ON DELETE CASCADE,
    recipe_key varchar(64) NOT NULL,
    snapshot json NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (household_id, recipe_key)
);
-- Access is through the authenticated backend, not direct client table access.
ALTER TABLE public.household_saved_recipes ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.household_saved_recipes FROM anon, authenticated;
COMMIT;

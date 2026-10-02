-- Apply once before deploying POST /api/v1/recipes/complete (safe to rerun).
BEGIN;
CREATE TABLE IF NOT EXISTS public.household_recipe_completions (
    household_id uuid NOT NULL REFERENCES public.households(id) ON DELETE CASCADE,
    completion_id varchar(100) NOT NULL,
    fingerprint varchar(64) NOT NULL,
    result text,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (household_id, completion_id)
);
ALTER TABLE public.household_recipe_completions ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.household_recipe_completions FROM anon, authenticated;
COMMIT;

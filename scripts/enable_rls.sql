-- Issue #41. Apply after init_db.sql as postgres (or a trusted BYPASSRLS owner).
-- Requires Supabase auth.uid(), authenticated and anon roles. One-time migration.
BEGIN;
CREATE SCHEMA mealventory_private;
REVOKE ALL ON SCHEMA mealventory_private FROM PUBLIC, anon, authenticated;
GRANT USAGE ON SCHEMA mealventory_private TO authenticated;

-- Reject an executor that cannot bypass membership RLS; otherwise this would recurse.
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname=current_user AND (rolsuper OR rolbypassrls)) THEN
        RAISE EXCEPTION 'Run RLS migration as a trusted BYPASSRLS administrator';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='public'
        AND tablename IN ('households','household_members','storage_locations','inventory_items',
                          'recipes','recipe_ingredients','shopping_list_items','foods','device_push_tokens')) THEN
        RAISE EXCEPTION 'Existing policies require explicit review before this migration';
    END IF;
END $$;

CREATE FUNCTION mealventory_private.is_household_member(_user_id uuid, _household_id uuid)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = ''
AS $$
    SELECT _user_id = (SELECT auth.uid()) AND EXISTS (
        SELECT 1 FROM public.household_members
        WHERE user_id = _user_id AND household_id = _household_id
    );
$$;
REVOKE ALL ON FUNCTION mealventory_private.is_household_member(uuid, uuid) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION mealventory_private.is_household_member(uuid, uuid) TO authenticated;

ALTER TABLE public.households ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.households FROM PUBLIC, anon, authenticated;

ALTER TABLE public.household_members ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.household_members FROM PUBLIC, anon, authenticated;

ALTER TABLE public.storage_locations ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.storage_locations FROM PUBLIC, anon, authenticated;

ALTER TABLE public.inventory_items ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.inventory_items FROM PUBLIC, anon, authenticated;

ALTER TABLE public.recipes ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.recipes FROM PUBLIC, anon, authenticated;

ALTER TABLE public.recipe_ingredients ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.recipe_ingredients FROM PUBLIC, anon, authenticated;

ALTER TABLE public.shopping_list_items ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.shopping_list_items FROM PUBLIC, anon, authenticated;

ALTER TABLE public.foods ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.foods FROM PUBLIC, anon, authenticated;

ALTER TABLE public.device_push_tokens ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.device_push_tokens FROM PUBLIC, anon, authenticated;
GRANT SELECT ON public.households TO authenticated;
CREATE POLICY households_read ON public.households FOR SELECT TO authenticated USING (mealventory_private.is_household_member((SELECT auth.uid()), id));
GRANT UPDATE (name) ON public.households TO authenticated;
CREATE POLICY households_update ON public.households FOR UPDATE TO authenticated USING (mealventory_private.is_household_member((SELECT auth.uid()), id)) WITH CHECK (mealventory_private.is_household_member((SELECT auth.uid()), id));
GRANT SELECT ON public.household_members TO authenticated;
CREATE POLICY household_members_read ON public.household_members FOR SELECT TO authenticated USING (mealventory_private.is_household_member((SELECT auth.uid()), household_id));
GRANT SELECT, INSERT, UPDATE, DELETE ON public.storage_locations TO authenticated;
CREATE POLICY storage_locations_member ON public.storage_locations TO authenticated USING (mealventory_private.is_household_member((SELECT auth.uid()), household_id)) WITH CHECK (mealventory_private.is_household_member((SELECT auth.uid()), household_id));
GRANT SELECT, INSERT, UPDATE, DELETE ON public.inventory_items TO authenticated;
CREATE POLICY inventory_items_member ON public.inventory_items TO authenticated USING (mealventory_private.is_household_member((SELECT auth.uid()), household_id)) WITH CHECK (mealventory_private.is_household_member((SELECT auth.uid()), household_id));
GRANT SELECT, INSERT, UPDATE, DELETE ON public.recipes TO authenticated;
CREATE POLICY recipes_member ON public.recipes TO authenticated USING (mealventory_private.is_household_member((SELECT auth.uid()), household_id)) WITH CHECK (mealventory_private.is_household_member((SELECT auth.uid()), household_id));
GRANT SELECT, INSERT, UPDATE, DELETE ON public.recipe_ingredients TO authenticated;
CREATE POLICY recipe_ingredients_member ON public.recipe_ingredients TO authenticated USING (mealventory_private.is_household_member((SELECT auth.uid()), household_id)) WITH CHECK (mealventory_private.is_household_member((SELECT auth.uid()), household_id));
GRANT SELECT, INSERT, UPDATE, DELETE ON public.shopping_list_items TO authenticated;
CREATE POLICY shopping_list_items_member ON public.shopping_list_items TO authenticated USING (mealventory_private.is_household_member((SELECT auth.uid()), household_id)) WITH CHECK (mealventory_private.is_household_member((SELECT auth.uid()), household_id));
GRANT SELECT ON public.foods TO authenticated;
CREATE POLICY foods_read ON public.foods FOR SELECT TO authenticated USING ((SELECT auth.uid()) IS NOT NULL);
GRANT SELECT, INSERT, UPDATE, DELETE ON public.device_push_tokens TO authenticated;
CREATE POLICY device_owner ON public.device_push_tokens TO authenticated USING (user_id = (SELECT auth.uid())) WITH CHECK (user_id = (SELECT auth.uid()));

COMMIT;

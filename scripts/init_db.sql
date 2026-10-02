-- Issue #29: initial household schema for a CLEAN PostgreSQL 16 database.
-- Intentionally fails on existing objects; never drops or overwrites live data.
-- User UUIDs are external identity references. Supabase auth FKs and RLS are separate work.
BEGIN;
SET LOCAL search_path = public, pg_catalog;

CREATE TYPE public.member_role AS ENUM ('owner', 'admin', 'member');
CREATE TYPE public.storage_zone AS ENUM ('pantry', 'fridge', 'freezer', 'spicerack');
CREATE TYPE public.item_status AS ENUM ('active', 'consumed', 'discarded');

CREATE OR REPLACE FUNCTION public.update_updated_at_column()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $$
BEGIN
    NEW.updated_at := clock_timestamp();
    RETURN NEW;
END;
$$;

CREATE TABLE public.households (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL CHECK (btrim(name) <> ''),
    created_by uuid NOT NULL,
    invite_code varchar(6) UNIQUE CHECK (invite_code ~ '^[A-Z0-9]{6}$'),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE public.household_members (
    household_id uuid NOT NULL REFERENCES public.households(id) ON DELETE CASCADE,
    user_id uuid NOT NULL,
    role public.member_role NOT NULL DEFAULT 'member',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (household_id, user_id)
);
CREATE INDEX idx_household_members ON public.household_members (user_id, household_id);

CREATE TABLE public.storage_locations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    household_id uuid NOT NULL REFERENCES public.households(id) ON DELETE CASCADE,
    name text NOT NULL CHECK (btrim(name) <> ''),
    zone public.storage_zone NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (household_id, id),
    UNIQUE (household_id, name)
);

-- Global food reference catalogue. Inventory quantities and dates belong to households.
CREATE TABLE public.foods (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL CHECK (btrim(name) <> ''),
    category text,
    barcode text UNIQUE CHECK (barcode IS NULL OR btrim(barcode) <> ''),
    default_unit text NOT NULL DEFAULT 'units' CHECK (btrim(default_unit) <> ''),
    avg_shelf_life_days integer CHECK (avg_shelf_life_days >= 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE public.inventory_items (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    household_id uuid NOT NULL REFERENCES public.households(id) ON DELETE CASCADE,
    food_id uuid NOT NULL REFERENCES public.foods(id),
    storage_location_id uuid,
    quantity numeric(12,3) NOT NULL DEFAULT 1 CHECK (quantity >= 0 AND quantity <> 'NaN'::numeric),
    unit text NOT NULL DEFAULT 'units' CHECK (btrim(unit) <> ''),
    purchase_date date,
    expiry_date date,
    status public.item_status NOT NULL DEFAULT 'active',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (household_id, storage_location_id)
        REFERENCES public.storage_locations(household_id, id)
);
CREATE INDEX idx_inventory_tenant ON public.inventory_items (household_id, status, expiry_date);
CREATE INDEX idx_inventory_food ON public.inventory_items (food_id);
CREATE INDEX idx_inventory_storage ON public.inventory_items (household_id, storage_location_id);

CREATE TABLE public.recipes (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    household_id uuid NOT NULL REFERENCES public.households(id) ON DELETE CASCADE,
    name text NOT NULL CHECK (btrim(name) <> ''),
    description text,
    instructions text NOT NULL DEFAULT '',
    servings integer NOT NULL DEFAULT 1 CHECK (servings > 0),
    prep_time_minutes integer CHECK (prep_time_minutes >= 0),
    cook_time_minutes integer CHECK (cook_time_minutes >= 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (household_id, id)
);

CREATE TABLE public.recipe_ingredients (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    household_id uuid NOT NULL REFERENCES public.households(id) ON DELETE CASCADE,
    recipe_id uuid NOT NULL,
    food_id uuid NOT NULL REFERENCES public.foods(id),
    quantity numeric(12,3) NOT NULL CHECK (quantity > 0 AND quantity <> 'NaN'::numeric),
    unit text NOT NULL DEFAULT 'units' CHECK (btrim(unit) <> ''),
    optional boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (household_id, recipe_id)
        REFERENCES public.recipes(household_id, id) ON DELETE CASCADE,
    UNIQUE (recipe_id, food_id)
);
CREATE INDEX idx_recipe_ingredients_tenant ON public.recipe_ingredients (household_id, recipe_id);
CREATE INDEX idx_recipe_ingredients_food ON public.recipe_ingredients (food_id);

CREATE TABLE public.shopping_list_items (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    household_id uuid NOT NULL REFERENCES public.households(id) ON DELETE CASCADE,
    food_id uuid REFERENCES public.foods(id),
    name text NOT NULL CHECK (btrim(name) <> ''),
    quantity numeric(12,3) NOT NULL DEFAULT 1 CHECK (quantity > 0 AND quantity <> 'NaN'::numeric),
    unit text NOT NULL DEFAULT 'units' CHECK (btrim(unit) <> ''),
    is_checked boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_shopping_tenant ON public.shopping_list_items (household_id, is_checked);
CREATE INDEX idx_shopping_food ON public.shopping_list_items (food_id);

CREATE TABLE public.household_stores (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    household_id uuid NOT NULL REFERENCES public.households(id) ON DELETE CASCADE,
    name text NOT NULL CHECK (btrim(name) <> ''),
    website_url text CHECK (website_url IS NULL OR website_url ~* '^https?://'),
    sort_order integer NOT NULL DEFAULT 0 CHECK (sort_order >= 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_household_stores_order ON public.household_stores (household_id, sort_order, created_at, id);

-- Device registrations belong to users, who may belong to multiple households.
CREATE TABLE public.device_push_tokens (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL,
    token text NOT NULL UNIQUE CHECK (btrim(token) <> ''),
    platform text NOT NULL CHECK (platform IN ('ios', 'android', 'web')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_device_push_tokens_user ON public.device_push_tokens (user_id);

CREATE TRIGGER households_updated_at BEFORE UPDATE ON public.households
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
CREATE TRIGGER household_members_updated_at BEFORE UPDATE ON public.household_members
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
CREATE TRIGGER storage_locations_updated_at BEFORE UPDATE ON public.storage_locations
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
CREATE TRIGGER foods_updated_at BEFORE UPDATE ON public.foods
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
CREATE TRIGGER inventory_items_updated_at BEFORE UPDATE ON public.inventory_items
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
CREATE TRIGGER recipes_updated_at BEFORE UPDATE ON public.recipes
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
CREATE TRIGGER recipe_ingredients_updated_at BEFORE UPDATE ON public.recipe_ingredients
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
CREATE TRIGGER shopping_list_items_updated_at BEFORE UPDATE ON public.shopping_list_items
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
CREATE TRIGGER household_stores_updated_at BEFORE UPDATE ON public.household_stores
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
CREATE TRIGGER device_push_tokens_updated_at BEFORE UPDATE ON public.device_push_tokens
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
COMMIT;

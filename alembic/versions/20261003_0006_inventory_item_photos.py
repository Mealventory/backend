"""Add pantry item image references and private Supabase Storage policies.

Revision ID: 20261003_0006
Revises: 20261002_0005
Create Date: 2026-10-03
"""
from alembic import op
import sqlalchemy as sa


revision = "20261003_0006"
down_revision = "20261002_0005"
branch_labels = None
depends_on = None


_STORAGE_POLICY_SQL = r"""
DO $do$
BEGIN
    IF to_regclass('storage.buckets') IS NOT NULL
       AND to_regclass('storage.objects') IS NOT NULL THEN

        INSERT INTO storage.buckets (
            id, name, public, file_size_limit, allowed_mime_types
        )
        VALUES (
            'pantry-item-images',
            'pantry-item-images',
            false,
            5242880,
            ARRAY['image/jpeg', 'image/png', 'image/webp']::text[]
        )
        ON CONFLICT (id) DO UPDATE
        SET public = EXCLUDED.public,
            file_size_limit = EXCLUDED.file_size_limit,
            allowed_mime_types = EXCLUDED.allowed_mime_types;

        EXECUTE 'DROP POLICY IF EXISTS mealventory_item_images_select ON storage.objects';
        EXECUTE 'DROP POLICY IF EXISTS mealventory_item_images_insert ON storage.objects';
        EXECUTE 'DROP POLICY IF EXISTS mealventory_item_images_update ON storage.objects';
        EXECUTE 'DROP POLICY IF EXISTS mealventory_item_images_delete ON storage.objects';

        EXECUTE $policy$
            CREATE POLICY mealventory_item_images_select
            ON storage.objects
            FOR SELECT
            TO authenticated
            USING (
                bucket_id = 'pantry-item-images'
                AND EXISTS (
                    SELECT 1
                    FROM public.household_members hm
                    WHERE hm.household_id::text = split_part(name, '/', 1)
                      AND hm.user_id = auth.uid()
                )
            )
        $policy$;

        EXECUTE $policy$
            CREATE POLICY mealventory_item_images_insert
            ON storage.objects
            FOR INSERT
            TO authenticated
            WITH CHECK (
                bucket_id = 'pantry-item-images'
                AND EXISTS (
                    SELECT 1
                    FROM public.household_members hm
                    WHERE hm.household_id::text = split_part(name, '/', 1)
                      AND hm.user_id = auth.uid()
                )
            )
        $policy$;

        EXECUTE $policy$
            CREATE POLICY mealventory_item_images_update
            ON storage.objects
            FOR UPDATE
            TO authenticated
            USING (
                bucket_id = 'pantry-item-images'
                AND EXISTS (
                    SELECT 1
                    FROM public.household_members hm
                    WHERE hm.household_id::text = split_part(name, '/', 1)
                      AND hm.user_id = auth.uid()
                )
            )
            WITH CHECK (
                bucket_id = 'pantry-item-images'
                AND EXISTS (
                    SELECT 1
                    FROM public.household_members hm
                    WHERE hm.household_id::text = split_part(name, '/', 1)
                      AND hm.user_id = auth.uid()
                )
            )
        $policy$;

        EXECUTE $policy$
            CREATE POLICY mealventory_item_images_delete
            ON storage.objects
            FOR DELETE
            TO authenticated
            USING (
                bucket_id = 'pantry-item-images'
                AND EXISTS (
                    SELECT 1
                    FROM public.household_members hm
                    WHERE hm.household_id::text = split_part(name, '/', 1)
                      AND hm.user_id = auth.uid()
                )
            )
        $policy$;
    END IF;
END
$do$;
"""


_DROP_STORAGE_POLICIES_SQL = r"""
DO $do$
BEGIN
    IF to_regclass('storage.objects') IS NOT NULL THEN
        EXECUTE 'DROP POLICY IF EXISTS mealventory_item_images_select ON storage.objects';
        EXECUTE 'DROP POLICY IF EXISTS mealventory_item_images_insert ON storage.objects';
        EXECUTE 'DROP POLICY IF EXISTS mealventory_item_images_update ON storage.objects';
        EXECUTE 'DROP POLICY IF EXISTS mealventory_item_images_delete ON storage.objects';
    END IF;
END
$do$;
"""


def upgrade() -> None:
    op.add_column(
        "inventory_items",
        sa.Column("image_ref", sa.Text(), nullable=True),
        schema="public",
    )
    op.create_check_constraint(
        "ck_inventory_items_image_ref_length",
        "inventory_items",
        "image_ref IS NULL OR char_length(image_ref) <= 2048",
        schema="public",
    )
    op.execute(_STORAGE_POLICY_SQL)


def downgrade() -> None:
    # Policies are removed, but the bucket itself is deliberately retained so
    # downgrading application schema never destroys uploaded user images.
    op.execute(_DROP_STORAGE_POLICIES_SQL)
    op.drop_constraint(
        "ck_inventory_items_image_ref_length",
        "inventory_items",
        schema="public",
        type_="check",
    )
    op.drop_column("inventory_items", "image_ref", schema="public")

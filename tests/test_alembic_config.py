from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_alembic_uses_explicit_migration_url_and_not_app_settings():
    source = (ROOT / "alembic" / "env.py").read_text()
    assert 'os.getenv("ALEMBIC_DATABASE_URL")' in source
    assert "DATABASE_URL is intentionally ignored" in source
    assert "from app.core.config" not in source


def test_app_startup_does_not_run_migrations():
    source = (ROOT / "app" / "main.py").read_text().lower()
    assert "alembic" not in source
    assert "upgrade head" not in source


def test_baseline_snapshot_contains_current_additive_tables():
    source = (
        ROOT / "alembic" / "sql" / "20261002_0001_current_household_baseline.sql"
    ).read_text()
    assert "CREATE TABLE public.household_stores" in source
    assert "CREATE TABLE public.household_saved_recipes" in source
    assert "CREATE TABLE public.household_recipe_completions" in source


def test_revision_chain_has_reversible_followup():
    baseline = (
        ROOT
        / "alembic"
        / "versions"
        / "20261002_0001_current_household_baseline.py"
    ).read_text()
    followup = (
        ROOT
        / "alembic"
        / "versions"
        / "20261002_0002_recipe_completion_history_index.py"
    ).read_text()

    assert 'revision = "20261002_0001"' in baseline
    assert "down_revision = None" in baseline
    assert 'revision = "20261002_0002"' in followup
    assert 'down_revision = "20261002_0001"' in followup
    assert "def downgrade()" in followup

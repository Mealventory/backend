"""merge waste reason and batch idempotency heads

Revision ID: 69b9c45b9a94
Revises: 20261016_0008, 20261022_0008
Create Date: 2026-11-03 09:58:44.385443
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '69b9c45b9a94'
down_revision: Union[str, Sequence[str], None] = ('20261016_0008', '20261022_0008')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

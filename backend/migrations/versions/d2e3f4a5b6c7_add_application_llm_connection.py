"""add application llm connection

Revision ID: d2e3f4a5b6c7
Revises: c1a2b3c4d5e6
"""

from alembic import op
import sqlalchemy as sa


revision = "d2e3f4a5b6c7"
down_revision = "c1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("applications", sa.Column("llm_connection_id", sa.Integer(), nullable=True))
    op.add_column("applications", sa.Column("llm_config", sa.JSON(), nullable=False, server_default=sa.text("('{}')")))
    op.create_index("ix_applications_llm_connection_id", "applications", ["llm_connection_id"])
    op.create_foreign_key(
        "fk_applications_llm_connection_id_connections",
        "applications",
        "connections",
        ["llm_connection_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_applications_llm_connection_id_connections", "applications", type_="foreignkey")
    op.drop_index("ix_applications_llm_connection_id", table_name="applications")
    op.drop_column("applications", "llm_config")
    op.drop_column("applications", "llm_connection_id")

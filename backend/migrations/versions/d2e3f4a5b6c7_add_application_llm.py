"""add per-application llm configuration

Revision ID: d2e3f4a5b6c7
Revises: c1a2b3c4d5e6
Create Date: 2026-09-16
"""

from alembic import op
import sqlalchemy as sa


revision = "d2e3f4a5b6c7"
down_revision = "c1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "applications",
        sa.Column("llm_connection_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "applications",
        sa.Column("llm_config", sa.JSON(), nullable=True),
    )
    op.execute("UPDATE applications SET llm_config = JSON_OBJECT() WHERE llm_config IS NULL")
    op.alter_column(
        "applications",
        "llm_config",
        existing_type=sa.JSON(),
        nullable=False,
    )
    op.create_index(
        "ix_applications_llm_connection_id",
        "applications",
        ["llm_connection_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_applications_llm_connection_id_connections",
        "applications",
        "connections",
        ["llm_connection_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_applications_llm_connection_id_connections",
        "applications",
        type_="foreignkey",
    )
    op.drop_index("ix_applications_llm_connection_id", table_name="applications")
    op.drop_column("applications", "llm_config")
    op.drop_column("applications", "llm_connection_id")

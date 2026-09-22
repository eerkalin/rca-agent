"""add llm interaction history

Revision ID: g5b6c7d8e9f0
Revises: f4a5b6c7d8e9
Create Date: 2026-09-22
"""

from alembic import op
import sqlalchemy as sa


revision = "g5b6c7d8e9f0"
down_revision = "f4a5b6c7d8e9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "applications",
        sa.Column("llm_history_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "investigations",
        sa.Column("llm_history_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("investigations", sa.Column("llm_provider_type", sa.String(length=64), nullable=True))
    op.add_column("investigations", sa.Column("llm_model", sa.String(length=255), nullable=True))
    op.add_column("investigations", sa.Column("llm_input_tokens", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("investigations", sa.Column("llm_output_tokens", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("investigations", sa.Column("llm_total_tokens", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("investigations", sa.Column("llm_token_usage_available", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_table(
        "llm_interactions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("investigation_id", sa.Integer(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("phase", sa.String(length=64), nullable=False),
        sa.Column("provider_type", sa.String(length=64), nullable=True),
        sa.Column("model", sa.String(length=255), nullable=True),
        sa.Column("request_payload", sa.JSON(), nullable=False),
        sa.Column("response_payload", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("token_usage_available", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["investigation_id"], ["investigations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("investigation_id", "sequence", name="uq_llm_interaction_sequence"),
    )
    op.create_index("ix_llm_interactions_investigation_id", "llm_interactions", ["investigation_id"], unique=False)
    op.create_index("ix_llm_interactions_phase", "llm_interactions", ["phase"], unique=False)
    op.create_index("ix_llm_interactions_created_at", "llm_interactions", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_llm_interactions_created_at", table_name="llm_interactions")
    op.drop_index("ix_llm_interactions_phase", table_name="llm_interactions")
    op.drop_index("ix_llm_interactions_investigation_id", table_name="llm_interactions")
    op.drop_table("llm_interactions")
    op.drop_column("investigations", "llm_token_usage_available")
    op.drop_column("investigations", "llm_total_tokens")
    op.drop_column("investigations", "llm_output_tokens")
    op.drop_column("investigations", "llm_input_tokens")
    op.drop_column("investigations", "llm_model")
    op.drop_column("investigations", "llm_provider_type")
    op.drop_column("investigations", "llm_history_enabled")
    op.drop_column("applications", "llm_history_enabled")

"""add application context

Revision ID: c1a2b3c4d5e6
Revises: aa9846a88aa0
Create Date: 2026-09-16
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "aa9846a88aa0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "applications",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("investigation_strategy", sa.String(length=50), nullable=False, server_default="agentic"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index("ix_applications_slug", "applications", ["slug"], unique=True)

    op.create_table(
        "connections",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("provider_type", sa.String(length=100), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("credentials_ciphertext", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_connections_provider_type", "connections", ["provider_type"], unique=False)

    op.create_table(
        "application_tools",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("application_id", sa.Integer(), nullable=False),
        sa.Column("connection_id", sa.Integer(), nullable=True),
        sa.Column("tool_type", sa.String(length=100), nullable=False),
        sa.Column("provider_type", sa.String(length=100), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["connection_id"], ["connections.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("application_id", "tool_type", "provider_type", "connection_id", name="uq_application_tool_binding"),
    )
    op.create_index("ix_application_tools_application_id", "application_tools", ["application_id"], unique=False)
    op.create_index("ix_application_tools_connection_id", "application_tools", ["connection_id"], unique=False)
    op.create_index("ix_application_tools_tool_type", "application_tools", ["tool_type"], unique=False)

    op.create_table(
        "application_dependencies",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("application_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("dependency_type", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_application_dependencies_application_id", "application_dependencies", ["application_id"], unique=False)
    op.create_index("ix_application_dependencies_dependency_type", "application_dependencies", ["dependency_type"], unique=False)

    op.create_table(
        "dependency_tools",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("dependency_id", sa.Integer(), nullable=False),
        sa.Column("connection_id", sa.Integer(), nullable=True),
        sa.Column("tool_type", sa.String(length=100), nullable=False),
        sa.Column("provider_type", sa.String(length=100), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(["dependency_id"], ["application_dependencies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["connection_id"], ["connections.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_dependency_tools_dependency_id", "dependency_tools", ["dependency_id"], unique=False)
    op.create_index("ix_dependency_tools_connection_id", "dependency_tools", ["connection_id"], unique=False)
    op.create_index("ix_dependency_tools_tool_type", "dependency_tools", ["tool_type"], unique=False)

    op.add_column("alerts", sa.Column("application_id", sa.Integer(), nullable=True))
    op.create_index("ix_alerts_application_id", "alerts", ["application_id"], unique=False)
    op.create_foreign_key("fk_alerts_application_id", "alerts", "applications", ["application_id"], ["id"])

    op.add_column("investigations", sa.Column("application_id", sa.Integer(), nullable=True))
    op.add_column("investigations", sa.Column("error", sa.Text(), nullable=True))
    op.add_column("investigations", sa.Column("started_at", sa.DateTime(), nullable=True))
    op.add_column("investigations", sa.Column("finished_at", sa.DateTime(), nullable=True))
    op.create_index("ix_investigations_application_id", "investigations", ["application_id"], unique=False)
    op.create_foreign_key(
        "fk_investigations_application_id",
        "investigations",
        "applications",
        ["application_id"],
        ["id"],
    )
    op.alter_column("investigations", "scope", existing_type=sa.JSON(), nullable=True)
    op.alter_column("investigations", "evidence", existing_type=sa.JSON(), nullable=True)
    op.alter_column("investigations", "rca_result", existing_type=sa.JSON(), nullable=True)


def downgrade() -> None:
    op.alter_column("investigations", "rca_result", existing_type=sa.JSON(), nullable=False)
    op.alter_column("investigations", "evidence", existing_type=sa.JSON(), nullable=False)
    op.alter_column("investigations", "scope", existing_type=sa.JSON(), nullable=False)
    op.drop_constraint("fk_investigations_application_id", "investigations", type_="foreignkey")
    op.drop_index("ix_investigations_application_id", table_name="investigations")
    op.drop_column("investigations", "finished_at")
    op.drop_column("investigations", "started_at")
    op.drop_column("investigations", "error")
    op.drop_column("investigations", "application_id")

    op.drop_constraint("fk_alerts_application_id", "alerts", type_="foreignkey")
    op.drop_index("ix_alerts_application_id", table_name="alerts")
    op.drop_column("alerts", "application_id")

    op.drop_table("dependency_tools")
    op.drop_table("application_dependencies")
    op.drop_table("application_tools")
    op.drop_table("connections")
    op.drop_index("ix_applications_slug", table_name="applications")
    op.drop_table("applications")

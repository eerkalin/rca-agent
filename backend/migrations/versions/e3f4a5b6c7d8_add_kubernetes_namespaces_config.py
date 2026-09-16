"""add kubernetes namespaces config compatibility

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
"""

import json

from alembic import op
import sqlalchemy as sa


revision = "e3f4a5b6c7d8"
down_revision = "d2e3f4a5b6c7"
branch_labels = None
depends_on = None


def _as_dict(value):
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        return json.loads(value or "{}")
    return dict(value)


def upgrade() -> None:
    """Expand legacy `namespace` into `namespaces` without removing legacy data.

    Keeping the original `namespace` key makes the data readable by the previous
    application version during a rollback. New code reads `namespaces` first and
    falls back to `namespace`.
    """
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT id, config FROM application_tools "
            "WHERE provider_type = 'kubernetes' AND tool_type = 'kubernetes'"
        )
    ).mappings()

    for row in rows:
        config = _as_dict(row["config"])
        legacy_namespace = config.get("namespace")
        namespaces = config.get("namespaces")
        if namespaces:
            continue
        if legacy_namespace:
            config["namespaces"] = [legacy_namespace]
            bind.execute(
                sa.text("UPDATE application_tools SET config = :config WHERE id = :id"),
                {"config": json.dumps(config), "id": row["id"]},
            )


def downgrade() -> None:
    """Remove only the new key; the legacy key was intentionally retained."""
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT id, config FROM application_tools "
            "WHERE provider_type = 'kubernetes' AND tool_type = 'kubernetes'"
        )
    ).mappings()

    for row in rows:
        config = _as_dict(row["config"])
        if "namespaces" not in config:
            continue
        namespaces = config.pop("namespaces") or []
        if not config.get("namespace") and namespaces:
            config["namespace"] = namespaces[0]
        bind.execute(
            sa.text("UPDATE application_tools SET config = :config WHERE id = :id"),
            {"config": json.dumps(config), "id": row["id"]},
        )

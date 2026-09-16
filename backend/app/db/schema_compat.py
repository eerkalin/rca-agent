from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy.engine import Engine


BACKEND_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"


def _script_directory() -> ScriptDirectory:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    return ScriptDirectory.from_config(config)


def expected_head_revisions() -> set[str]:
    """Return all Alembic heads shipped with this application version."""
    return set(_script_directory().get_heads())


def current_database_revisions(engine: Engine) -> set[str]:
    """Return Alembic revisions recorded in the connected database.

    An empty set means the database has not been migrated yet or the
    ``alembic_version`` table does not exist.
    """
    with engine.connect() as connection:
        context = MigrationContext.configure(connection)
        heads = context.get_current_heads()
    return set(heads)


def schema_status(engine: Engine) -> dict:
    current = current_database_revisions(engine)
    expected = expected_head_revisions()
    return {
        "current_revisions": sorted(current),
        "expected_revisions": sorted(expected),
        "up_to_date": bool(current) and current == expected,
    }


def assert_schema_current(engine: Engine) -> None:
    """Fail fast when backend code and database schema are incompatible.

    Kubernetes/Compose deployments run ``alembic upgrade head`` before the API
    starts. This guard also protects direct/standalone starts from accidentally
    running newer code against an older schema.
    """
    status = schema_status(engine)
    if status["up_to_date"]:
        return
    raise RuntimeError(
        "Database schema is not up to date. "
        f"current_revisions={status['current_revisions']} "
        f"expected_revisions={status['expected_revisions']}. "
        "Run 'alembic upgrade head' with the same application version before starting RCA Agent."
    )

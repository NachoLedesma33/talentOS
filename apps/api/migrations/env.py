from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

# Importar entidades registra sus tablas en Base.metadata antes de migrar/comparar.
import app.audit.models  # noqa: F401
import app.candidates.models  # noqa: F401
import app.identity.models  # noqa: F401
import app.jobs.models  # noqa: F401
from app.core.config import get_settings
from app.db.base import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    """URL desde settings tipados; nunca desde literal en alembic.ini."""
    return str(get_settings().DATABASE_URL)


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(_database_url())
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

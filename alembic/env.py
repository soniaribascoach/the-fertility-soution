import sys
import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# Add project root to sys.path so imports work
sys.path.insert(0, os.getcwd())

# Import Base and all models so Alembic knows about the tables
from app.db.database import Base
from app.models import conversation  # noqa: F401 — registers model with Base
from app.models import event  # noqa: F401
from app.models import config  # noqa: F401

# Pull DB URL from settings, stripping +asyncpg for Alembic's sync connection
from config import settings

# this is the Alembic Config object
config = context.config

# Override sqlalchemy.url with the value from our settings (sync driver)
config.set_main_option("sqlalchemy.url", settings.database_url.replace("+asyncpg", ""))

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

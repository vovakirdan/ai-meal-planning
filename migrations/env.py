from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig
from pathlib import Path

from aimealplanner.core.config import _DEFAULT_DATABASE_URL
from aimealplanner.infrastructure.db import models  # noqa: F401
from aimealplanner.infrastructure.db.base import Base
from alembic import context
from dotenv import load_dotenv
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine, async_engine_from_config

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _project_root() -> Path:
    if config.config_file_name is not None:
        return Path(config.config_file_name).resolve().parent
    return Path(__file__).resolve().parents[1]


def _database_url() -> str:
    load_dotenv(_project_root() / ".env", override=False)
    return os.getenv("DATABASE_URL", _DEFAULT_DATABASE_URL)


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _database_url()

    connectable: AsyncEngine = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

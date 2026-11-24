from alembic import context
from sqlalchemy import engine_from_config, pool

from app.config import get_settings
from app.models import Base
from app.security.crypto import EncryptedString


def render_item(type_, obj, autogen_context):  # noqa: ANN001, ANN201
    """Encrypted columns are plain VARCHAR in the database; never import app code in migrations."""
    if type_ == "type" and isinstance(obj, EncryptedString):
        return f"sa.String(length={obj.impl.length})"
    return False


config = context.config
config.set_main_option("sqlalchemy.url", get_settings().database_url)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        render_item=render_item,
        compare_type=True,
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
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            render_item=render_item,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

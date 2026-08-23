"""Launch lightnovel-crawler with a narrow SQLite migration compatibility fix."""

from typing import Any


def _ddl_literal(value: Any, *_: Any, **__: Any) -> Any:
    """Return a SQL literal column rather than a bind parameter for DDL defaults."""
    from sqlalchemy import literal_column

    if value is None:
        rendered = "NULL"
    elif isinstance(value, bool):
        rendered = "1" if value else "0"
    elif isinstance(value, (int, float)):
        rendered = str(value)
    elif isinstance(value, str):
        rendered = "'" + value.replace("'", "''") + "'"
    else:
        raise TypeError(f"Unsupported migration default type: {type(value).__name__}")
    return literal_column(rendered)


def main() -> None:
    import sqlmodel

    # lncrawl 4.14 uses sa.literal(0) as a SQLite column server_default. Alembic
    # otherwise emits `DEFAULT :param_1`, but SQLite DDL cannot contain bind parameters.
    sqlmodel.literal = _ddl_literal

    from lncrawl import main as lncrawl_main

    lncrawl_main()

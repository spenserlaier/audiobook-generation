from sqlalchemy.dialects import sqlite

from audiobook.lncrawl_compat import _ddl_literal


def test_ddl_literals_compile_without_bind_parameters():
    dialect = sqlite.dialect()
    assert str(_ddl_literal(0).compile(dialect=dialect)) == "0"
    assert str(_ddl_literal(True).compile(dialect=dialect)) == "1"
    assert str(_ddl_literal("it's").compile(dialect=dialect)) == "'it''s'"

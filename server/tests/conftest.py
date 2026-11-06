from collections.abc import Iterator
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

from rulecite.config import Settings
from rulecite.db import connect


@pytest.fixture
def conn() -> Iterator[psycopg.Connection]:
    """테스트마다 임시 스키마를 만들어 그 안에서만 테이블을 만들고, 끝나면 지운다."""
    schema = sql.Identifier(f"test_{uuid4().hex[:12]}")
    with connect(Settings(), autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(schema))
        connection.execute(sql.SQL("SET search_path TO {}, public").format(schema))
        try:
            yield connection
        finally:
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(schema))

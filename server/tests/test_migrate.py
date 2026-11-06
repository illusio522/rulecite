from uuid import uuid4

import psycopg
import pytest

from rulecite.db.migrate import apply_migrations

ZERO_EMBEDDING = "[" + ",".join(["0"] * 1536) + "]"


def insert_document(conn: psycopg.Connection, access_level: str) -> int:
    row = conn.execute(
        "INSERT INTO documents"
        " (title, doc_type, access_level, version, effective_date, source_path)"
        " VALUES ('테스트 규정', 'COMPANY_RULE', %s, '1.0', '2026-01-01', %s)"
        " RETURNING id",
        (access_level, f"data/company/{uuid4().hex}.md"),
    ).fetchone()
    return row[0]


def insert_chunk(conn: psycopg.Connection, document_id: int, access_level: str) -> None:
    conn.execute(
        "INSERT INTO chunks"
        " (document_id, path, citation, content, embedding, access_level)"
        " VALUES (%s, '제1조', '테스트 규정 제1조', '본문', %s::vector, %s)",
        (document_id, ZERO_EMBEDDING, access_level),
    )


def table_names(conn: psycopg.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT table_name FROM information_schema.tables"
        " WHERE table_schema = current_schema()"
    )
    return {row[0] for row in rows}


def test_apply_migrations_creates_tables_on_empty_schema(conn):
    """빈 스키마에 적용하면 문서·조각·마이그레이션 기록 테이블이 생긴다."""
    # given: 빈 임시 스키마

    # when
    newly_applied = apply_migrations(conn)

    # then
    assert newly_applied == [
        "0001_create_documents_and_chunks.sql",
        "0002_add_chunk_citation.sql",
    ]
    assert {"documents", "chunks", "schema_migrations"} <= table_names(conn)


def test_apply_migrations_skips_already_applied_files(conn):
    """이미 적용한 마이그레이션은 다시 실행하지 않는다."""
    # given
    apply_migrations(conn)

    # when
    newly_applied = apply_migrations(conn)

    # then
    assert newly_applied == []


def test_chunk_rejects_access_level_different_from_document(conn):
    """조각의 접근 등급이 문서와 다르면 저장을 거부한다."""
    # given
    apply_migrations(conn)
    document_id = insert_document(conn, "HR_ONLY")

    # when / then
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        insert_chunk(conn, document_id, "ALL")


def test_document_rejects_unknown_access_level(conn):
    """정해지지 않은 접근 등급의 문서는 저장을 거부한다."""
    # given
    apply_migrations(conn)

    # when / then
    with pytest.raises(psycopg.errors.CheckViolation):
        insert_document(conn, "PUBLIC")


def test_changing_document_access_level_updates_its_chunks(conn):
    """문서의 접근 등급을 바꾸면 그 문서의 조각 접근 등급도 함께 바뀐다."""
    # given
    apply_migrations(conn)
    document_id = insert_document(conn, "ALL")
    insert_chunk(conn, document_id, "ALL")

    # when
    conn.execute(
        "UPDATE documents SET access_level = 'HR_ONLY' WHERE id = %s", (document_id,)
    )

    # then
    row = conn.execute(
        "SELECT access_level FROM chunks WHERE document_id = %s", (document_id,)
    ).fetchone()
    assert row[0] == "HR_ONLY"

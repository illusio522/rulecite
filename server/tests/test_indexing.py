from collections.abc import Sequence
from datetime import date

from rulecite.db.migrate import apply_migrations
from rulecite.embedding import EMBEDDING_DIMENSION
from rulecite.ingestion.chunking import chunk_by_structure
from rulecite.ingestion.indexing import index_document
from rulecite.ingestion.parsing import (
    COMPANY_RULE,
    Block,
    ParsedDocument,
    Section,
)


class FakeEmbedder:
    """API를 부르지 않고 입력 순서대로 구별되는 벡터를 돌려준다."""

    def __init__(self) -> None:
        self.inputs: list[tuple[str, str]] = []

    def embed_documents(
        self, documents: Sequence[tuple[str, str]]
    ) -> list[list[float]]:
        self.inputs += documents
        return [
            [float(i + 1)] + [0.0] * (EMBEDDING_DIMENSION - 1)
            for i in range(len(documents))
        ]

    def embed_query(self, query: str) -> list[float]:
        return [1.0] + [0.0] * (EMBEDDING_DIMENSION - 1)


def make_document(access_level: str = "HR_ONLY") -> ParsedDocument:
    return ParsedDocument(
        title="징계 지침",
        doc_type=COMPANY_RULE,
        access_level=access_level,
        version="1.0",
        effective_date=date(2026, 1, 1),
        source_path="data/company/fake.md",
        sections=(
            Section(
                path=("제1장 총칙",),
                label="제1조",
                title="목적",
                blocks=(Block(1, "", "이 지침은 목적을 정한다."),),
            ),
            Section(
                path=("제1장 총칙",),
                label="제2조",
                title="위원회",
                blocks=(Block(1, "제1항", "① 위원회는 5명으로 한다."),),
            ),
        ),
    )


def test_index_document_stores_document_and_chunks(conn):
    """문서 정보와 조각(경로, 출처, 본문, 임베딩, 접근 등급)을 저장한다."""
    # given
    apply_migrations(conn)
    document = make_document()
    embedder = FakeEmbedder()

    # when
    count = index_document(conn, document, chunk_by_structure(document), embedder)

    # then
    assert count == 2
    rows = conn.execute(
        "SELECT c.path, c.citation, c.content, c.access_level, vector_dims(c.embedding)"
        " FROM chunks c JOIN documents d ON d.id = c.document_id"
        " WHERE d.source_path = %s ORDER BY c.id",
        ("data/company/fake.md",),
    ).fetchall()
    assert rows[1] == (
        "제1장 총칙 > 제2조(위원회)",
        "징계 지침 제2조",
        "제2조(위원회)\n① 위원회는 5명으로 한다.",
        "HR_ONLY",
        EMBEDDING_DIMENSION,
    )
    assert embedder.inputs[0] == (
        "징계 지침 > 제1장 총칙",
        "제1조(목적)\n이 지침은 목적을 정한다.",
    )


def test_reindexing_replaces_existing_document(conn):
    """같은 원본 경로를 다시 인덱싱하면 기존 문서와 조각을 바꿔 넣는다."""
    # given
    apply_migrations(conn)
    first = make_document("HR_ONLY")
    index_document(conn, first, chunk_by_structure(first), FakeEmbedder())
    second = make_document("ALL")

    # when
    index_document(conn, second, chunk_by_structure(second), FakeEmbedder())

    # then
    documents = conn.execute("SELECT access_level FROM documents").fetchall()
    chunk_levels = conn.execute("SELECT DISTINCT access_level FROM chunks").fetchall()
    assert documents == [("ALL",)]
    assert chunk_levels == [("ALL",)]
    assert conn.execute("SELECT count(*) FROM chunks").fetchone()[0] == 2

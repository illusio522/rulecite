from datetime import date

import psycopg
import pytest

from rulecite.db.migrate import apply_migrations
from rulecite.embedding import EMBEDDING_DIMENSION
from rulecite.rag.retrieval import retrieve, search


def unit_vector(axis: int, weight: float = 1.0) -> list[float]:
    """axis 방향 성분이 weight이고 나머지는 1번 축 방향인 벡터.

    weight가 클수록 axis 방향 질문 벡터와 코사인 유사도가 높다.
    """
    values = [0.0] * EMBEDDING_DIMENSION
    values[axis] = weight
    values[1] = 1.0 - weight
    return values


def literal(vector: list[float]) -> str:
    return "[" + ",".join(map(str, vector)) + "]"


def add_document(
    conn: psycopg.Connection, title: str, access_level: str, chunks: dict[str, float]
) -> None:
    """chunks는 {출처 문자열: 0번 축 가중치}다."""
    document_id = conn.execute(
        "INSERT INTO documents"
        " (title, doc_type, access_level, version, effective_date, source_path)"
        " VALUES (%s, 'COMPANY_RULE', %s, '1.0', '2026-01-01', %s) RETURNING id",
        (title, access_level, f"data/company/{title}.md"),
    ).fetchone()[0]
    for citation, weight in chunks.items():
        conn.execute(
            "INSERT INTO chunks"
            " (document_id, path, citation, content, embedding, access_level)"
            " VALUES (%s, %s, %s, %s, %s::vector, %s)",
            (
                document_id,
                citation,
                citation,
                f"{citation} 본문",
                literal(unit_vector(0, weight)),
                access_level,
            ),
        )


@pytest.fixture
def indexed(conn):
    """일반 문서 조각 3개와, 질문과 가장 비슷한 인사팀 전용 조각 1개를 넣는다."""
    apply_migrations(conn)
    add_document(
        conn, "복리후생", "ALL", {"복리후생 제1조": 0.9, "복리후생 제2조": 0.5}
    )
    add_document(conn, "휴가안내", "ALL", {"휴가안내 제1조": 0.7})
    add_document(conn, "징계지침", "HR_ONLY", {"징계지침 제1조": 1.0})
    return conn


def test_results_are_ordered_by_similarity(indexed):
    """질문과 비슷한 조각부터 차례로 돌려준다."""
    # given
    query = unit_vector(0)

    # when
    results = search(indexed, query, ["ALL", "HR_ONLY"])

    # then
    assert [r.citation for r in results] == [
        "징계지침 제1조",
        "복리후생 제1조",
        "휴가안내 제1조",
        "복리후생 제2조",
    ]
    assert results[0].score == pytest.approx(1.0)
    assert results[0].score > results[1].score > results[2].score


def test_disallowed_access_level_is_never_returned(indexed):
    """가장 비슷해도 허용되지 않은 접근 등급의 조각은 결과에 나오지 않는다."""
    # given
    query = unit_vector(0)

    # when
    results = search(indexed, query, ["ALL"])

    # then
    assert [r.citation for r in results] == [
        "복리후생 제1조",
        "휴가안내 제1조",
        "복리후생 제2조",
    ]
    assert {r.access_level for r in results} == {"ALL"}


def test_top_k_limits_result_count(indexed):
    """top_k개까지만 돌려준다."""
    # given
    query = unit_vector(0)

    # when
    results = search(indexed, query, ["ALL"], top_k=2)

    # then
    assert [r.citation for r in results] == ["복리후생 제1조", "휴가안내 제1조"]


def test_result_includes_document_information_for_citation(indexed):
    """결과에는 답변 출처에 쓸 문서 제목, 버전, 시행일이 들어 있다."""
    # given
    query = unit_vector(0)

    # when
    [result] = search(indexed, query, ["ALL"], top_k=1)

    # then
    assert result.document_title == "복리후생"
    assert result.document_version == "1.0"
    assert result.effective_date == date(2026, 1, 1)
    assert result.content == "복리후생 제1조 본문"


@pytest.mark.parametrize("levels", [[], ["PUBLIC"], ["ALL", "SECRET"]])
def test_invalid_access_levels_are_rejected(indexed, levels):
    """허용 등급이 비었거나 정해지지 않은 값이면 검색하지 않고 거부한다."""
    # given
    query = unit_vector(0)

    # when / then
    with pytest.raises(ValueError, match="access levels"):
        search(indexed, query, levels)


def test_retrieve_embeds_question_then_searches(indexed):
    """retrieve는 질문을 임베딩한 벡터로 검색한다."""

    # given
    class FakeEmbedder:
        def embed_documents(self, documents):
            raise AssertionError("not used")

        def embed_query(self, query: str) -> list[float]:
            return unit_vector(0)

    # when
    results = retrieve(indexed, FakeEmbedder(), "결혼 휴가", ["ALL"], top_k=1)

    # then
    assert results[0].citation == "복리후생 제1조"

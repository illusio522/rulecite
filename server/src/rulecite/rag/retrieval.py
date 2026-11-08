"""질문과 비슷한 조각을 권한 조건 안에서 찾는다.

권한 조건은 LLM 호출 전에 SQL로 건다.
허용되지 않은 접근 등급의 조각은 후보에도 오르지 않는다.
인덱스 없이 전체를 비교하는 정확 검색이다.
이유는 docs/adr/0003-database-and-migrations.md에 있다.

확인용 실행: poetry run python -m rulecite.rag.retrieval "질문" --levels ALL
"""

import argparse
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

import psycopg

from rulecite.config import Settings
from rulecite.db import connect
from rulecite.embedding import Embedder, GeminiEmbedder
from rulecite.ingestion.parsing import ACCESS_LEVELS

DEFAULT_TOP_K = 5

SEARCH_SQL = """
SELECT c.id, c.citation, c.content, c.access_level,
       d.title, d.version, d.effective_date,
       1 - (c.embedding <=> %(query)s::vector) AS score
FROM chunks c
JOIN documents d ON d.id = c.document_id
WHERE c.access_level = ANY(%(levels)s)
ORDER BY c.embedding <=> %(query)s::vector
LIMIT %(top_k)s
"""


@dataclass(frozen=True)
class SearchResult:
    chunk_id: int
    citation: str
    content: str
    access_level: str
    document_title: str
    document_version: str
    effective_date: date
    score: float


def search(
    conn: psycopg.Connection,
    query_vector: Sequence[float],
    access_levels: Sequence[str],
    top_k: int = DEFAULT_TOP_K,
) -> list[SearchResult]:
    """허용된 접근 등급의 조각 중 질문 벡터와 가장 비슷한 top_k개를 돌려준다."""
    levels = list(access_levels)
    if not levels or not set(levels) <= ACCESS_LEVELS:
        raise ValueError(f"Invalid access levels: {levels!r}")
    if top_k < 1:
        raise ValueError(f"top_k must be positive: {top_k}")
    query = "[" + ",".join(str(value) for value in query_vector) + "]"
    rows = conn.execute(
        SEARCH_SQL, {"query": query, "levels": levels, "top_k": top_k}
    ).fetchall()
    return [
        SearchResult(
            chunk_id=row[0],
            citation=row[1],
            content=row[2],
            access_level=row[3],
            document_title=row[4],
            document_version=row[5],
            effective_date=row[6],
            score=float(row[7]),
        )
        for row in rows
    ]


def retrieve(
    conn: psycopg.Connection,
    embedder: Embedder,
    question: str,
    access_levels: Sequence[str],
    top_k: int = DEFAULT_TOP_K,
) -> list[SearchResult]:
    """질문을 임베딩해 search를 실행한다."""
    return search(conn, embedder.embed_query(question), access_levels, top_k)


def main() -> None:
    parser = argparse.ArgumentParser(description="Search chunks for a question.")
    parser.add_argument("question")
    parser.add_argument("--levels", default="ALL", help="comma-separated, e.g. ALL")
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    args = parser.parse_args()

    settings = Settings()
    if settings.gemini_api_key is None:
        raise SystemExit("GEMINI_API_KEY is not set in .env")
    embedder = GeminiEmbedder(
        settings.gemini_api_key.get_secret_value(), settings.embedding_model
    )
    with connect(settings) as conn:
        results = retrieve(
            conn, embedder, args.question, args.levels.split(","), args.top_k
        )
    for rank, result in enumerate(results, start=1):
        print(
            f"{rank}. {result.score:.3f} {result.citation}"
            f" (시행 {result.effective_date}, {result.access_level})"
        )


if __name__ == "__main__":
    main()

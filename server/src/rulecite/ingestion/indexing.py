"""문서를 파싱·분할·임베딩해 DB에 저장한다.

실행: poetry run python -m rulecite.ingestion.indexing
data/public과 data/company의 모든 문서를 구조 분할로 인덱싱한다.
"""

import logging
from pathlib import Path

import psycopg

from rulecite.config import Settings
from rulecite.db import connect
from rulecite.embedding import Embedder, GeminiEmbedder
from rulecite.ingestion.chunking import Chunk, chunk_by_structure
from rulecite.ingestion.parsing import ParsedDocument, parse_document

# 저장소 루트 (server/src/rulecite/ingestion/indexing.py 기준 네 단계 위)
REPO_ROOT = Path(__file__).resolve().parents[4]
DATA_DIRS = ("data/public", "data/company")
DOCUMENT_SUFFIXES = {".html", ".md"}


def find_documents(root: Path = REPO_ROOT) -> list[Path]:
    return sorted(
        path
        for directory in DATA_DIRS
        for path in (root / directory).iterdir()
        if path.suffix in DOCUMENT_SUFFIXES
    )


def index_document(
    conn: psycopg.Connection,
    document: ParsedDocument,
    chunks: list[Chunk],
    embedder: Embedder,
) -> int:
    """문서와 조각을 저장하고 저장한 조각 수를 돌려준다.

    같은 source_path의 기존 문서와 조각은 지우고 새로 넣는다.
    임베딩은 DB 트랜잭션 밖에서 먼저 만들어, 네트워크 대기 중에 트랜잭션을 잡지 않는다.
    autocommit 연결을 받아 문서 하나를 한 트랜잭션으로 저장한다.
    """
    vectors = embedder.embed_documents(
        [(" > ".join([document.title, *chunk.path]), chunk.content) for chunk in chunks]
    )
    with conn.transaction():
        conn.execute(
            "DELETE FROM documents WHERE source_path = %s", (document.source_path,)
        )
        document_id = conn.execute(
            "INSERT INTO documents"
            " (title, doc_type, access_level, version, effective_date, source_path)"
            " VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
            (
                document.title,
                document.doc_type,
                document.access_level,
                document.version,
                document.effective_date,
                document.source_path,
            ),
        ).fetchone()[0]
        with conn.cursor() as cursor:
            cursor.executemany(
                "INSERT INTO chunks"
                " (document_id, path, citation, content, embedding, access_level)"
                " VALUES (%s, %s, %s, %s, %s::vector, %s)",
                [
                    (
                        document_id,
                        " > ".join(
                            part for part in (*chunk.path, chunk.heading) if part
                        ),
                        chunk.citation,
                        chunk.content,
                        _vector_literal(vector),
                        document.access_level,
                    )
                    for chunk, vector in zip(chunks, vectors, strict=True)
                ],
            )
    return len(chunks)


def _vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(str(value) for value in vector) + "]"


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    settings = Settings()
    if settings.gemini_api_key is None:
        raise SystemExit("GEMINI_API_KEY is not set in .env")
    embedder = GeminiEmbedder(
        settings.gemini_api_key.get_secret_value(), settings.embedding_model
    )
    total = 0
    with connect(settings, autocommit=True) as conn:
        for path in find_documents():
            document = parse_document(path, REPO_ROOT)
            count = index_document(
                conn, document, chunk_by_structure(document), embedder
            )
            total += count
            print(f"Indexed {document.source_path}: {count} chunks")
    print(f"Indexed {total} chunks in total")


if __name__ == "__main__":
    main()

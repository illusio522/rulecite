"""임베딩 제공사 인터페이스와 Gemini API 구현.

제공사를 바꿀 때는 Embedder를 따르는 구현만 추가한다.
모델, 차원, 입력 형식의 근거는 docs/adr/0002-llm-and-embedding-models.md에 있다.
"""

import time
from collections.abc import Callable, Sequence
from typing import Protocol

import httpx2

from rulecite.gemini import GeminiClient

# DB 스키마의 vector(1536)와 같아야 한다.
EMBEDDING_DIMENSION = 1536


class Embedder(Protocol):
    def embed_documents(
        self, documents: Sequence[tuple[str, str]]
    ) -> list[list[float]]:
        """(제목, 본문) 목록을 같은 순서의 벡터 목록으로 바꾼다."""
        ...

    def embed_query(self, query: str) -> list[float]: ...


class GeminiEmbedder:
    def __init__(
        self,
        api_key: str,
        model: str,
        client: httpx2.Client | None = None,
        batch_size: int = 50,
        max_retries: int = 8,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._gemini = GeminiClient(api_key, client, max_retries, sleep)
        self._model = model
        self._batch_size = batch_size

    def embed_documents(
        self, documents: Sequence[tuple[str, str]]
    ) -> list[list[float]]:
        texts = [
            f"title: {title or 'none'} | text: {text}" for title, text in documents
        ]
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self._batch_size):
            vectors += self._embed_batch(texts[start : start + self._batch_size])
        return vectors

    def embed_query(self, query: str) -> list[float]:
        return self._embed_batch([f"task: question answering | query: {query}"])[0]

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        body = {
            "requests": [
                {
                    "model": f"models/{self._model}",
                    "content": {"parts": [{"text": text}]},
                    "outputDimensionality": EMBEDDING_DIMENSION,
                }
                for text in texts
            ]
        }
        data = self._gemini.post(f"/models/{self._model}:batchEmbedContents", body)
        embeddings = data.get("embeddings")
        if not isinstance(embeddings, list) or len(embeddings) != len(texts):
            raise ValueError("Unexpected embedding response: count mismatch")
        vectors = [item.get("values") for item in embeddings]
        if any(
            not isinstance(v, list) or len(v) != EMBEDDING_DIMENSION for v in vectors
        ):
            raise ValueError("Unexpected embedding response: dimension mismatch")
        return vectors

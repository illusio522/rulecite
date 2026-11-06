"""임베딩 제공사 인터페이스와 Gemini API 구현.

제공사를 바꿀 때는 Embedder를 따르는 구현만 추가한다.
모델, 차원, 입력 형식의 근거는 docs/adr/0002-llm-and-embedding-models.md에 있다.
"""

import logging
import re
import time
from collections.abc import Callable, Sequence
from typing import Protocol

import httpx2

logger = logging.getLogger(__name__)

# DB 스키마의 vector(1536)와 같아야 한다.
EMBEDDING_DIMENSION = 1536
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


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
        if not api_key:
            raise ValueError("GEMINI_API_KEY is not set")
        self._api_key = api_key
        self._model = model
        self._client = client or httpx2.Client(timeout=httpx2.Timeout(30.0))
        self._batch_size = batch_size
        self._max_retries = max_retries
        self._sleep = sleep

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
        response = self._post(f"/models/{self._model}:batchEmbedContents", body)
        embeddings = response.json().get("embeddings")
        if not isinstance(embeddings, list) or len(embeddings) != len(texts):
            raise ValueError("Unexpected embedding response: count mismatch")
        vectors = [item.get("values") for item in embeddings]
        if any(
            not isinstance(v, list) or len(v) != EMBEDDING_DIMENSION for v in vectors
        ):
            raise ValueError("Unexpected embedding response: dimension mismatch")
        return vectors

    def _post(self, path: str, body: dict) -> httpx2.Response:
        """요청 한도(429)나 일시 오류(5xx)면 기다렸다가 다시 시도한다."""
        attempt = 0
        while True:
            response = self._client.post(
                GEMINI_BASE_URL + path,
                json=body,
                headers={"x-goog-api-key": self._api_key},
            )
            if response.status_code in RETRYABLE_STATUS and attempt < self._max_retries:
                delay = _retry_delay(response, attempt)
                logger.warning(
                    "Gemini API returned %s, retrying in %.0fs (attempt %d/%d)",
                    response.status_code,
                    delay,
                    attempt + 1,
                    self._max_retries,
                )
                self._sleep(delay)
                attempt += 1
                continue
            response.raise_for_status()
            return response


def _retry_delay(response: httpx2.Response, attempt: int) -> float:
    """서버가 알려 준 대기 시간을 따르고, 없으면 지수적으로 늘린다(최대 60초).

    순서: 응답 본문의 RetryInfo.retryDelay("37s"), Retry-After 헤더, 1·2·4…초.
    """
    try:
        details = response.json().get("error", {}).get("details", [])
    except ValueError:
        details = []
    for detail in details:
        if detail.get("@type", "").endswith("RetryInfo"):
            match = re.fullmatch(r"(\d+(?:\.\d+)?)s", str(detail.get("retryDelay", "")))
            if match is not None:
                return float(match.group(1))
    retry_after = response.headers.get("retry-after", "")
    if retry_after.isdigit():
        return float(retry_after)
    return float(min(2**attempt, 60))

import json

import httpx2
import pytest

from rulecite.embedding import EMBEDDING_DIMENSION, GeminiEmbedder

FAKE_KEY = "test-key-not-real"


def vector(value: float) -> list[float]:
    return [value] * EMBEDDING_DIMENSION


class FakeGemini:
    """batchEmbedContents 요청을 기록하고, 정해 둔 상태 코드를 차례로 돌려준다."""

    def __init__(self, statuses: list[int] | None = None) -> None:
        self.requests: list[httpx2.Request] = []
        self.statuses = list(statuses or [])

    def handle(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        status = self.statuses.pop(0) if self.statuses else 200
        if status != 200:
            return httpx2.Response(status, json={"error": {"code": status}})
        count = len(json.loads(request.content)["requests"])
        embeddings = [{"values": vector(float(i))} for i in range(count)]
        return httpx2.Response(200, json={"embeddings": embeddings})

    def client(self) -> httpx2.Client:
        return httpx2.Client(transport=httpx2.MockTransport(self.handle))


def body(request: httpx2.Request) -> dict:
    return json.loads(request.content)


def test_embed_documents_sends_batches_in_document_format():
    """문서는 title·text 형식으로 묶음 요청을 보내고, 묶음 크기를 넘으면 나눠 보낸다."""
    # given
    fake = FakeGemini()
    embedder = GeminiEmbedder(
        FAKE_KEY, "gemini-embedding-2", client=fake.client(), batch_size=2
    )

    # when
    vectors = embedder.embed_documents(
        [("근로기준법", "제1조"), ("", "제2조"), ("", "제3조")]
    )

    # then
    assert len(vectors) == 3
    assert [len(body(r)["requests"]) for r in fake.requests] == [2, 1]
    first = body(fake.requests[0])["requests"][0]
    assert first["model"] == "models/gemini-embedding-2"
    assert first["content"]["parts"][0]["text"] == "title: 근로기준법 | text: 제1조"
    assert first["outputDimensionality"] == EMBEDDING_DIMENSION
    second = body(fake.requests[0])["requests"][1]
    assert second["content"]["parts"][0]["text"] == "title: none | text: 제2조"
    assert fake.requests[0].url.path.endswith(":batchEmbedContents")
    assert fake.requests[0].headers["x-goog-api-key"] == FAKE_KEY


def test_embed_query_uses_question_answering_task_format():
    """질문은 question answering 작업 지시를 붙여 보낸다."""
    # given
    fake = FakeGemini()
    embedder = GeminiEmbedder(FAKE_KEY, "gemini-embedding-2", client=fake.client())

    # when
    result = embedder.embed_query("연차는 며칠인가요?")

    # then
    [request] = body(fake.requests[0])["requests"]
    assert request["content"]["parts"][0]["text"] == (
        "task: question answering | query: 연차는 며칠인가요?"
    )
    assert len(result) == EMBEDDING_DIMENSION


def test_rate_limited_request_is_retried_after_waiting():
    """요청 한도(429)에 걸리면 기다렸다가 다시 보낸다."""
    # given
    fake = FakeGemini(statuses=[429, 429])
    waits: list[float] = []
    embedder = GeminiEmbedder(
        FAKE_KEY, "gemini-embedding-2", client=fake.client(), sleep=waits.append
    )

    # when
    embedder.embed_query("질문")

    # then
    assert len(fake.requests) == 3
    assert waits == [1.0, 2.0]


def test_client_error_is_raised_without_retry():
    """잘못된 요청(400)은 다시 보내지 않고 오류를 올린다."""
    # given
    fake = FakeGemini(statuses=[400])
    embedder = GeminiEmbedder(
        FAKE_KEY, "gemini-embedding-2", client=fake.client(), sleep=lambda _: None
    )

    # when / then
    with pytest.raises(httpx2.HTTPStatusError):
        embedder.embed_query("질문")
    assert len(fake.requests) == 1


def test_unexpected_dimension_is_rejected():
    """응답 벡터의 차원이 DB 스키마와 다르면 거부한다."""

    # given
    def handle(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json={"embeddings": [{"values": [0.1] * 768}]})

    client = httpx2.Client(transport=httpx2.MockTransport(handle))
    embedder = GeminiEmbedder(FAKE_KEY, "gemini-embedding-2", client=client)

    # when / then
    with pytest.raises(ValueError, match="dimension"):
        embedder.embed_query("질문")


def test_missing_api_key_is_rejected():
    """API 키가 비어 있으면 만들 때 거부한다."""
    # given
    api_key = ""

    # when / then
    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        GeminiEmbedder(api_key, "gemini-embedding-2")


def test_retry_waits_for_delay_given_by_server():
    """429 응답 본문에 서버가 알려 준 대기 시간이 있으면 그만큼 기다린다."""
    # given
    responses = [
        httpx2.Response(
            429,
            json={
                "error": {
                    "code": 429,
                    "details": [
                        {
                            "@type": "type.googleapis.com/google.rpc.RetryInfo",
                            "retryDelay": "37s",
                        }
                    ],
                }
            },
        ),
        httpx2.Response(200, json={"embeddings": [{"values": vector(0.0)}]}),
    ]
    client = httpx2.Client(transport=httpx2.MockTransport(lambda _: responses.pop(0)))
    waits: list[float] = []
    embedder = GeminiEmbedder(
        FAKE_KEY, "gemini-embedding-2", client=client, sleep=waits.append
    )

    # when
    embedder.embed_query("질문")

    # then
    assert waits == [37.0]

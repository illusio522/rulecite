import json

import httpx2
import pytest

from rulecite.llm import GeminiLLM

FAKE_KEY = "test-key-not-real"


def gemini_client(handler) -> httpx2.Client:
    return httpx2.Client(transport=httpx2.MockTransport(handler))


def test_generate_sends_system_instruction_and_thinking_level():
    """시스템 지시, 사용자 메시지, 생각 수준을 generateContent 형식으로 보낸다."""
    # given
    requests: list[httpx2.Request] = []

    def handle(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return httpx2.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": "답변 [1]"}]}}]},
        )

    llm = GeminiLLM(FAKE_KEY, "gemini-3.6-flash", client=gemini_client(handle))

    # when
    llm.generate("시스템 지시", "질문")

    # then
    [request] = requests
    body = json.loads(request.content)
    assert request.url.path.endswith("/models/gemini-3.6-flash:generateContent")
    assert request.headers["x-goog-api-key"] == FAKE_KEY
    assert body["systemInstruction"] == {"parts": [{"text": "시스템 지시"}]}
    assert body["contents"] == [{"role": "user", "parts": [{"text": "질문"}]}]
    assert body["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "LOW"}


def test_generate_reads_text_without_thoughts_and_token_usage():
    """생각 내용(thought) 부분은 빼고 답변 텍스트와 토큰 사용량을 읽는다."""

    # given
    def handle(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"text": "생각 중", "thought": True},
                                {"text": " 연차는 15일입니다 [1]. "},
                            ]
                        }
                    }
                ],
                "usageMetadata": {
                    "promptTokenCount": 120,
                    "candidatesTokenCount": 30,
                    "thoughtsTokenCount": 15,
                },
            },
        )

    llm = GeminiLLM(FAKE_KEY, "gemini-3.6-flash", client=gemini_client(handle))

    # when
    generation = llm.generate("시스템", "질문")

    # then
    assert generation.text == "연차는 15일입니다 [1]."
    assert (
        generation.prompt_tokens,
        generation.output_tokens,
        generation.thinking_tokens,
    ) == (120, 30, 15)


def test_generate_rejects_response_without_candidates():
    """답변 후보가 없는 응답(예: 차단된 요청)은 오류로 처리한다."""

    # given
    def handle(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json={"promptFeedback": {"blockReason": "OTHER"}})

    llm = GeminiLLM(FAKE_KEY, "gemini-3.6-flash", client=gemini_client(handle))

    # when / then
    with pytest.raises(ValueError, match="no candidates"):
        llm.generate("시스템", "질문")

"""답변 생성 LLM 인터페이스와 Gemini API 구현.

제공사를 바꿀 때는 LLM을 따르는 구현만 추가한다.
모델 선택 근거는 docs/adr/0002-llm-and-embedding-models.md에 있다.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

import httpx2

from rulecite.gemini import GeminiClient

# 근거 자료 안에서 답하는 작업이라 깊은 추론보다 응답 시간과 비용을 우선한다.
DEFAULT_THINKING_LEVEL = "LOW"


@dataclass(frozen=True)
class Generation:
    text: str
    prompt_tokens: int
    output_tokens: int
    thinking_tokens: int


class LLM(Protocol):
    def generate(self, system: str, user: str) -> Generation: ...


class GeminiLLM:
    def __init__(
        self,
        api_key: str,
        model: str,
        client: httpx2.Client | None = None,
        thinking_level: str = DEFAULT_THINKING_LEVEL,
        max_retries: int = 8,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._gemini = GeminiClient(api_key, client, max_retries, sleep)
        self._model = model
        self._thinking_level = thinking_level

    def generate(self, system: str, user: str) -> Generation:
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {
                "thinkingConfig": {"thinkingLevel": self._thinking_level}
            },
        }
        data = self._gemini.post(f"/models/{self._model}:generateContent", body)
        candidates = data.get("candidates") or []
        if not candidates:
            raise ValueError("Gemini returned no candidates")
        parts = candidates[0].get("content", {}).get("parts", [])
        text = "".join(
            part.get("text", "") for part in parts if not part.get("thought")
        )
        if not text.strip():
            reason = candidates[0].get("finishReason", "")
            raise ValueError(f"Gemini returned empty text (finishReason={reason})")
        usage = data.get("usageMetadata", {})
        return Generation(
            text=text.strip(),
            prompt_tokens=usage.get("promptTokenCount", 0),
            output_tokens=usage.get("candidatesTokenCount", 0),
            thinking_tokens=usage.get("thoughtsTokenCount", 0),
        )

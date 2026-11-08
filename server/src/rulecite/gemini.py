"""Gemini REST API 공용 호출부.

임베딩과 답변 생성이 함께 쓴다.
요청 한도(429)와 일시 오류(5xx) 재시도를 한곳에서 처리한다.
"""

import logging
import re
import time
from collections.abc import Callable

import httpx2

logger = logging.getLogger(__name__)

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class GeminiClient:
    def __init__(
        self,
        api_key: str,
        client: httpx2.Client | None = None,
        max_retries: int = 8,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not api_key:
            raise ValueError("GEMINI_API_KEY is not set")
        self._api_key = api_key
        self._client = client or httpx2.Client(timeout=httpx2.Timeout(60.0))
        self._max_retries = max_retries
        self._sleep = sleep

    def post(self, path: str, body: dict) -> dict:
        """API에 요청을 보내고 JSON 응답을 돌려준다.

        요청 한도나 일시 오류면 기다렸다가 다시 시도하고,
        재시도가 끝나거나 다른 오류면 httpx2.HTTPStatusError를 올린다.
        """
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
            return response.json()


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

from __future__ import annotations

import httpx

from app.ai.providers.base import ModelProvider
from app.ai.rate_limits import normalize_rate_limit_headers
from app.ai.schemas import ModelRequest, ModelResponse


class OpenAICompatibleChatProvider(ModelProvider):
    def __init__(
        self,
        *,
        name: str,
        api_key: str,
        base_url: str,
        timeout_seconds: float = 120.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.name = name
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._client = client

    async def _post(self, payload: dict) -> httpx.Response:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if self._client is not None:
            response = await self._client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            return response

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            return response

    async def generate(self, request: ModelRequest) -> ModelResponse:
        payload: dict = {
            "model": request.model,
            "messages": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.user_prompt},
            ],
            "stream": False,
        }
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.max_output_tokens is not None:
            payload["max_tokens"] = request.max_output_tokens

        http_response = await self._post(payload)
        data = http_response.json()
        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError(f"{self.name} returned no choices")
        message = choices[0].get("message") or {}
        text = message.get("content")
        if not isinstance(text, str) or not text.strip():
            raise RuntimeError(f"{self.name} returned an empty text response")

        usage = data.get("usage") or {}
        rate_limit = normalize_rate_limit_headers(http_response.headers)
        return ModelResponse(
            text=text.strip(),
            provider=self.name,
            model=str(data.get("model") or request.model),
            request_id=data.get("id") or rate_limit.get("request_id"),
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
            metadata={
                "finish_reason": choices[0].get("finish_reason"),
                "rate_limit": rate_limit,
            },
        )

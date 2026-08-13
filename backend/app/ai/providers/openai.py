from __future__ import annotations

import httpx

from app.ai.providers.base import ModelProvider
from app.ai.rate_limits import normalize_rate_limit_headers
from app.ai.schemas import ModelRequest, ModelResponse


class OpenAIProvider(ModelProvider):
    name = "openai"

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        timeout_seconds: float = 120.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._client = client

    @staticmethod
    def _extract_text(data: dict) -> str:
        top_level = data.get("output_text")
        if isinstance(top_level, str) and top_level.strip():
            return top_level.strip()

        parts: list[str] = []
        for item in data.get("output") or []:
            if item.get("type") != "message":
                continue
            for content in item.get("content") or []:
                if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                    parts.append(content["text"])
        text = "".join(parts).strip()
        if not text:
            raise RuntimeError("OpenAI returned an empty text response")
        return text

    async def _post(self, payload: dict) -> httpx.Response:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if self._client is not None:
            response = await self._client.post(
                f"{self.base_url}/responses",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            return response

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(
                f"{self.base_url}/responses",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            return response

    async def generate(self, request: ModelRequest) -> ModelResponse:
        payload: dict = {
            "model": request.model,
            "instructions": request.system_prompt,
            "input": request.user_prompt,
        }
        if request.max_output_tokens is not None:
            payload["max_output_tokens"] = request.max_output_tokens
        if request.temperature is not None:
            payload["temperature"] = request.temperature

        http_response = await self._post(payload)
        data = http_response.json()
        usage = data.get("usage") or {}
        rate_limit = normalize_rate_limit_headers(http_response.headers)
        return ModelResponse(
            text=self._extract_text(data),
            provider=self.name,
            model=str(data.get("model") or request.model),
            request_id=data.get("id") or rate_limit.get("request_id"),
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
            metadata={"status": data.get("status"), "rate_limit": rate_limit},
        )

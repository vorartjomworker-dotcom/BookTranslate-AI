from __future__ import annotations

import httpx

from app.ai.providers.base import ModelProvider
from app.ai.rate_limits import normalize_rate_limit_headers
from app.ai.schemas import ModelRequest, ModelResponse


class GeminiProvider(ModelProvider):
    name = "gemini"

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
        timeout_seconds: float = 120.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._client = client

    @staticmethod
    def _extract_text(data: dict) -> str:
        parts: list[str] = []
        for step in data.get("steps") or []:
            if step.get("type") != "model_output":
                continue
            for content in step.get("content") or []:
                if content.get("type") == "text" and isinstance(content.get("text"), str):
                    parts.append(content["text"])
        text = "".join(parts).strip()
        if not text:
            raise RuntimeError("Gemini returned an empty text response")
        return text

    async def _post(self, payload: dict) -> httpx.Response:
        headers = {
            "x-goog-api-key": self.api_key,
            "Content-Type": "application/json",
        }
        if self._client is not None:
            response = await self._client.post(
                f"{self.base_url}/interactions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            return response

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(
                f"{self.base_url}/interactions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            return response

    async def generate(self, request: ModelRequest) -> ModelResponse:
        generation_config: dict = {}
        if request.max_output_tokens is not None:
            generation_config["max_output_tokens"] = request.max_output_tokens
        if request.temperature is not None:
            generation_config["temperature"] = request.temperature

        payload: dict = {
            "model": request.model,
            "input": request.user_prompt,
            "system_instruction": request.system_prompt,
            "store": False,
        }
        if generation_config:
            payload["generation_config"] = generation_config

        http_response = await self._post(payload)
        data = http_response.json()
        usage = data.get("usage") or {}
        rate_limit = normalize_rate_limit_headers(http_response.headers)
        return ModelResponse(
            text=self._extract_text(data),
            provider=self.name,
            model=str(data.get("model") or request.model),
            request_id=data.get("id") or rate_limit.get("request_id"),
            input_tokens=usage.get("total_input_tokens"),
            output_tokens=usage.get("total_output_tokens"),
            metadata={"status": data.get("status"), "rate_limit": rate_limit},
        )

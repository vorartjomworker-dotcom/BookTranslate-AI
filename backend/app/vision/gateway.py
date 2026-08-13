from __future__ import annotations

from app.core.config import Settings
from app.vision.providers import OpenAIVisionProvider, VisionProvider
from app.vision.schemas import VisionResult


class VisionGateway:
    def __init__(self, providers: dict[str, VisionProvider]) -> None:
        self.providers = providers

    @classmethod
    def from_settings(cls, settings: Settings) -> "VisionGateway":
        providers: dict[str, VisionProvider] = {}
        if settings.openai_api_key:
            providers["openai"] = OpenAIVisionProvider(
                settings.openai_api_key,
                settings.openai_base_url,
                settings.ai_request_timeout_seconds,
            )
        return cls(providers)

    async def extract(
        self,
        *,
        provider: str,
        model: str,
        image_bytes: bytes,
        media_type: str,
        prompt: str,
    ) -> VisionResult:
        implementation = self.providers.get(provider)
        if implementation is None:
            raise RuntimeError(f"Vision provider '{provider}' is not configured")
        return await implementation.extract(
            image_bytes=image_bytes,
            media_type=media_type,
            model=model,
            prompt=prompt,
        )

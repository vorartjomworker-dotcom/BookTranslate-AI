from __future__ import annotations

from app.ai.providers.aitunnel import AITunnelProvider
from app.ai.providers.base import ModelProvider
from app.ai.providers.gemini import GeminiProvider
from app.ai.providers.kimi import KimiProvider
from app.ai.providers.openai import OpenAIProvider
from app.ai.schemas import ModelRequest, ModelResponse
from app.core.config import Settings


class ModelGateway:
    def __init__(self) -> None:
        self._providers: dict[str, ModelProvider] = {}

    def register(self, provider: ModelProvider) -> None:
        self._providers[provider.name] = provider

    @property
    def available_providers(self) -> list[str]:
        return sorted(self._providers)

    def has_provider(self, name: str) -> bool:
        return name in self._providers

    async def generate(self, provider_name: str, request: ModelRequest) -> ModelResponse:
        provider = self._providers.get(provider_name)
        if provider is None:
            available = ", ".join(self.available_providers) or "none"
            raise ValueError(
                f"AI provider '{provider_name}' is not configured. Available providers: {available}"
            )
        return await provider.generate(request)

    @classmethod
    def from_settings(cls, settings: Settings) -> "ModelGateway":
        gateway = cls()
        timeout = float(settings.ai_request_timeout_seconds)

        if settings.openai_api_key:
            gateway.register(
                OpenAIProvider(
                    api_key=settings.openai_api_key,
                    base_url=settings.openai_base_url,
                    timeout_seconds=timeout,
                )
            )
        if settings.kimi_api_key:
            gateway.register(
                KimiProvider(
                    api_key=settings.kimi_api_key,
                    base_url=settings.kimi_base_url,
                    timeout_seconds=timeout,
                )
            )
        if settings.gemini_api_key:
            gateway.register(
                GeminiProvider(
                    api_key=settings.gemini_api_key,
                    base_url=settings.gemini_base_url,
                    timeout_seconds=timeout,
                )
            )
        if settings.aitunnel_api_key:
            gateway.register(
                AITunnelProvider(
                    api_key=settings.aitunnel_api_key,
                    base_url=settings.aitunnel_base_url,
                    timeout_seconds=timeout,
                )
            )
        return gateway

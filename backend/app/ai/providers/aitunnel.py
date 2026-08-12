import httpx

from app.ai.providers.openai_compatible import OpenAICompatibleChatProvider


class AITunnelProvider(OpenAICompatibleChatProvider):
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.aitunnel.ru/v1",
        timeout_seconds: float = 120.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(
            name="aitunnel",
            api_key=api_key,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            client=client,
        )

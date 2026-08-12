import asyncio

import httpx

from app.ai.providers.aitunnel import AITunnelProvider
from app.ai.providers.gemini import GeminiProvider
from app.ai.providers.kimi import KimiProvider
from app.ai.providers.openai import OpenAIProvider
from app.ai.schemas import ModelRequest


_REQUEST = ModelRequest(
    model="test-model",
    system_prompt="system",
    user_prompt="translate this",
    max_output_tokens=100,
)


def test_openai_responses_adapter() -> None:
    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/v1/responses"
            assert request.headers["authorization"] == "Bearer test-key"
            return httpx.Response(
                200,
                json={
                    "id": "resp_1",
                    "model": "test-model",
                    "status": "completed",
                    "output": [
                        {
                            "type": "message",
                            "content": [{"type": "output_text", "text": "OpenAI translation"}],
                        }
                    ],
                    "usage": {"input_tokens": 10, "output_tokens": 4},
                },
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = OpenAIProvider(api_key="test-key", client=client)
            response = await provider.generate(_REQUEST)
        assert response.text == "OpenAI translation"
        assert response.request_id == "resp_1"
        assert response.input_tokens == 10
        assert response.output_tokens == 4

    asyncio.run(run())


def test_kimi_chat_completions_adapter() -> None:
    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/v1/chat/completions"
            return httpx.Response(
                200,
                json={
                    "id": "kimi_1",
                    "model": "kimi-test",
                    "choices": [
                        {"message": {"role": "assistant", "content": "Kimi translation"}, "finish_reason": "stop"}
                    ],
                    "usage": {"prompt_tokens": 11, "completion_tokens": 5},
                },
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = KimiProvider(api_key="test-key", client=client)
            response = await provider.generate(_REQUEST)
        assert response.text == "Kimi translation"
        assert response.provider == "kimi"
        assert response.input_tokens == 11

    asyncio.run(run())


def test_gemini_interactions_adapter() -> None:
    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/v1beta/interactions"
            assert request.headers["x-goog-api-key"] == "test-key"
            return httpx.Response(
                200,
                json={
                    "id": "gemini_1",
                    "model": "gemini-test",
                    "status": "completed",
                    "steps": [
                        {
                            "type": "model_output",
                            "content": [{"type": "text", "text": "Gemini translation"}],
                        }
                    ],
                    "usage": {"total_input_tokens": 12, "total_output_tokens": 6},
                },
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = GeminiProvider(api_key="test-key", client=client)
            response = await provider.generate(_REQUEST)
        assert response.text == "Gemini translation"
        assert response.provider == "gemini"
        assert response.output_tokens == 6

    asyncio.run(run())


def test_aitunnel_chat_completions_adapter() -> None:
    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/v1/chat/completions"
            return httpx.Response(
                200,
                json={
                    "id": "tunnel_1",
                    "model": "provider-model",
                    "choices": [
                        {"message": {"role": "assistant", "content": "Tunnel translation"}, "finish_reason": "stop"}
                    ],
                    "usage": {"prompt_tokens": 9, "completion_tokens": 3, "cost_rub": 0.1},
                },
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = AITunnelProvider(api_key="test-key", client=client)
            response = await provider.generate(_REQUEST)
        assert response.text == "Tunnel translation"
        assert response.provider == "aitunnel"
        assert response.request_id == "tunnel_1"

    asyncio.run(run())

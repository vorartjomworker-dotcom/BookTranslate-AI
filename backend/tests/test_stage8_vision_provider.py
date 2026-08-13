import json

import httpx
import pytest

from app.vision.providers import OpenAIVisionProvider


@pytest.mark.asyncio
async def test_openai_vision_provider_uses_responses_image_input() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/responses"
        payload = json.loads(request.content)
        assert payload["model"] == "vision-model"
        content = payload["input"][0]["content"]
        assert content[0]["type"] == "input_text"
        assert content[1]["type"] == "input_image"
        assert content[1]["image_url"].startswith("data:image/png;base64,")
        return httpx.Response(
            200,
            json={
                "id": "resp_vision",
                "model": "vision-model",
                "status": "completed",
                "output_text": '{"text":"Latency 12 us","has_text":true,"regions":[{"text":"Latency 12 us","kind":"label","bbox":[0.1,0.2,0.5,0.3]}]}',
                "usage": {"input_tokens": 20, "output_tokens": 12},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.openai.test") as client:
        provider = OpenAIVisionProvider("secret", "https://api.openai.test/v1", client=client)
        result = await provider.extract(
            image_bytes=b"png-bytes",
            media_type="image/png",
            model="vision-model",
            prompt="Extract text",
        )

    assert result.text == "Latency 12 us"
    assert result.regions[0]["kind"] == "label"
    assert result.regions[0]["bbox"] == [0.1, 0.2, 0.5, 0.3]
    assert result.input_tokens == 20
    assert result.output_tokens == 12

from __future__ import annotations

import base64
import json
from typing import Protocol

import httpx

from app.vision.schemas import VisionResult


class VisionProvider(Protocol):
    name: str

    async def extract(self, *, image_bytes: bytes, media_type: str, model: str, prompt: str) -> VisionResult: ...


class OpenAIVisionProvider:
    name = "openai"

    def __init__(self, api_key: str, base_url: str, timeout_seconds: float = 120.0, client: httpx.AsyncClient | None = None) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.client = client

    @staticmethod
    def _output_text(data: dict) -> str:
        if isinstance(data.get("output_text"), str) and data["output_text"].strip():
            return data["output_text"].strip()
        chunks: list[str] = []
        for item in data.get("output") or []:
            if item.get("type") != "message":
                continue
            for part in item.get("content") or []:
                if part.get("type") == "output_text" and isinstance(part.get("text"), str):
                    chunks.append(part["text"])
        return "".join(chunks).strip()

    @staticmethod
    def _parse_payload(text: str) -> tuple[str, list[dict]]:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()
        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError:
            return cleaned, ([{"text": cleaned, "kind": "unknown", "bbox": None}] if cleaned else [])
        text_value = str(payload.get("text") or "").strip()
        regions = payload.get("regions") if isinstance(payload.get("regions"), list) else []
        normalized: list[dict] = []
        for region in regions:
            if not isinstance(region, dict):
                continue
            region_text = str(region.get("text") or "").strip()
            if not region_text:
                continue
            bbox = region.get("bbox")
            if not (isinstance(bbox, list) and len(bbox) == 4):
                bbox = None
            normalized.append({"text": region_text, "kind": str(region.get("kind") or "other"), "bbox": bbox})
        if not text_value and normalized:
            text_value = "\n".join(item["text"] for item in normalized)
        return text_value, normalized

    async def extract(self, *, image_bytes: bytes, media_type: str, model: str, prompt: str) -> VisionResult:
        data_url = f"data:{media_type or 'image/png'};base64,{base64.b64encode(image_bytes).decode('ascii')}"
        payload = {
            "model": model,
            "input": [
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt},
                        {"type": "input_image", "image_url": data_url, "detail": "high"},
                    ],
                }
            ],
        }
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        if self.client is not None:
            response = await self.client.post(f"{self.base_url}/responses", headers=headers, json=payload)
            response.raise_for_status()
            body = response.json()
        else:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(f"{self.base_url}/responses", headers=headers, json=payload)
                response.raise_for_status()
                body = response.json()
        output = self._output_text(body)
        text, regions = self._parse_payload(output)
        usage = body.get("usage") or {}
        return VisionResult(
            text=text,
            regions=regions,
            raw={"status": body.get("status"), "output_text": output},
            provider=self.name,
            model=str(body.get("model") or model),
            request_id=body.get("id"),
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
        )

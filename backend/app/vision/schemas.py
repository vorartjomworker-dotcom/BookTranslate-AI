from dataclasses import dataclass, field


@dataclass(slots=True)
class VisionResult:
    text: str
    regions: list[dict] = field(default_factory=list)
    raw: dict = field(default_factory=dict)
    provider: str = "openai"
    model: str = ""
    request_id: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None

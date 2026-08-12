from dataclasses import dataclass, field


@dataclass(slots=True)
class ModelRequest:
    model: str
    system_prompt: str
    user_prompt: str
    temperature: float | None = 0.2
    max_output_tokens: int | None = 4000
    metadata: dict = field(default_factory=dict)


@dataclass(slots=True)
class ModelResponse:
    text: str
    provider: str
    model: str
    request_id: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    metadata: dict = field(default_factory=dict)

from abc import ABC, abstractmethod

from app.ai.schemas import ModelRequest, ModelResponse


class ModelProvider(ABC):
    name: str

    @abstractmethod
    async def generate(self, request: ModelRequest) -> ModelResponse:
        raise NotImplementedError

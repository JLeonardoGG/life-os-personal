from __future__ import annotations

from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field

from lifeos.config import Settings


class AIResult(BaseModel):
    status: Literal["disabled", "ok", "unavailable", "error"]
    text: str = ""
    model: str = ""
    details: dict[str, Any] = Field(default_factory=dict)


class AIService:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def generate(self, prompt: str, context: str = "") -> AIResult:
        if not self.settings.ai_enabled:
            return AIResult(
                status="disabled",
                model=self.settings.ollama_model,
                details={"reason": "LIFE_OS_AI_ENABLED is false"},
            )
        combined_prompt = f"{context.strip()}\n\n{prompt.strip()}".strip()
        try:
            async with httpx.AsyncClient(timeout=self.settings.ollama_timeout_seconds) as client:
                response = await client.post(
                    self.settings.ollama_url,
                    json={
                        "model": self.settings.ollama_model,
                        "prompt": combined_prompt,
                        "stream": False,
                    },
                )
                response.raise_for_status()
                payload = response.json()
                return AIResult(
                    status="ok",
                    text=str(payload.get("response") or ""),
                    model=str(payload.get("model") or self.settings.ollama_model),
                    details={"done": payload.get("done", True)},
                )
        except httpx.ConnectError:
            return AIResult(
                status="unavailable",
                model=self.settings.ollama_model,
                details={"reason": "Ollama is not reachable"},
            )
        except (httpx.HTTPError, ValueError) as exc:
            return AIResult(
                status="error",
                model=self.settings.ollama_model,
                details={"reason": type(exc).__name__},
            )

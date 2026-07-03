"""Route model turns between primary and vision-capable providers."""

from __future__ import annotations

from typing import Any

from app.agent.llm.provider_adapter import ModelResponse, ProviderAdapter


class ProviderRouter:
    """Select the best provider for the current turn based on message content."""

    def __init__(
        self,
        *,
        primary: ProviderAdapter,
        vision: ProviderAdapter | None = None,
    ) -> None:
        self._primary = primary
        self._vision = vision

    @property
    def enabled(self) -> bool:
        return self._primary.enabled or bool(self._vision and self._vision.enabled)

    async def complete(
        self,
        *,
        instructions: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        runtime_hints: dict[str, Any] | None = None,
    ) -> ModelResponse:
        has_images = self._contains_images(messages)
        adapter = self._vision if has_images and self._vision and self._vision.enabled else self._primary
        response = await adapter.complete(
            instructions=instructions,
            messages=messages,
            tools=tools,
            runtime_hints=runtime_hints,
        )
        if has_images and adapter is self._primary and self._looks_like_unsupported_image_error(response.text):
            return ModelResponse(
                text=(
                    "我收到了图片，但当前配置的模型不支持图片识别。"
                    "请配置支持视觉输入的模型后再试，例如设置 "
                    "VISION_LLM_MODEL，并按需补充 VISION_LLM_BASE_URL 与 VISION_LLM_API_KEY。"
                ),
                tool_calls=[],
                reasoning_items=[],
            )
        return response

    def _contains_images(self, messages: list[dict[str, Any]]) -> bool:
        for message in messages:
            if not isinstance(message, dict):
                continue
            content = message.get("content")
            if not isinstance(content, list):
                continue
            for item in content:
                if not isinstance(item, dict):
                    continue
                if str(item.get("type") or "").strip() == "image_url":
                    return True
        return False

    def _looks_like_unsupported_image_error(self, text: str | None) -> bool:
        if not isinstance(text, str):
            return False
        normalized = text.lower()
        return (
            "unknown variant image_url" in normalized
            or "expected text" in normalized
            or "does not support images" in normalized
            or "vision" in normalized and "not support" in normalized
        )

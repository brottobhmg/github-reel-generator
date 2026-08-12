"""LLM provider clients and resilient chat completion.

The pipeline tries a list of models on Nvidia NIM first, then falls back to
OpenRouter, so a single provider outage does not stop the whole job.
"""

from __future__ import annotations

from openai import AsyncOpenAI

from config import settings
from logging_config import get_logger

logger = get_logger(__name__)


def _build_clients() -> tuple[AsyncOpenAI | None, AsyncOpenAI | None, AsyncOpenAI | None]:
    """Build the provider clients from settings.

    Returns:
        A tuple ``(groq, nim, openrouter)``. Clients whose API key is missing
        are returned as ``None``.
    """
    groq = (
        AsyncOpenAI(
            api_key=settings.groq_api_key,
            base_url="https://api.groq.com/openai/v1",
        )
        if settings.groq_api_key
        else None
    )
    nim = (
        AsyncOpenAI(
            api_key=settings.nvidia_nim_api_key,
            base_url="https://integrate.api.nvidia.com/v1",
            timeout=settings.nim_timeout,
            # Un solo retry: fallire presto e passare al modello successivo
            # è meglio che aspettare i 3 retry di default dell'SDK.
            max_retries=1,
        )
        if settings.nvidia_nim_api_key
        else None
    )
    openrouter = (
        AsyncOpenAI(
            api_key=settings.openrouter_api_key,
            base_url="https://openrouter.ai/api/v1",
            timeout=settings.openrouter_timeout,
            max_retries=1,
        )
        if settings.openrouter_api_key
        else None
    )
    return groq, nim, openrouter


groq_client, nim_client, openrouter_client = _build_clients()


async def safe_chat_completion(prompt: str, temperature: float = 0.7) -> str:
    """Send a chat completion, trying NIM models then OpenRouter models.

    Args:
        prompt: The user prompt to send.
        temperature: Sampling temperature.

    Returns:
        The trimmed text content of the first successful response.

    Raises:
        RuntimeError: If every provider/model attempt fails.
    """
    last_error: Exception | None = None

    if nim_client is not None:
        for model in settings.nim_models:
            try:
                logger.info("Nvidia NIM: trying model %s", model)
                response = await nim_client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=temperature,
                    timeout=settings.nim_timeout,
                )
                content = response.choices[0].message.content
                if content is None:
                    raise ValueError(
                        f"Nvidia NIM ({model}) returned empty/filtered content."
                    )
                logger.info("Nvidia NIM (%s) succeeded.", model)
                return content.strip()
            except Exception as exc:  # noqa: BLE001 - provider fallback
                logger.warning("Nvidia NIM (%s) failed: %s", model, exc)
                last_error = exc

    if openrouter_client is not None:
        for model in settings.openrouter_models:
            try:
                logger.info("OpenRouter: trying model %s", model)
                response = await openrouter_client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=temperature,
                    timeout=settings.openrouter_timeout,
                )
                content = response.choices[0].message.content
                if content is None:
                    raise ValueError(
                        f"OpenRouter ({model}) returned empty/filtered content."
                    )
                logger.info("OpenRouter (%s) succeeded.", model)
                return content.strip()
            except Exception as exc:  # noqa: BLE001 - provider fallback
                logger.warning("OpenRouter (%s) failed: %s", model, exc)
                last_error = exc

    logger.error("All LLM provider attempts failed.")
    raise RuntimeError(f"All LLM providers failed: {last_error}")

import logging
import random
import time
from abc import ABC, abstractmethod

from google.genai import Client, errors, types
from PIL import Image
from pydantic import BaseModel, ValidationError

from backend.app.core.exceptions import (
    ExtractionFailedError,
    LlmRateLimitedError,
    LlmTimeoutError,
)

logger = logging.getLogger("app.llm")

MAX_RATE_LIMIT_RETRIES = 4
MAX_BACKOFF_SECONDS = 30.0


class LLMProvider(ABC):
    @abstractmethod
    def generate_structured(self, prompt: str, image: Image.Image, schema: type[BaseModel]) -> BaseModel: ...


def _backoff_seconds(attempt: int, retry_after: float | None) -> float:
    if retry_after is not None:
        return retry_after
    base = min(2**attempt, MAX_BACKOFF_SECONDS)
    return base + random.uniform(0, base * 0.25)


def _retry_after_seconds(exc: errors.APIError) -> float | None:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if not headers:
        return None
    value = headers.get("Retry-After")
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None


class GeminiLLMProvider(LLMProvider):
    """Gemini vision LLM behind the LLMProvider interface. The free tier has a low
    per-minute request cap, so a 429/503 is expected under load, not exceptional --
    we back off with jitter and retry a bounded number of times before surfacing a
    clean LLM_RATE_LIMITED error instead of hanging.
    """

    def __init__(self, api_key: str, model: str):
        # The SDK retries 429/5xx internally by default (5 attempts, up to 60s delay
        # each) *underneath* our own retry loop below, which turns "capped retries"
        # into an effectively uncapped, multi-minute hang under sustained rate
        # limiting. Disabling it here makes our backoff the only retry layer.
        http_options = types.HttpOptions(
            timeout=30_000, retry_options=types.HttpRetryOptions(attempts=1)
        )
        self.client = Client(api_key=api_key, http_options=http_options)
        self.model = model

    def generate_structured(self, prompt: str, image: Image.Image, schema: type[BaseModel]) -> BaseModel:
        raw_text = self._call_with_retry(prompt, image, schema)
        try:
            return schema.model_validate_json(raw_text)
        except ValidationError as exc:
            logger.warning("llm_schema_validation_failed_retrying", extra={"error": str(exc)})
            correction_prompt = (
                f"{prompt}\n\nYour previous response failed schema validation with this "
                f"error:\n{exc}\n\nReturn corrected JSON that matches the schema exactly."
            )
            raw_text = self._call_with_retry(correction_prompt, image, schema)
            try:
                return schema.model_validate_json(raw_text)
            except ValidationError as exc2:
                raise ExtractionFailedError(f"LLM response failed schema validation twice: {exc2}") from exc2

    def _call_with_retry(self, prompt: str, image: Image.Image, schema: type[BaseModel]) -> str:
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=schema,
            temperature=0.0,
            max_output_tokens=8192,
        )
        last_exc: Exception | None = None
        for attempt in range(MAX_RATE_LIMIT_RETRIES):
            try:
                start = time.monotonic()
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=[image, prompt],
                    config=config,
                )
                logger.info(
                    "llm_call_completed",
                    extra={"model": self.model, "duration_ms": round((time.monotonic() - start) * 1000, 2)},
                )
                if not response.text:
                    raise ExtractionFailedError("LLM returned an empty response.")
                return response.text
            except errors.APIError as exc:
                last_exc = exc
                if exc.code in (429, 503):
                    delay = _backoff_seconds(attempt, _retry_after_seconds(exc))
                    logger.warning(
                        "llm_rate_limited_backoff",
                        extra={"attempt": attempt, "delay_seconds": delay, "code": exc.code},
                    )
                    time.sleep(delay)
                    continue
                raise ExtractionFailedError(f"Gemini API error: {exc}") from exc
            except TimeoutError as exc:
                raise LlmTimeoutError(f"Gemini request timed out: {exc}") from exc
        raise LlmRateLimitedError(
            f"Gemini rate limit exceeded after {MAX_RATE_LIMIT_RETRIES} retries: {last_exc}"
        )


def get_llm_provider(provider_name: str, api_key: str, model: str) -> LLMProvider:
    if provider_name == "gemini":
        return GeminiLLMProvider(api_key=api_key, model=model)
    raise ValueError(f"Unsupported LLM_PROVIDER: {provider_name}")

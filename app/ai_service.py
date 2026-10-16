"""AI integration. Uses any OpenAI-compatible endpoint (Groq by default).

The API key stays server-side only.
"""
from __future__ import annotations

import logging
from typing import Iterable

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
    BadRequestError,
    RateLimitError,
)

from .config import get_settings

log = logging.getLogger("not.ai")

_LANG_INSTRUCTIONS = {
    "auto": "Respond in the same language the user wrote in.",
    "en": "Respond in English.",
    "ur": "Respond in Urdu (اردو script).",
    "roman-ur": "Respond in Roman Urdu (Urdu written in Latin letters).",
    "hi": "Respond in Hindi (Devanagari script).",
}


class AIServiceError(Exception):
    """Raised when the AI call fails in a way the caller should surface."""

    def __init__(self, message: str, *, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


def _client() -> AsyncOpenAI:
    settings = get_settings()
    if not settings.api_key_configured:
        raise AIServiceError(
            "No AI API key is configured on the server. "
            "Add GROQ_API_KEY (or OPENAI_API_KEY) to your .env file "
            "(local) or your hosting environment variables.",
            status_code=503,
        )
    return AsyncOpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        timeout=settings.openai_timeout,
        max_retries=1,
    )


def _build_messages(
    history: Iterable[dict],
    user_message: str,
    language: str,
) -> list[dict]:
    settings = get_settings()
    system = settings.system_prompt
    lang_note = _LANG_INSTRUCTIONS.get(language, _LANG_INSTRUCTIONS["auto"])
    system = f"{system}\n\nLanguage instruction: {lang_note}"

    messages: list[dict] = [{"role": "system", "content": system}]
    for m in history:
        role = m.get("role")
        content = m.get("content", "")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user_message})
    return messages


async def generate_reply(
    history: list[dict],
    user_message: str,
    language: str = "auto",
) -> tuple[str, str]:
    """Return (reply_text, model_name). Raises AIServiceError on failure."""
    settings = get_settings()
    client = _client()

    trimmed_history = history[-settings.max_history_messages :]
    payload = _build_messages(trimmed_history, user_message, language)

    try:
        resp = await client.chat.completions.create(
            model=settings.openai_model,
            messages=payload,  # type: ignore[arg-type]
            temperature=0.7,
        )
    except AuthenticationError as exc:
        log.warning("AI auth error: %s", exc)
        raise AIServiceError(
            "The server's AI API key was rejected. Check that it is valid "
            "and has not been revoked.",
            status_code=502,
        ) from exc

    except RateLimitError as exc:
        log.warning("AI rate limit: %s", exc)
        # Distinguish "no money" from "too many requests" — different UX.
        body = getattr(exc, "body", None) or {}
        err_type = ""
        err_msg = ""
        if isinstance(body, dict):
            err = body.get("error") or {}
            err_type = str(err.get("type", ""))
            err_msg = str(err.get("message", ""))

        low = (err_type + " " + err_msg).lower()
        if (
            "insufficient_quota" in low
            or "credit_balance_exhausted" in low
            or "exceeded your current quota" in low
            or "no credits remaining" in low
        ):
            raise AIServiceError(
                "The AI provider says this account has no credits remaining. "
                "Add credits to your provider's billing page and try again.",
                status_code=402,
            ) from exc

        # Groq returns 429 with a JSON body describing which limit was hit.
        if "rate_limit_exceeded" in low or "requests" in low or "tokens" in low:
            raise AIServiceError(
                "You've hit the provider's rate limit for this model. "
                "Wait a few seconds and try again, or switch to a lighter model "
                "(e.g. llama-3.1-8b-instant on Groq).",
                status_code=429,
            ) from exc

        raise AIServiceError(
            "The AI service is busy right now. Wait a few seconds and try again.",
            status_code=429,
        ) from exc

    except APITimeoutError as exc:
        log.warning("AI timeout: %s", exc)
        raise AIServiceError(
            "The AI service timed out. Please try again.", status_code=504
        ) from exc

    except APIConnectionError as exc:
        log.warning("AI connection error: %s", exc)
        raise AIServiceError(
            "Could not reach the AI service. Check the server's network connection "
            f"and the configured base URL ({settings.openai_base_url}).",
            status_code=502,
        ) from exc

    except BadRequestError as exc:
        log.warning("AI bad request: %s", exc)
        raise AIServiceError(
            "The AI service rejected the request. The model name may be wrong "
            f"for this provider (currently: {settings.openai_model}).",
            status_code=400,
        ) from exc

    except APIStatusError as exc:
        log.warning("AI API status error: %s", exc)
        raise AIServiceError(
            "The AI service returned an unexpected error.", status_code=502
        ) from exc

    if not resp.choices:
        raise AIServiceError("The AI service returned an empty response.")

    reply = (resp.choices[0].message.content or "").strip()
    if not reply:
        raise AIServiceError("The AI service returned an empty reply.")
    return reply, settings.openai_model
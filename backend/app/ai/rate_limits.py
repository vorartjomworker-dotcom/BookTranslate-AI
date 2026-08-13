from __future__ import annotations

import email.utils
import re
from datetime import datetime, timezone
from typing import Mapping

_DURATION_RE = re.compile(r"(?:(\d+(?:\.\d+)?)h)?(?:(\d+(?:\.\d+)?)m)?(?:(\d+(?:\.\d+)?)s)?(?:(\d+(?:\.\d+)?)ms)?$")


def _int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(float(value.strip()))
    except (TypeError, ValueError):
        return None


def _duration_seconds(value: str | None) -> float | None:
    if not value:
        return None
    raw = value.strip().lower()
    try:
        return max(0.0, float(raw))
    except ValueError:
        pass
    match = _DURATION_RE.fullmatch(raw)
    if match and any(part is not None for part in match.groups()):
        hours, minutes, seconds, milliseconds = (float(part or 0) for part in match.groups())
        return max(0.0, hours * 3600 + minutes * 60 + seconds + milliseconds / 1000)
    try:
        parsed = email.utils.parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return max(0.0, (parsed - datetime.now(timezone.utc)).total_seconds())
    except (TypeError, ValueError, OverflowError):
        return None


def normalize_rate_limit_headers(headers: Mapping[str, str]) -> dict:
    lowered = {str(key).lower(): str(value) for key, value in headers.items()}
    request_id = lowered.get("x-request-id") or lowered.get("request-id") or lowered.get("x-goog-request-id")
    retry_after = _duration_seconds(lowered.get("retry-after"))
    reset_requests = _duration_seconds(
        lowered.get("x-ratelimit-reset-requests")
        or lowered.get("ratelimit-reset")
        or lowered.get("x-rate-limit-reset")
    )
    reset_tokens = _duration_seconds(lowered.get("x-ratelimit-reset-tokens"))
    payload = {
        "request_id": request_id,
        "limit_requests": _int(lowered.get("x-ratelimit-limit-requests") or lowered.get("ratelimit-limit")),
        "remaining_requests": _int(lowered.get("x-ratelimit-remaining-requests") or lowered.get("ratelimit-remaining")),
        "reset_requests_seconds": reset_requests,
        "limit_tokens": _int(lowered.get("x-ratelimit-limit-tokens")),
        "remaining_tokens": _int(lowered.get("x-ratelimit-remaining-tokens")),
        "reset_tokens_seconds": reset_tokens,
        "retry_after_seconds": retry_after,
    }
    return {key: value for key, value in payload.items() if value is not None}

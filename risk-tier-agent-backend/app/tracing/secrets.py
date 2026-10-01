from __future__ import annotations

from typing import Any

# Substring match (case-insensitive, "-"/" " normalized to "_") against dict
# keys — deliberately broad so "jira_api_token", "Authorization",
# "OPENAI_API_KEY", "client_secret" etc. are all caught by one check.
#
# "token" is NOT in this substring list on purpose: this app's own trace
# files legitimately carry real fields named "tokens"/"prompt_tokens"/
# "completion_tokens"/"total_tokens" (requirement: capture real LLM token
# usage, never estimate) — a bare substring match on "token" would redact
# those too. "token" is instead matched as a whole "_"-delimited segment
# below, which still catches "token", "access_token", "id_token",
# "auth_token", "csrf_token", etc. but not the plural "tokens" forms.
_SENSITIVE_KEY_MARKERS = (
    "api_key",
    "apikey",
    "authorization",
    "password",
    "secret",
    "credential",
)

REDACTED = "***REDACTED***"


def _is_sensitive_key(key: Any) -> bool:
    normalized = str(key).strip().lower().replace("-", "_").replace(" ", "_")
    if any(marker in normalized for marker in _SENSITIVE_KEY_MARKERS):
        return True
    return "token" in normalized.split("_")


def mask_secrets(value: Any) -> Any:
    """
    Recursively redact dict values whose key looks like a credential.

    Applied centrally in app/tracing/writer.py at the point every trace file
    is serialized, so no call site anywhere in the tracer has to remember to
    mask anything itself.
    """
    if isinstance(value, dict):
        return {
            key: (REDACTED if _is_sensitive_key(key) else mask_secrets(val))
            for key, val in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [mask_secrets(item) for item in value]
    return value

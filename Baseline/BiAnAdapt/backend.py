"""Minimal, loopback-only OpenAI-compatible HTTP client (standard library)."""

from __future__ import annotations

import ipaddress
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


class BackendFailure(RuntimeError):
    """A sanitized failure; exception messages never contain credentials."""


def validate_local_url(base_url: str) -> str:
    parsed = urllib.parse.urlsplit(base_url)
    if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
        raise ValueError("backend must be a loopback HTTP(S) URL without credentials")
    if parsed.query or parsed.fragment:
        raise ValueError("backend URL cannot contain a query or fragment")
    try:
        is_local = ipaddress.ip_address(parsed.hostname or "").is_loopback
    except ValueError:
        is_local = parsed.hostname == "localhost"
    if not is_local:
        raise ValueError("only loopback model endpoints are allowed; use an explicit local tunnel")
    return base_url.rstrip("/")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise BackendFailure("HTTP redirect refused for local model endpoint")


class LocalOpenAITransport:
    """Callable transport. No proxy, remote redirect, SDK, or model fallback."""

    def __init__(self, base_url: str, api_key: str | None = None):
        self.base_url = validate_local_url(base_url)
        self._api_key = api_key
        self._opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}), _NoRedirect()
        )

    def __call__(self, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = "Bearer " + self._api_key
        req = urllib.request.Request(
            self.base_url + "/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with self._opener.open(req, timeout=timeout) as response:
                data = response.read(16 * 1024 * 1024 + 1)
            if len(data) > 16 * 1024 * 1024:
                raise BackendFailure("backend response exceeds 16 MiB")
            value = json.loads(data)
            if not isinstance(value, dict):
                raise BackendFailure("backend returned a non-object response")
            return value
        except urllib.error.HTTPError as exc:
            raise BackendFailure(f"local backend HTTP {exc.code}") from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise BackendFailure("local model backend unavailable or timed out") from None
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise BackendFailure("local backend returned invalid JSON") from None

"""Refreshable reader for the Marketaux token: one exact SecureString, nothing else.

This is the only SDK call in the service process (see the Service Decoupling amendment in
spec 001). The parameter name comes from the environment; the value is cached for a few
minutes, and a failed refresh keeps the last good value. Values and raw provider errors are
never logged.
"""
from __future__ import annotations

import re
import time
from collections.abc import Callable, Mapping
from typing import Any

_NAME = re.compile(r'/mcp/(development|test|production)/service/marketaux-api-token')
_MAX_LENGTH = 512
DEFAULT_TTL_SECONDS = 300.0


def parameter_name_from(environment: Mapping[str, str]) -> str:
    """Return the configured parameter name, or '' when the token is supplied another way."""
    name = environment.get('MARKETAUX_API_TOKEN_PARAMETER', '')
    if name and not _NAME.fullmatch(name):
        raise ValueError('Invalid MARKETAUX_API_TOKEN_PARAMETER')
    return name


class MarketauxToken:
    def __init__(self, name: str, client: Any = None, ttl_seconds: float = DEFAULT_TTL_SECONDS,
                 clock: Callable[[], float] = time.monotonic,
                 emit: Callable[..., None] | None = None):
        if not _NAME.fullmatch(name):
            raise ValueError('Invalid MARKETAUX_API_TOKEN_PARAMETER')
        self._name = name
        self._client = client
        self._ttl = ttl_seconds
        self._clock = clock
        self._emit = emit
        self._value = ''
        self._loaded_at: float | None = None

    def _ssm(self) -> Any:
        if self._client is None:
            import boto3  # the one permitted SDK import in the service (pinned in pyproject)
            self._client = boto3.client('ssm')
        return self._client

    def value(self) -> str:
        """Return the cached token, refreshing it when the cache is older than the TTL."""
        now = self._clock()
        if self._loaded_at is not None and now - self._loaded_at < self._ttl:
            return self._value
        self._loaded_at = now
        try:
            fetched = self._ssm().get_parameter(Name=self._name, WithDecryption=True)['Parameter']['Value']
            if not isinstance(fetched, str) or not fetched or len(fetched) > _MAX_LENGTH or '\x00' in fetched:
                raise ValueError('invalid_value')
            self._value = fetched
        except Exception:  # sanitized: the class name only, never the value or the provider message
            if self._emit is not None:
                self._emit('WARNING', operation='marketaux.token', outcome='refresh_failed',
                           error_class=_error_class())
        return self._value


def _error_class() -> str:
    import sys
    exc = sys.exc_info()[1]
    return type(exc).__name__ if exc is not None else 'unknown'

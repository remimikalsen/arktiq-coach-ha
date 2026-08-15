"""Async client for the ArktIQ Coach read-only integration API (v1)."""
from __future__ import annotations

import asyncio
from typing import Any

import aiohttp

REQUEST_TIMEOUT = 30


class ArktiqApiError(Exception):
    """Base error talking to the ArktIQ Coach API."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class ArktiqAuthError(ArktiqApiError):
    """The API key was rejected (revoked or invalid)."""


class ArktiqRateLimitError(ArktiqApiError):
    """The API rate limit was hit."""

    def __init__(self, message: str, retry_after: int | None = None) -> None:
        super().__init__(message, status=429)
        self.retry_after = retry_after


class ArktiqCoachClient:
    """Thin wrapper around the /api/integration/v1 surface."""

    def __init__(
        self, session: aiohttp.ClientSession, base_url: str, api_key: str
    ) -> None:
        self._session = session
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key

    async def _get(self, path: str) -> Any:
        url = f"{self._base_url}/api/integration/v1/{path}"
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                response = await self._session.get(
                    url, headers={"X-Api-Key": self._api_key}
                )
        except TimeoutError as err:
            raise ArktiqApiError(f"Timeout requesting {url}") from err
        except aiohttp.ClientError as err:
            raise ArktiqApiError(f"Error requesting {url}: {err}") from err

        if response.status in (401, 403):
            raise ArktiqAuthError(
                f"API key rejected (HTTP {response.status})", status=response.status
            )
        if response.status == 429:
            retry_header = response.headers.get("Retry-After", "")
            retry_after = int(retry_header) if retry_header.isdigit() else None
            raise ArktiqRateLimitError("Rate limited", retry_after=retry_after)
        if response.status >= 400:
            raise ArktiqApiError(
                f"HTTP {response.status} from {url}", status=response.status
            )
        return await response.json()

    async def get_summary(self) -> dict[str, Any]:
        """Active goals with level, streak and badge count."""
        return await self._get("summary")

    async def get_today(self) -> dict[str, Any]:
        """Today's task list in the account's timezone."""
        return await self._get("today")

    async def get_badges(self) -> list[dict[str, Any]]:
        """Earned badges, newest first."""
        return await self._get("badges")

    async def get_metric_latest(self, key: str) -> dict[str, Any]:
        """Latest logged value of a global metric."""
        return await self._get(f"metrics/{key}/latest")

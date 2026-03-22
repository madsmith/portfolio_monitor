"""Shared HTTP helpers and API client for CLI commands.

APIClient — bound to a base URL and optional Bearer token:
  client.get(path, *, params)   — exits on ConnectError or 401
  client.put(path, *, json)     — exits on ConnectError or 401
  client.post(path, *, json)    — exits on ConnectError
  client.get_json(path)         — additionally exits on non-2xx, returns parsed JSON
  client.put_json(path, *, json) — additionally exits on non-2xx
  client.try_get_json(path)     — returns None on any failure instead of exiting

make_client(args, *, require_token) — construct an APIClient from parsed CLI args
"""
import argparse
import sys
from typing import Any

import httpx

__all__ = ["APIClient", "make_client"]


class APIClient:
    """HTTP client bound to a base URL and optional Bearer token."""

    def __init__(self, base_url: str, token: str | None = None) -> None:
        self._base: str = base_url.rstrip("/")
        self._headers: dict[str, str] = {}
        if token:
            self._headers["Authorization"] = f"Bearer {token}"

    # ------------------------------------------------------------------
    # Low-level — caller inspects status codes beyond ConnectError / 401
    # ------------------------------------------------------------------

    def get(self, path: str, *, params: dict[str, str] | None = None) -> httpx.Response:
        """GET request. Exits on connection error or 401."""
        return _request("GET", self._base + path, headers=self._headers, params=params)

    def put(self, path: str, *, json: Any = None) -> httpx.Response:
        """PUT request. Exits on connection error or 401."""
        return _request("PUT", self._base + path, headers=self._headers, json=json)

    def post(self, path: str, *, json: Any = None) -> httpx.Response:
        """POST request. Exits on connection error."""
        return _request("POST", self._base + path, headers=self._headers, json=json, check_auth=False)

    def delete(self, path: str) -> httpx.Response:
        """DELETE request. Exits on connection error or 401."""
        return _request("DELETE", self._base + path, headers=self._headers)

    # ------------------------------------------------------------------
    # High-level — additionally exit on any non-2xx response
    # ------------------------------------------------------------------

    def get_json(self, path: str) -> Any:
        """GET request. Exits on connection error, 401, or non-2xx. Returns parsed JSON."""
        response = self.get(path)
        _require_success(response)
        return response.json()

    def put_json(self, path: str, *, json: Any = None) -> None:
        """PUT request. Exits on connection error, 401, or non-2xx."""
        response = self.put(path, json=json)
        _require_success(response)



def make_client(args: argparse.Namespace, *, require_token: bool = True) -> APIClient:
    """Construct an APIClient from parsed CLI args.

    If require_token is True (the default) and no token is present, prints an
    error and exits.
    """
    if require_token and not args.token:
        print("error: --token is required", file=sys.stderr)
        sys.exit(1)
    return APIClient(args.url, args.token)


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _request(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None,
    params: dict[str, str] | None = None,
    json: Any = None,
    check_auth: bool = True,
) -> httpx.Response:
    try:
        response = httpx.request(method, url, headers=headers, params=params, json=json)
    except httpx.ConnectError:
        print(f"error: could not connect to {url}", file=sys.stderr)
        sys.exit(1)
    if check_auth and response.status_code == 401:
        print("error: unauthorized — check your token", file=sys.stderr)
        sys.exit(1)
    return response


def _require_success(response: httpx.Response) -> None:
    if not response.is_success:
        print(f"error: server returned {response.status_code}", file=sys.stderr)
        sys.exit(1)

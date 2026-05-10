"""Small JSON HTTP helper used by the fetch scripts.

The original project used ``requests``.  This helper keeps the rebuilt project
usable in a fresh Python environment by relying only on the standard library.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Optional
from http.cookiejar import CookieJar
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen


DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/plain, */*",
}


class HttpClientError(RuntimeError):
    """Raised when an HTTP request cannot be completed or decoded."""


@dataclass(frozen=True)
class JsonResponse:
    url: str
    status: int
    content_type: str
    data: Any


@dataclass(frozen=True)
class TextResponse:
    url: str
    status: int
    content_type: str
    text: str


@dataclass(frozen=True)
class BytesResponse:
    url: str
    status: int
    content_type: str
    data: bytes


def fetch_json(
    url: str,
    params: Optional[dict[str, Any]] = None,
    headers: Optional[dict[str, str]] = None,
    timeout: int = 20,
) -> JsonResponse:
    """Fetch a URL and parse the response body as JSON."""

    clean_params = {}
    for key, value in (params or {}).items():
        if value is not None and value != "":
            clean_params[key] = value

    if clean_params:
        separator = "&" if "?" in url else "?"
        url = f"{url}{separator}{urlencode(clean_params)}"

    merged_headers = dict(DEFAULT_HEADERS)
    if headers:
        merged_headers.update(headers)

    request = Request(url, headers=merged_headers)
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8-sig")
            content_type = response.headers.get("Content-Type", "")
            status = int(getattr(response, "status", 200))
    except HTTPError as exc:
        try:
            body = exc.read().decode("utf-8-sig", errors="replace")
        except Exception:
            body = ""
        raise HttpClientError(f"HTTP {exc.code} for {url}: {body[:300]}") from exc
    except URLError as exc:
        raise HttpClientError(f"Request failed for {url}: {exc.reason}") from exc

    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise HttpClientError(f"Response is not valid JSON for {url}: {body[:300]}") from exc

    return JsonResponse(url=url, status=status, content_type=content_type, data=data)


def post_json(
    url: str,
    payload: Any,
    headers: Optional[dict[str, str]] = None,
    timeout: int = 20,
) -> JsonResponse:
    """POST a JSON payload and parse the JSON response."""

    merged_headers = dict(DEFAULT_HEADERS)
    merged_headers["Content-Type"] = "application/json"
    if headers:
        merged_headers.update(headers)

    body = json.dumps(payload).encode("utf-8")
    request = Request(url, data=body, headers=merged_headers, method="POST")
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8-sig")
            content_type = response.headers.get("Content-Type", "")
            status = int(getattr(response, "status", 200))
    except HTTPError as exc:
        try:
            raw = exc.read().decode("utf-8-sig", errors="replace")
        except Exception:
            raw = ""
        raise HttpClientError(f"HTTP {exc.code} for {url}: {raw[:300]}") from exc
    except URLError as exc:
        raise HttpClientError(f"Request failed for {url}: {exc.reason}") from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HttpClientError(f"Response is not valid JSON for {url}: {raw[:300]}") from exc

    return JsonResponse(url=url, status=status, content_type=content_type, data=data)


def fetch_text(
    url: str,
    headers: Optional[dict[str, str]] = None,
    timeout: int = 20,
    use_cookies: bool = False,
) -> TextResponse:
    """Fetch text/HTML content."""

    merged_headers = dict(DEFAULT_HEADERS)
    if headers:
        merged_headers.update(headers)

    request = Request(url, headers=merged_headers)
    opener = build_opener(HTTPCookieProcessor(CookieJar())) if use_cookies else None
    try:
        response_obj = opener.open(request, timeout=timeout) if opener else urlopen(request, timeout=timeout)
        with response_obj as response:
            raw = response.read().decode("utf-8-sig", errors="replace")
            content_type = response.headers.get("Content-Type", "")
            status = int(getattr(response, "status", 200))
            final_url = response.geturl()
    except HTTPError as exc:
        try:
            raw = exc.read().decode("utf-8-sig", errors="replace")
        except Exception:
            raw = ""
        raise HttpClientError(f"HTTP {exc.code} for {url}: {raw[:300]}") from exc
    except URLError as exc:
        raise HttpClientError(f"Request failed for {url}: {exc.reason}") from exc

    return TextResponse(url=final_url, status=status, content_type=content_type, text=raw)


def fetch_bytes(
    url: str,
    headers: Optional[dict[str, str]] = None,
    timeout: int = 20,
    use_cookies: bool = False,
) -> BytesResponse:
    """Fetch binary content."""

    merged_headers = dict(DEFAULT_HEADERS)
    if headers:
        merged_headers.update(headers)

    request = Request(url, headers=merged_headers)
    opener = build_opener(HTTPCookieProcessor(CookieJar())) if use_cookies else None
    try:
        response_obj = opener.open(request, timeout=timeout) if opener else urlopen(request, timeout=timeout)
        with response_obj as response:
            raw = response.read()
            content_type = response.headers.get("Content-Type", "")
            status = int(getattr(response, "status", 200))
            final_url = response.geturl()
    except HTTPError as exc:
        try:
            raw = exc.read()
        except Exception:
            raw = b""
        preview = raw[:300].decode("utf-8-sig", errors="replace")
        raise HttpClientError(f"HTTP {exc.code} for {url}: {preview}") from exc
    except URLError as exc:
        raise HttpClientError(f"Request failed for {url}: {exc.reason}") from exc

    return BytesResponse(url=final_url, status=status, content_type=content_type, data=raw)

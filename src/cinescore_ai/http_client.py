from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl
from urllib.request import Request, urlopen


@dataclass(slots=True)
class SimpleHTTPResponse:
    status_code: int
    headers: dict[str, str]
    content: bytes

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")

    def json(self) -> Any:
        return json.loads(self.text)


class UrllibSession:
    def request(self, method: str, url: str, **kwargs: Any) -> SimpleHTTPResponse:
        headers = {str(key): str(value) for key, value in dict(kwargs.get("headers") or {}).items()}
        params = kwargs.get("params")
        timeout = float(kwargs.get("timeout", 30) or 30)
        request_url = _append_query_params(url, params)
        body = _build_request_body(kwargs, headers)

        request = Request(
            request_url,
            data=body,
            headers=headers,
            method=method.upper(),
        )
        try:
            with urlopen(request, timeout=timeout) as response:
                return SimpleHTTPResponse(
                    status_code=int(getattr(response, "status", 200) or 200),
                    headers=dict(response.headers.items()),
                    content=response.read(),
                )
        except HTTPError as exc:
            return SimpleHTTPResponse(
                status_code=int(exc.code),
                headers=dict(exc.headers.items()),
                content=exc.read(),
            )


def build_http_session() -> Any:
    try:
        import requests
    except ImportError:
        return UrllibSession()
    return requests.Session()


def _append_query_params(url: str, params: Any) -> str:
    if not params:
        return url
    split = urlsplit(url)
    current_query = parse_qsl(split.query, keep_blank_values=True)
    for key, value in dict(params).items():
        current_query.append((str(key), str(value)))
    query = urlencode(current_query)
    return urlunsplit((split.scheme, split.netloc, split.path, query, split.fragment))


def _build_request_body(kwargs: dict[str, Any], headers: dict[str, str]) -> bytes | None:
    if "json" in kwargs and kwargs["json"] is not None:
        headers.setdefault("Content-Type", "application/json")
        return json.dumps(kwargs["json"]).encode("utf-8")

    data = kwargs.get("data")
    if data is None:
        return None
    if isinstance(data, (bytes, bytearray)):
        return bytes(data)
    if isinstance(data, str):
        return data.encode("utf-8")
    if isinstance(data, dict):
        headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
        return urlencode({str(key): str(value) for key, value in data.items()}).encode("utf-8")
    return bytes(data)

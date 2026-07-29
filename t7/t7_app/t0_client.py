from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass(slots=True)
class T0ClientError(Exception):
    status_code: int
    body: dict[str, Any]

    def __str__(self) -> str:
        return str(self.body.get("message", "T0 请求失败"))


class T0Client(Protocol):
    async def get(self, path: str) -> dict[str, Any]: ...

    async def post(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        request_id: str,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]: ...


@dataclass(slots=True)
class HttpT0Client:
    base_url: str
    api_key: str = ""
    timeout_seconds: float = 20.0

    async def get(self, path: str) -> dict[str, Any]:
        return await asyncio.to_thread(self._request_json, "GET", path, None, {}, 3.0)

    async def post(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        request_id: str,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        headers = {"X-Request-ID": request_id}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        return await asyncio.to_thread(
            self._request_json,
            "POST",
            path,
            payload,
            headers,
            self.timeout_seconds,
        )

    def _request_json(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None,
        extra_headers: dict[str, str],
        timeout_seconds: float,
    ) -> dict[str, Any]:
        headers = {"Accept": "application/json", **extra_headers}
        body = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        request = Request(
            f"{self.base_url}{path}",
            data=body,
            headers=headers,
            method=method,
        )
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                raw = response.read().decode("utf-8")
                result = json.loads(raw) if raw else {}
                if not isinstance(result, dict):
                    raise T0ClientError(
                        502,
                        {
                            "code": "INVALID_T0_RESPONSE",
                            "message": "T0 响应必须是 JSON 对象",
                            "retryable": False,
                            "details": {},
                        },
                    )
                return result
        except HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                error_body = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                error_body = {}
            if not isinstance(error_body, dict):
                error_body = {}
            error_body.setdefault("code", "T0_HTTP_ERROR")
            error_body.setdefault("message", f"T0 返回 HTTP {exc.code}")
            error_body.setdefault("retryable", exc.code >= 500 or exc.code == 429)
            error_body.setdefault("details", {})
            raise T0ClientError(exc.code, error_body) from exc
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise T0ClientError(
                502,
                {
                    "code": "T0_UNAVAILABLE",
                    "message": "T0 服务暂不可用",
                    "retryable": True,
                    "details": {"reason": type(exc).__name__},
                },
            ) from exc

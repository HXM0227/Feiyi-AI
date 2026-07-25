from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class T0Error(Exception):
    code: str
    message: str
    status_code: int = 500
    retryable: bool = False
    details: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


class ModuleCallError(T0Error):
    def __init__(
        self,
        module_id: str,
        message: str,
        *,
        retryable: bool = True,
        status_code: int = 502,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            code="DOWNSTREAM_MODULE_ERROR",
            message=f"{module_id} 调用失败：{message}",
            status_code=status_code,
            retryable=retryable,
            details={"module_id": module_id, **(details or {})},
        )

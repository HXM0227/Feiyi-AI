from __future__ import annotations

from dataclasses import dataclass

from .config import MODULE_IDS, Settings
from .contracts import HttpModuleClient, MockModuleClient, ModuleClient
from .errors import T0Error


@dataclass(slots=True)
class ModuleRegistry:
    clients: dict[str, ModuleClient]

    def get(self, module_id: str) -> ModuleClient:
        try:
            return self.clients[module_id]
        except KeyError as exc:
            raise T0Error(
                code="MODULE_NOT_REGISTERED",
                message=f"模块 {module_id} 未注册",
                status_code=503,
                retryable=False,
                details={"module_id": module_id},
            ) from exc


def build_registry(settings: Settings) -> ModuleRegistry:
    clients: dict[str, ModuleClient] = {}
    for module_id in MODULE_IDS:
        if settings.mode == "mock":
            clients[module_id] = MockModuleClient(module_id)
        else:
            clients[module_id] = HttpModuleClient(
                module_id=module_id,
                base_url=settings.module_urls[module_id],
                token=settings.downstream_token,
                timeout_seconds=settings.timeout_seconds,
                retry_count=settings.retry_count,
            )
    return ModuleRegistry(clients)

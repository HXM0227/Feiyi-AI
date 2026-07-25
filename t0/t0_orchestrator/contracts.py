from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .errors import ModuleCallError


class ModuleClient(Protocol):
    module_id: str

    async def call(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        trace_id: str,
        request_id: str,
    ) -> dict[str, Any]: ...

    async def health(self) -> bool: ...


@dataclass(slots=True)
class HttpModuleClient:
    module_id: str
    base_url: str
    token: str = ""
    timeout_seconds: float = 12.0
    retry_count: int = 1

    async def call(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        trace_id: str,
        request_id: str,
    ) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(self.retry_count + 1):
            try:
                return await asyncio.to_thread(
                    self._post_json, path, payload, trace_id, request_id
                )
            except ModuleCallError as exc:
                last_error = exc
                if not exc.retryable or attempt >= self.retry_count:
                    raise
                await asyncio.sleep(0.1 * (2**attempt))
        raise ModuleCallError(self.module_id, str(last_error))

    def _post_json(
        self,
        path: str,
        payload: dict[str, Any],
        trace_id: str,
        request_id: str,
    ) -> dict[str, Any]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Trace-ID": trace_id,
            "X-Request-ID": request_id,
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                body = response.read().decode("utf-8")
                result = json.loads(body) if body else {}
                if not isinstance(result, dict):
                    raise ModuleCallError(self.module_id, "响应必须是 JSON 对象")
                return result
        except HTTPError as exc:
            retryable = exc.code >= 500 or exc.code == 429
            raise ModuleCallError(
                self.module_id,
                f"HTTP {exc.code}",
                retryable=retryable,
                details={"path": path},
            ) from exc
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise ModuleCallError(
                self.module_id, str(exc), retryable=True, details={"path": path}
            ) from exc

    async def health(self) -> bool:
        try:
            return await asyncio.to_thread(self._get_health)
        except Exception:
            return False

    def _get_health(self) -> bool:
        request = Request(f"{self.base_url}/healthz", method="GET")
        with urlopen(request, timeout=min(self.timeout_seconds, 3.0)) as response:
            return 200 <= response.status < 300


@dataclass(slots=True)
class MockModuleClient:
    module_id: str

    async def call(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        trace_id: str,
        request_id: str,
    ) -> dict[str, Any]:
        await asyncio.sleep(0)
        handlers = {
            ("T1", "/v1/documents/normalize"): self._normalize_documents,
            ("T2", "/v1/graph/context"): self._graph_context,
            ("T2", "/v1/graph/upsert"): self._graph_upsert,
            ("T3", "/v1/retrieve"): self._retrieve,
            ("T3", "/v1/index/upsert"): self._index_upsert,
            ("T4", "/v1/generate"): self._generate,
            ("T5", "/v1/adapt"): self._adapt,
            ("T6", "/v1/input/normalize"): self._normalize_input,
            ("T6", "/v1/audio/synthesize"): self._synthesize,
            ("T8", "/v1/content/generate"): self._content,
            ("T9", "/v1/events"): self._ack,
            ("T9", "/v1/feedback"): self._ack,
        }
        handler = handlers.get((self.module_id, path))
        if handler is None:
            raise ModuleCallError(
                self.module_id, f"Mock 未实现 {path}", retryable=False
            )
        return handler(payload, trace_id, request_id)

    async def health(self) -> bool:
        return True

    @staticmethod
    def _normalize_input(payload: dict[str, Any], *_: str) -> dict[str, Any]:
        item = payload["input"]
        if item["type"] == "text":
            text = item["text"]
        elif item["type"] == "exhibit_id":
            text = f"请介绍展品 {item['exhibit_id']}"
        else:
            text = f"请识别并介绍该{item['type']}中的非遗内容"
        return {"query": text, "detected_language": "zh-CN", "confidence": 0.99}

    @staticmethod
    def _retrieve(payload: dict[str, Any], *_: str) -> dict[str, Any]:
        query = payload["query"]
        return {
            "chunks": [
                {
                    "citation_id": "CIT-001",
                    "source_id": "SRC-DEMO-001",
                    "title": "非遗项目示例资料",
                    "section": "历史与工艺",
                    "uri": "https://example.org/ich/demo#history",
                    "excerpt": f"与“{query[:24]}”相关的经审核示例知识片段。",
                    "score": 0.94,
                },
                {
                    "citation_id": "CIT-002",
                    "source_id": "SRC-DEMO-002",
                    "title": "传承人口述记录",
                    "section": "文化寓意",
                    "uri": "https://example.org/ich/demo#meaning",
                    "excerpt": "文化寓意应结合工艺语境解释，避免脱离来源的类比。",
                    "score": 0.88,
                },
            ]
        }

    @staticmethod
    def _graph_context(payload: dict[str, Any], *_: str) -> dict[str, Any]:
        return {
            "entities": ["非遗项目", "代表工艺", "文化寓意"],
            "relations": ["非遗项目-包含-代表工艺"],
            "constraints": ["区分史实与文化类比", "专名首次出现保留中文"],
        }

    @staticmethod
    def _adapt(payload: dict[str, Any], *_: str) -> dict[str, Any]:
        audience = payload["audience"]
        return {
            "policy_version": "mock-1",
            "instructions": [
                f"面向 {audience['region']} 地区的 {audience['knowledge_level']} 受众",
                f"采用 {audience['style']} 叙事风格",
                "事实必须有引用；类比必须标明是帮助理解的类比",
            ],
            "blocked_terms": [],
        }

    @staticmethod
    def _generate(payload: dict[str, Any], *_: str) -> dict[str, Any]:
        target = payload["target_language"]
        query = payload["query"]
        if target.lower().startswith("en"):
            answer = (
                f"This is a source-grounded demonstration answer to: {query}. "
                "It explains the craft, its historical context, and its cultural meaning "
                "without treating a cultural analogy as fact [CIT-001][CIT-002]."
            )
        else:
            answer = (
                f"这是针对“{query}”的有据示范讲解。内容依次说明代表工艺、历史语境与文化寓意，"
                "并明确区分史实和帮助理解的文化类比 [CIT-001][CIT-002]。"
            )
        return {"answer": answer, "used_citation_ids": ["CIT-001", "CIT-002"]}

    @staticmethod
    def _synthesize(payload: dict[str, Any], trace_id: str, *_: str) -> dict[str, Any]:
        digest = sha256(f"{trace_id}:{payload['text']}".encode()).hexdigest()[:12]
        return {
            "url": f"mock://audio/{digest}.mp3",
            "mime_type": "audio/mpeg",
            "voice": payload.get("voice", "default"),
        }

    @staticmethod
    def _content(payload: dict[str, Any], *_: str) -> dict[str, Any]:
        return {
            "content": (
                f"[{payload['platform']}] {payload['topic']}：一段适合目标平台的多语种传播文案。"
                "发布前请由项目成员核验事实、译名与授权状态。"
            ),
            "used_citation_ids": ["CIT-001", "CIT-002"],
            "review_required": True,
        }

    @staticmethod
    def _normalize_documents(payload: dict[str, Any], *_: str) -> dict[str, Any]:
        records = []
        for document in payload["documents"]:
            records.append(
                {
                    "source_id": document["source_id"],
                    "title": document["title"],
                    "source_uri": document["source_uri"],
                    "authorization_status": document["authorization_status"],
                    "chunks": [
                        {
                            "chunk_id": f"{document['source_id']}-001",
                            "text": f"{document['title']} 的 Mock 清洗片段",
                        }
                    ],
                }
            )
        return {"records": records}

    @staticmethod
    def _graph_upsert(payload: dict[str, Any], *_: str) -> dict[str, Any]:
        return {"accepted_count": len(payload.get("records", []))}

    @staticmethod
    def _index_upsert(payload: dict[str, Any], *_: str) -> dict[str, Any]:
        return {"accepted_count": len(payload.get("records", []))}

    @staticmethod
    def _ack(payload: dict[str, Any], *_: str) -> dict[str, Any]:
        return {"accepted": True}

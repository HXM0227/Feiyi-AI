from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


class AcceptanceFailure(RuntimeError):
    pass


class Client:
    def __init__(self, root: Path, evidence: Path) -> None:
        self.root = root
        self.evidence = evidence
        self.requests_dir = evidence / "requests"
        self.responses_dir = evidence / "responses"
        self.errors_dir = evidence / "errors"
        for directory in (self.requests_dir, self.responses_dir, self.errors_dir):
            directory.mkdir(parents=True, exist_ok=True)
        self.results: list[str] = []

    def record(self, message: str) -> None:
        print(message)
        self.results.append(message)

    def call(
        self,
        name: str,
        method: str,
        base_url: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        headers: dict[str, str] | None = None,
        expected_status: int = 200,
        timeout: float = 5.0,
        save_request: bool = True,
    ) -> dict[str, Any]:
        body = None
        request_headers = {"Accept": "application/json"}
        if headers:
            request_headers.update(headers)
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
            request_headers["Content-Type"] = "application/json"
        if save_request and payload is not None:
            self._write(self.requests_dir / f"{name}.json", payload)
        request = urllib.request.Request(
            f"{base_url.rstrip('/')}{path}", data=body, headers=request_headers, method=method
        )
        status = 0
        response_headers: dict[str, str] = {}
        response_body: Any = None
        error_text = ""
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                status = response.status
                response_headers = dict(response.headers.items())
                raw = response.read().decode("utf-8")
                response_body = json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            status = exc.code
            response_headers = dict(exc.headers.items()) if exc.headers else {}
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                response_body = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                response_body = {"raw": raw}
            error_text = f"HTTP {status}: {response_body}"
        except Exception as exc:  # expected for the unreachable-T2 scenario
            error_text = repr(exc)
            self._write(self.errors_dir / f"{name}.txt", error_text)
        record = {
            "status": status,
            "headers": {
                key: value
                for key, value in response_headers.items()
                if key.lower() in {"x-trace-id", "x-request-id", "content-type"}
            },
            "body": response_body,
            "error": error_text,
        }
        self._write(self.responses_dir / f"{name}.json", record)
        if status != expected_status:
            raise AcceptanceFailure(f"{name}: expected HTTP {expected_status}, got {status}; {error_text}")
        return record

    @staticmethod
    def _write(path: Path, value: Any) -> None:
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) if not isinstance(value, str) else value, encoding="utf-8")


def document(source_id: str, status: str, *, keyword: str, entity_prefix: str, relation_status: str | None = None) -> dict[str, Any]:
    chunk_id = f"{source_id}-0001"
    subject = f"{entity_prefix}-CRAFT"
    object_id = f"{entity_prefix}-TOOL"
    return {
        "source_id": source_id,
        "source_uri": f"https://example.org/feiyi/t2-closure/{source_id.lower()}",
        "media_type": "document",
        "title": f"T2 集成收口 {source_id}",
        "authorization_status": status,
        "metadata": {
            "text": f"{keyword} 是非遗人工标注验收资料，用于验证 T2 与 T3 的来源和分块回链。",
            "language": "zh-CN",
            "section": "integration-closure",
            "version": "2026-08-15",
        },
        "entities": [
            {
                "entity_id": subject,
                "entity_type": "craft",
                "canonical_name": keyword,
                "aliases": [f"{keyword}别名", f"{entity_prefix}-alias"],
                "language": "zh-CN",
            },
            {
                "entity_id": object_id,
                "entity_type": "tool",
                "canonical_name": f"{keyword}工具",
                "aliases": [f"{entity_prefix}-tool-alias"],
                "language": "zh-CN",
            },
        ],
        "relations": [
            {
                "relation_id": f"{entity_prefix}-USES",
                "subject_id": subject,
                "predicate": "uses",
                "object_id": object_id,
                "source_id": source_id,
                "chunk_id": chunk_id,
                "authorization_status": relation_status or status,
            }
        ],
    }


def body(record: dict[str, Any], request_id: str) -> dict[str, Any]:
    return {"request_id": request_id, "publish": True, "documents": [record]}


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AcceptanceFailure(message)


def wait_health(client: Client, port: int, label: str, timeout_seconds: float = 12.0) -> None:
    deadline = time.time() + timeout_seconds
    last: Exception | None = None
    while time.time() < deadline:
        try:
            result = client.call(f"health-{label}", "GET", f"http://127.0.0.1:{port}", "/healthz", expected_status=200, timeout=2, save_request=False)
            assert_true(result["body"].get("status") == "ok", f"{label} health body not ok")
            return
        except Exception as exc:
            last = exc
            time.sleep(0.25)
    raise AcceptanceFailure(f"{label} did not become healthy: {last}")


def run(args: argparse.Namespace) -> int:
    evidence = Path(args.evidence).resolve()
    client = Client(Path(args.root).resolve(), evidence)
    t0 = f"http://127.0.0.1:{args.t0_port}"
    t1 = f"http://127.0.0.1:{args.t1_port}"
    t2 = f"http://127.0.0.1:{args.t2_port}"
    t3 = f"http://127.0.0.1:{args.t3_port}"
    try:
        # Real Uvicorn health and readiness checks.
        for label, port in (("t0", args.t0_port), ("t1", args.t1_port), ("t2", args.t2_port), ("t3", args.t3_port)):
            wait_health(client, port, label, args.health_wait_seconds)
        for label, url in (("t1", t1), ("t2", t2), ("t3", t3)):
            result = client.call(f"ready-{label}", "GET", url, "/readyz")
            assert_true(result["body"].get("ready") is True, f"{label} readiness failed")
        client.call("capabilities-t2", "GET", t2, "/v1/capabilities")

        source_id = "SRC-T2-CLOSURE-CHAIN-20260815"
        prefix = "E-T2-CLOSURE-CHAIN-20260815"
        keyword = "闭环剪纸工艺20260815"
        chain_record = document(source_id, "authorized", keyword=keyword, entity_prefix=prefix)
        chain_payload = body(chain_record, "REQ-T2-CLOSURE-CHAIN-20260815")
        first = client.call("normal-ingest-001", "POST", t0, "/v1/knowledge/ingest", chain_payload, headers={"X-Trace-ID": "TRACE-T2-CLOSURE-CHAIN-001", "X-Request-ID": "REQ-T2-CLOSURE-CHAIN-20260815"})
        first_body = first["body"]
        assert_true(first_body.get("status") == "completed", "normal T0 ingestion did not complete")
        assert_true(first_body.get("accepted_count") == 1, "normal ingestion accepted_count != 1")
        assert_true(first["headers"].get("x-trace-id") == "TRACE-T2-CLOSURE-CHAIN-001", "T0 trace header was not preserved")
        assert_true(first_body.get("trace_id"), "T0 response body did not include trace_id")
        repeated_ingest = client.call("normal-ingest-repeat-001", "POST", t0, "/v1/knowledge/ingest", chain_payload, headers={"X-Trace-ID": "TRACE-T2-CLOSURE-CHAIN-002", "X-Request-ID": "REQ-T2-CLOSURE-CHAIN-20260815"})
        assert_true(repeated_ingest["body"].get("status") == "completed", "repeated T0 ingestion did not complete")
        assert_true(repeated_ingest["body"].get("accepted_count") == first_body.get("accepted_count"), "repeated ingestion accepted_count changed")

        query = client.call("chain-t2-query-001", "POST", t2, "/v1/graph/query", {"name": keyword, "include_relations": True})
        entities = query["body"].get("entities", [])
        relations = query["body"].get("relations", [])
        assert_true(any(item.get("entity_id") == f"{prefix}-CRAFT" for item in entities), "T2 chain entity missing")
        assert_true(any(item.get("relation_id") == f"{prefix}-USES" for item in relations), "T2 chain relation missing")
        entity = next(item for item in entities if item.get("entity_id") == f"{prefix}-CRAFT")
        relation = next(item for item in relations if item.get("relation_id") == f"{prefix}-USES")
        source_refs = entity.get("sources", [])
        assert_true(any(ref.get("source_id") == source_id and ref.get("chunk_id") == f"{source_id}-0001" for ref in source_refs), "T2 entity source/chunk backlink mismatch")
        assert_true(relation.get("source_id") == source_id and relation.get("chunk_id") == f"{source_id}-0001", "T2 relation source/chunk backlink mismatch")

        retrieval = client.call("chain-t3-retrieve-001", "POST", t3, "/v1/retrieve", {"query": keyword, "language": "zh-CN", "top_k": 10, "filters": {"authorization_status": ["authorized", "public"]}})
        chunks = retrieval["body"].get("chunks", [])
        citation = next((item for item in chunks if item.get("source_id") == source_id), None)
        assert_true(citation is not None, "T3 citation missing chain source")
        assert_true(citation.get("citation_id") == f"CIT-{source_id}-0001", "T3 citation chunk backlink mismatch")
        assert_true(citation.get("title") == chain_record["title"], "T3 title mismatch")
        assert_true(citation.get("uri") == chain_record["source_uri"], "T3 URI mismatch")
        assert_true(citation.get("source_id") == relation.get("source_id") and citation.get("citation_id", "").removeprefix("CIT-") == relation.get("chunk_id"), "T2/T3 source/chunk mismatch")

        repeated_query = client.call("chain-t2-query-repeat-001", "POST", t2, "/v1/graph/query", {"name": keyword, "include_relations": True})
        repeated_retrieval = client.call("chain-t3-retrieve-repeat-001", "POST", t3, "/v1/retrieve", {"query": keyword, "language": "zh-CN", "top_k": 10, "filters": {"authorization_status": ["authorized", "public"]}})
        assert_true(
            len([item for item in repeated_query["body"].get("entities", []) if item.get("entity_id") == f"{prefix}-CRAFT"]) == 1,
            "repeated ingestion produced duplicate T2 entity",
        )
        assert_true(
            len([item for item in repeated_query["body"].get("relations", []) if item.get("relation_id") == f"{prefix}-USES"]) == 1,
            "repeated ingestion produced duplicate T2 relation",
        )
        assert_true(
            len([item for item in repeated_retrieval["body"].get("chunks", []) if item.get("source_id") == source_id]) == 1,
            "repeated ingestion produced duplicate T3 citation",
        )

        # Authorization matrix and explicit bypass attempts. Direct T2 HTTP is used to isolate filtering semantics.
        auth_records = [
            document("SRC-T2-AUTH-AUTHORIZED-20260815", "authorized", keyword="授权可见实体20260815", entity_prefix="E-T2-AUTH-AUTHORIZED-20260815"),
            document("SRC-T2-AUTH-PUBLIC-20260815", "public", keyword="公开可见实体20260815", entity_prefix="E-T2-AUTH-PUBLIC-20260815"),
            document("SRC-T2-AUTH-UNKNOWN-20260815", "unknown", keyword="未知授权实体20260815", entity_prefix="E-T2-AUTH-UNKNOWN-20260815"),
            document("SRC-T2-AUTH-RESTRICTED-20260815", "restricted", keyword="受限授权实体20260815", entity_prefix="E-T2-AUTH-RESTRICTED-20260815"),
        ]
        auth_payload = {"records": [{**record, "chunks": [{"chunk_id": f"{record['source_id']}-0001", "text": record["metadata"]["text"], "sequence": 1, "language": "zh-CN"}]} for record in auth_records], "publish": True}
        auth_upsert = client.call("auth-upsert-001", "POST", t2, "/v1/graph/upsert", auth_payload)
        auth_upsert_repeat = client.call("auth-upsert-repeat-001", "POST", t2, "/v1/graph/upsert", auth_payload)
        assert_true(auth_upsert_repeat["body"].get("accepted_count") == auth_upsert["body"].get("accepted_count"), "T2 repeated accepted_count changed")
        assert_true(auth_upsert_repeat["body"].get("entity_count") == auth_upsert["body"].get("entity_count"), "T2 repeated entity_count changed")
        assert_true(auth_upsert_repeat["body"].get("relation_count") == auth_upsert["body"].get("relation_count"), "T2 repeated relation_count changed")
        for record in auth_records:
            keyword_value = record["entities"][0]["canonical_name"]
            expected = record["authorization_status"] in {"authorized", "public"}
            result = client.call(f"auth-default-{record['authorization_status']}-001", "POST", t2, "/v1/graph/query", {"name": keyword_value})
            found = bool(result["body"].get("entities"))
            assert_true(found == expected, f"default authorization visibility wrong for {record['authorization_status']}")
        unknown = auth_records[2]
        restricted = auth_records[3]
        for label, record in (("unknown", unknown), ("restricted", restricted)):
            keyword_value = record["entities"][0]["canonical_name"]
            entity_id = record["entities"][0]["entity_id"]
            alias = record["entities"][0]["aliases"][0]
            relation_id = record["relations"][0]["relation_id"]
            for suffix, payload in (
                ("name", {"name": keyword_value, "filters": {"authorization_status": [record["authorization_status"]]}}),
                ("alias", {"alias": alias}),
                ("entity-id", {"entity_id": entity_id}),
                ("predicate", {"predicate": "uses"}),
            ):
                result = client.call(f"auth-bypass-{label}-{suffix}-001", "POST", t2, "/v1/graph/query", payload)
                assert_true(not any(item.get("entity_id") == entity_id for item in result["body"].get("entities", [])) and not any(item.get("relation_id") == relation_id for item in result["body"].get("relations", [])), f"{label} bypass via {suffix} succeeded")
            detail = client.call(f"auth-bypass-{label}-detail-001", "GET", t2, f"/v1/graph/entities/{entity_id}")
            assert_true(detail["body"].get("entity") is None and not detail["body"].get("relations"), f"{label} entity detail bypass succeeded")
            relation_result = client.call(f"auth-bypass-{label}-relation-list-001", "GET", t2, f"/v1/graph/relations?entity_id={entity_id}")
            assert_true(not relation_result["body"].get("relations"), f"{label} relation list bypass succeeded")

        # Record a failure check for the T0 partial scenario in a separate live T0 process.
        if args.partial_t0_port:
            partial_t0 = f"http://127.0.0.1:{args.partial_t0_port}"
            wait_health(client, args.partial_t0_port, "partial-t0")
            partial_record = document("SRC-T2-PARTIAL-20260815", "authorized", keyword="T2失败降级资料20260815", entity_prefix="E-T2-PARTIAL-20260815")
            partial_payload = body(partial_record, "REQ-T2-PARTIAL-20260815")
            result = client.call("partial-ingest-001", "POST", partial_t0, "/v1/knowledge/ingest", partial_payload, headers={"X-Trace-ID": "TRACE-T2-PARTIAL-001", "X-Request-ID": "REQ-T2-PARTIAL-20260815"})
            partial_body = result["body"]
            assert_true(partial_body.get("status") == "partial", "T0 did not return partial when T2 was unreachable")
            assert_true(any("T2" in warning for warning in partial_body.get("warnings", [])), "partial response did not name T2 failure")
            assert_true(result["headers"].get("x-trace-id") == "TRACE-T2-PARTIAL-001", "partial response trace header mismatch")
            partial_retrieval = client.call("partial-t3-retrieve-001", "POST", t3, "/v1/retrieve", {"query": partial_record["metadata"]["text"].split("是")[0], "language": "zh-CN", "top_k": 10, "filters": {"authorization_status": ["authorized", "public"]}})
            assert_true(any(item.get("source_id") == partial_record["source_id"] for item in partial_retrieval["body"].get("chunks", [])), "T3 content did not survive T2 partial failure")
            partial_t2 = client.call("partial-t2-query-001", "POST", t2, "/v1/graph/query", {"name": partial_record["entities"][0]["canonical_name"]})
            assert_true(not partial_t2["body"].get("entities"), "T2 unexpectedly stored graph data during unreachable-T2 partial test")

        client.record("PASS real HTTP health/readiness/capabilities")
        client.record("PASS normal T0 -> T1 -> T3/T2 chain, source/chunk backlink")
        client.record("PASS duplicate ingestion downstream idempotency and stable query/retrieval")
        client.record("PASS authorized/public visible; unknown/restricted filtered; explicit bypass blocked")
        if args.partial_t0_port:
            client.record("PASS unreachable T2 -> T0 status=partial; T3 retained; graph absent")
        (evidence / "test-results.txt").write_text("\n".join(client.results) + "\n", encoding="utf-8")
        return 0
    except Exception as exc:
        client.record(f"FAIL {exc}")
        (evidence / "test-results.txt").write_text("\n".join(client.results) + "\n", encoding="utf-8")
        return 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=Path(__file__).resolve().parents[2])
    parser.add_argument("--evidence", default=Path(__file__).resolve().parents[2] / "联调证据" / "2026-08-15-t2-integration-closure")
    parser.add_argument("--t0-port", type=int, default=8100)
    parser.add_argument("--t1-port", type=int, default=8101)
    parser.add_argument("--t2-port", type=int, default=8102)
    parser.add_argument("--t3-port", type=int, default=8103)
    parser.add_argument("--partial-t0-port", type=int, default=8110)
    parser.add_argument("--health-wait-seconds", type=float, default=12.0)
    return run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())

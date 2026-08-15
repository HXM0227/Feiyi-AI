from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
PYTHON = str((ROOT.parent / ".venv" / "Scripts" / "python.exe").resolve())
DEFAULT_OUTPUT = ROOT / "联调证据" / "2026-08-13-t1-t3-acceptance"


class JsonStubHandler(BaseHTTPRequestHandler):
    """Minimal HTTP dependency used only to exercise T0 orchestration boundaries."""

    def do_GET(self) -> None:
        if self.path == "/healthz":
            self._json(200, {"status": "ok", "module": self.server.module_name})
            return
        self._json(404, {"code": "NOT_FOUND", "message": "stub route not found"})

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        payload = {}
        if length:
            raw = self.rfile.read(length)
            try:
                payload = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                payload = {}
        if self.path == "/v1/input/normalize":
            input_payload = payload.get("input", {})
            text = input_payload.get("text") or input_payload.get("value") or ""
            self._json(200, {"query": text, "detected_language": payload.get("source_language", "zh-CN")})
            return
        if self.path == "/v1/audio/synthesize":
            self._json(200, {"url": "stub://audio/acceptance.mp3", "mime_type": "audio/mpeg", "voice": "default"})
            return
        if self.path == "/v1/graph/upsert":
            self._json(200, {"status": "completed", "accepted_count": len(payload.get("records", []))})
            return
        if self.path == "/v1/graph/query":
            self._json(200, {"context": [], "nodes": [], "edges": []})
            return
        if self.path == "/v1/adapt":
            self._json(200, {"policy_version": "acceptance-stub", "instructions": [], "blocked_terms": []})
            return
        if self.path == "/v1/generate":
            self._json(200, {"answer": "stub answer [CIT-001]", "used_citation_ids": ["CIT-001"]})
            return
        if self.path == "/v1/synthesize":
            self._json(200, {"url": "stub://audio/acceptance.mp3", "mime_type": "audio/mpeg", "voice": "default"})
            return
        if self.path == "/v1/content":
            self._json(200, {"content": "stub content [CIT-001]", "used_citation_ids": ["CIT-001"], "review_required": True})
            return
        if self.path == "/v1/events":
            self._json(200, {"accepted": True})
            return
        if self.path == "/v1/feedback":
            self._json(200, {"accepted": True})
            return
        self._json(404, {"code": "NOT_FOUND", "message": "stub route not found"})

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Trace-ID", self.headers.get("X-Trace-ID", ""))
        self.send_header("X-Request-ID", self.headers.get("X-Request-ID", ""))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args) -> None:
        return


class T6UnavailableHandler(JsonStubHandler):
    def do_GET(self) -> None:
        if self.path == "/healthz":
            self._json(503, {"code": "DOWNSTREAM_UNAVAILABLE", "message": "T6 unavailable"})
            return
        super().do_GET()


def http_json(base_url: str, method: str, path: str, payload: dict | None = None, *, trace_id: str = "", request_id: str = "", headers: dict[str, str] | None = None) -> dict:
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request_headers = {"Accept": "application/json"}
    if data is not None:
        request_headers["Content-Type"] = "application/json; charset=utf-8"
    if trace_id:
        request_headers["X-Trace-ID"] = trace_id
    if request_id:
        request_headers["X-Request-ID"] = request_id
    if headers:
        request_headers.update(headers)
    request = Request(f"{base_url}{path}", data=data, headers=request_headers, method=method)
    try:
        with urlopen(request, timeout=8) as response:
            body = response.read().decode("utf-8")
            return {"status": response.status, "body": json.loads(body) if body else {}, "headers": {"X-Trace-ID": response.headers.get("X-Trace-ID", ""), "X-Request-ID": response.headers.get("X-Request-ID", "")}}
    except HTTPError as exc:
        raw = exc.read().decode("utf-8")
        return {"status": exc.code, "body": json.loads(raw) if raw else {}, "headers": {"X-Trace-ID": exc.headers.get("X-Trace-ID", ""), "X-Request-ID": exc.headers.get("X-Request-ID", "")}}
    except (URLError, TimeoutError, OSError) as exc:
        return {"status": 0, "body": {"code": "CONNECTION_ERROR", "message": str(exc)}, "headers": {}}


def wait_ready(base_url: str, timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        result = http_json(base_url, "GET", "/readyz")
        last = result
        if result["status"] == 200:
            return
        time.sleep(0.25)
    raise RuntimeError(f"service not ready: {base_url}; last={last}")


def start_service(name: str, module: str, port: int, output_dir: Path, env: dict[str, str], *, cwd: Path = ROOT) -> subprocess.Popen:
    stdout = (output_dir / "logs" / f"{name}-stdout.log").open("w", encoding="utf-8")
    stderr = (output_dir / "logs" / f"{name}-stderr.log").open("w", encoding="utf-8")
    process = subprocess.Popen([PYTHON, "-m", "uvicorn", module, "--factory", "--host", "127.0.0.1", "--port", str(port)], cwd=cwd, stdout=stdout, stderr=stderr, env=env)
    process._acceptance_log_handles = (stdout, stderr)  # type: ignore[attr-defined]
    return process


def run_stub(server: ThreadingHTTPServer) -> threading.Thread:
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return thread


def save_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="可复现的 T1/T3 验收 HTTP 联调")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    output_dir = args.output_dir if args.output_dir.is_absolute() else ROOT / args.output_dir
    for subdir in ("requests", "responses", "errors", "logs"):
        (output_dir / subdir).mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env.update({
        "PYTHONUTF8": "1",
        "T1_DB_PATH": str((output_dir / "t1.db").resolve()),
        "T3_DB_PATH": str((output_dir / "t3.db").resolve()),
        "T0_MODE": "http",
        "T1_BASE_URL": "http://127.0.0.1:8111",
        "T2_BASE_URL": "http://127.0.0.1:8112",
        "T3_BASE_URL": "http://127.0.0.1:8113",
        "T4_BASE_URL": "http://127.0.0.1:8114",
        "T5_BASE_URL": "http://127.0.0.1:8115",
        "T6_BASE_URL": "http://127.0.0.1:8116",
        "T8_BASE_URL": "http://127.0.0.1:8118",
        "T9_BASE_URL": "http://127.0.0.1:8119",
        "T0_TIMEOUT_SECONDS": "2",
        "T0_RETRY_COUNT": "0",
    })
    processes: list[subprocess.Popen] = []
    stubs: list[ThreadingHTTPServer] = []
    records = [
        {"source_id": "ACCEPTANCE-AUTH-001", "source_uri": "https://example.org/acceptance/auth", "media_type": "text", "title": "剪纸授权验收资料", "authorization_status": "authorized", "metadata": {"text": "剪纸拥有悠久历史。剪纸工艺包括折叠、刻剪和展开。", "language": "zh-CN", "version": "acceptance-1", "section": "历史与工艺"}},
        {"source_id": "ACCEPTANCE-UNKNOWN-001", "source_uri": "https://example.org/acceptance/unknown", "media_type": "text", "title": "剪纸未知授权资料", "authorization_status": "unknown", "metadata": {"text": "剪纸未知授权资料，不得默认公开。", "language": "zh-CN", "version": "acceptance-1", "section": "授权"}},
        {"source_id": "ACCEPTANCE-RESTRICTED-001", "source_uri": "https://example.org/acceptance/restricted", "media_type": "text", "title": "剪纸受限授权资料", "authorization_status": "restricted", "metadata": {"text": "剪纸受限授权资料，不得默认公开。", "language": "zh-CN", "version": "acceptance-1", "section": "授权"}},
    ]
    ingest_payload = {"request_id": "acceptance-ingest-001", "publish": False, "documents": records}
    guide_payload = {"request_id": "acceptance-guide-001", "session_id": "acceptance-session-001", "source_language": "zh-CN", "target_language": "zh-CN", "input": {"type": "text", "text": "剪纸工艺的历史是什么？"}, "audience": {"region": "global", "knowledge_level": "general", "style": "educational"}, "options": {"top_k": 5, "include_graph_context": False}}
    assertions: dict[str, bool] = {}
    results: dict[str, object] = {}
    try:
        for module, port in (("T2", 8112), ("T4", 8114), ("T5", 8115), ("T6", 8116), ("T8", 8118), ("T9", 8119)):
            server = ThreadingHTTPServer(("127.0.0.1", port), JsonStubHandler)
            server.module_name = f"{module}-STUB"  # type: ignore[attr-defined]
            stubs.append(server)
            run_stub(server)
        for name, module, port in (("t1", "t1.t1_service.api:create_app", 8111), ("t3", "t3.t3_service.api:create_app", 8113), ("t0", "t0.t0_orchestrator.api:create_app", 8110)):
            processes.append(start_service(name, module, port, output_dir, env))
        wait_ready("http://127.0.0.1:8111")
        wait_ready("http://127.0.0.1:8113")
        wait_ready("http://127.0.0.1:8110")

        for name, base, path, method, payload, trace, request in (
            ("t1-normalize", "http://127.0.0.1:8111", "/v1/documents/normalize", "POST", {"documents": [records[0]]}, "trace-t1-001", "request-t1-001"),
            ("t0-knowledge-ingest", "http://127.0.0.1:8110", "/v1/knowledge/ingest", "POST", ingest_payload, "trace-t0-ingest-001", "request-t0-ingest-001"),
            ("t3-upsert", "http://127.0.0.1:8113", "/v1/index/upsert", "POST", {"records": []}, "trace-t3-upsert-001", "request-t3-upsert-001"),
            ("t3-retrieve", "http://127.0.0.1:8113", "/v1/retrieve", "POST", {"query": "剪纸工艺历史", "language": "zh-CN", "top_k": 5}, "trace-t3-retrieve-001", "request-t3-retrieve-001"),
        ):
            save_json(output_dir / "requests" / f"{name}.json", {"method": method, "path": path, "headers": {"X-Trace-ID": trace, "X-Request-ID": request}, "body": payload})
            response = http_json(base, method, path, payload, trace_id=trace, request_id=request)
            results[name] = response
            save_json(output_dir / "responses" / f"{name}-response.json", response)

        # Direct T1/T3 boundary: consume T1 output and send it unchanged to T3.
        t1_response = results["t1-normalize"]  # type: ignore[assignment]
        direct_upsert_payload = {"records": t1_response["body"]["records"]}
        save_json(output_dir / "requests" / "t3-upsert-from-t1.json", direct_upsert_payload)
        direct_upsert = http_json("http://127.0.0.1:8113", "POST", "/v1/index/upsert", direct_upsert_payload, trace_id="trace-t1-t3-upsert-001", request_id="request-t1-t3-upsert-001")
        results["t3-upsert-from-t1"] = direct_upsert
        save_json(output_dir / "responses" / "t3-upsert-from-t1-response.json", direct_upsert)
        duplicate_upsert = http_json("http://127.0.0.1:8113", "POST", "/v1/index/upsert", direct_upsert_payload, trace_id="trace-t3-idempotent-001", request_id="request-t3-idempotent-001")
        results["t3-duplicate-upsert"] = duplicate_upsert
        save_json(output_dir / "errors" / "duplicate-upsert.json", duplicate_upsert)

        retrieve_auth = http_json("http://127.0.0.1:8113", "POST", "/v1/retrieve", {"query": "剪纸工艺历史", "top_k": 10}, trace_id="trace-auth-001", request_id="request-auth-001")
        retrieve_unknown = http_json("http://127.0.0.1:8113", "POST", "/v1/retrieve", {"query": "未知授权", "top_k": 10}, trace_id="trace-unknown-001", request_id="request-unknown-001")
        retrieve_restricted = http_json("http://127.0.0.1:8113", "POST", "/v1/retrieve", {"query": "受限授权", "top_k": 10}, trace_id="trace-restricted-001", request_id="request-restricted-001")
        no_match = http_json("http://127.0.0.1:8113", "POST", "/v1/retrieve", {"query": "完全不存在的关键词", "top_k": 5}, trace_id="trace-no-match-001", request_id="request-no-match-001")
        for name, response in (("unknown-authorization", retrieve_unknown), ("restricted-authorization", retrieve_restricted), ("no-match", no_match)):
            results[name] = response
            save_json(output_dir / "errors" / f"{name}.json", response)

        invalid_t1 = http_json("http://127.0.0.1:8111", "POST", "/v1/documents/normalize", {"documents": [{"source_id": "", "title": "", "source_uri": "x", "media_type": "text", "authorization_status": "unknown", "metadata": {}}]}, trace_id="trace-invalid-t1", request_id="request-invalid-t1")
        results["invalid-t1"] = invalid_t1
        save_json(output_dir / "errors" / "invalid-t1.json", invalid_t1)

        guide = http_json("http://127.0.0.1:8110", "POST", "/v1/guide/query", guide_payload, trace_id="trace-guide-001", request_id="request-guide-001")
        results["t0-guide-query"] = guide
        save_json(output_dir / "requests" / "t0-guide-query.json", {"method": "POST", "path": "/v1/guide/query", "headers": {"X-Trace-ID": "trace-guide-001", "X-Request-ID": "request-guide-001"}, "body": guide_payload})
        save_json(output_dir / "responses" / "t0-guide-query-response.json", guide)

        # T0 downstream unavailable: stop T3 and verify no ungrounded generation.
        t3_process = next(p for p in processes if p.args[-1] == "8113")
        t3_process.terminate()
        t3_process.wait(timeout=5)
        downstream_error = http_json("http://127.0.0.1:8110", "POST", "/v1/guide/query", guide_payload, trace_id="trace-downstream-001", request_id="request-downstream-001")
        results["downstream-unavailable"] = downstream_error
        save_json(output_dir / "errors" / "downstream-unavailable.json", downstream_error)

        assertions.update({
            "t1_normalize_ok": results["t1-normalize"]["status"] == 200 and bool(results["t1-normalize"]["body"].get("records")),
            "t0_ingest_completed": results["t0-knowledge-ingest"]["status"] == 200 and results["t0-knowledge-ingest"]["body"].get("status") == "completed" and results["t0-knowledge-ingest"]["body"].get("accepted_count") == 3,
            "t1_output_consumed_by_t3": direct_upsert["status"] == 200 and direct_upsert["body"].get("indexed_count") == 1,
            "duplicate_upsert_idempotent": duplicate_upsert["status"] == 200 and duplicate_upsert["body"].get("indexed_count") == 1,
            "authorized_retrievable": retrieve_auth["status"] == 200 and any(item.get("source_id") == "ACCEPTANCE-AUTH-001" for item in retrieve_auth["body"].get("chunks", [])),
            "unknown_filtered": retrieve_unknown["status"] == 200 and not retrieve_unknown["body"].get("chunks") and retrieve_unknown["body"].get("code") is None,
            "restricted_filtered": retrieve_restricted["status"] == 200 and not retrieve_restricted["body"].get("chunks") and retrieve_restricted["body"].get("code") is None,
            "no_match_empty": no_match["status"] == 200 and no_match["body"].get("chunks") == [],
            "citation_complete": retrieve_auth["status"] == 200 and all({"citation_id", "source_id", "title", "section", "uri", "excerpt", "score"}.issubset(item) for item in retrieve_auth["body"].get("chunks", [])),
            "t1_invalid_rejected": invalid_t1["status"] == 422 and invalid_t1["body"].get("code") == "VALIDATION_ERROR",
            "t0_guide_consumes_citations": guide["status"] == 200 and bool(guide["body"].get("citations")) and bool(guide["body"].get("answer")),
            "trace_headers_echoed": results["t1-normalize"]["headers"].get("X-Trace-ID") == "trace-t1-001" and results["t1-normalize"]["headers"].get("X-Request-ID") == "request-t1-001" and results["t3-retrieve"]["headers"].get("X-Trace-ID") == "trace-t3-retrieve-001",
            "t0_blocks_ungrounded": downstream_error["status"] >= 400 and downstream_error["body"].get("code") in {"DOWNSTREAM_MODULE_ERROR", "DOWNSTREAM_UNAVAILABLE", "NO_GROUNDED_CONTEXT"} and not downstream_error["body"].get("answer"),
        })
        save_json(output_dir / "summary.json", {"assertions": assertions, "results": results})
        (output_dir / "test-results.txt").write_text("\n".join(name + ": " + ("PASS" if bool(value) else "FAIL") for name, value in assertions.items()) + "\n", encoding="utf-8")
        print(json.dumps({"assertions": assertions, "all_passed": all(bool(value) for value in assertions.values())}, ensure_ascii=False, indent=2))
        return 0 if all(bool(value) for value in assertions.values()) else 1
    finally:
        for server in stubs:
            server.shutdown()
            server.server_close()
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            for handle in getattr(process, "_acceptance_log_handles", ()):  # type: ignore[attr-defined]
                handle.close()


if __name__ == "__main__":
    raise SystemExit(main())

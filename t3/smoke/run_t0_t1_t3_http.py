from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
PYTHON = str((ROOT.parent / ".venv" / "Scripts" / "python.exe").resolve())


class T2StubHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/healthz":
            self._json(200, {"status": "ok", "module": "T2-STUB"})
            return
        self._json(404, {"code": "NOT_FOUND"})

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        if length:
            self.rfile.read(length)
        if self.path == "/v1/graph/upsert":
            self._json(200, {"status": "completed", "accepted_count": 1})
            return
        self._json(404, {"code": "NOT_FOUND"})

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


def http_json(base_url: str, method: str, path: str, payload: dict | None = None, trace_id: str = "", request_id: str = "") -> dict:
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json; charset=utf-8"
    if trace_id:
        headers["X-Trace-ID"] = trace_id
    if request_id:
        headers["X-Request-ID"] = request_id
    request = Request(f"{base_url}{path}", data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=15) as response:
            return {
                "status": response.status,
                "body": json.loads(response.read().decode("utf-8")),
                "headers": {
                    "X-Trace-ID": response.headers.get("X-Trace-ID", ""),
                    "X-Request-ID": response.headers.get("X-Request-ID", ""),
                },
            }
    except HTTPError as exc:
        return {
            "status": exc.code,
            "body": json.loads(exc.read().decode("utf-8")),
            "headers": {},
        }


def wait_ready(base_url: str, timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if http_json(base_url, "GET", "/readyz")["status"] == 200:
                return
        except Exception:
            pass
        time.sleep(0.25)
    raise RuntimeError(f"service not ready: {base_url}")


def start_service(name: str, module: str, port: int, output_dir: Path, env: dict[str, str]) -> subprocess.Popen:
    stdout = (output_dir / f"{name}-stdout.log").open("w", encoding="utf-8")
    stderr = (output_dir / f"{name}-stderr.log").open("w", encoding="utf-8")
    process = subprocess.Popen(
        [PYTHON, "-m", "uvicorn", module, "--factory", "--host", "127.0.0.1", "--port", str(port)],
        cwd=ROOT,
        stdout=stdout,
        stderr=stderr,
        env=env,
    )
    process._codex_log_handles = (stdout, stderr)  # type: ignore[attr-defined]
    return process


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=ROOT / "联调证据" / "2026-08-02-t0-t1-t3")
    args = parser.parse_args()
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    for old in output_dir.glob("*.log"):
        old.unlink()

    environment = os.environ.copy()
    environment.update(
        {
            "PYTHONUTF8": "1",
            "T1_DB_PATH": str((output_dir / "t1.db").resolve()),
            "T3_DB_PATH": str((output_dir / "t3.db").resolve()),
            "T0_MODE": "http",
            "T1_BASE_URL": "http://127.0.0.1:8101",
            "T2_BASE_URL": "http://127.0.0.1:8102",
            "T3_BASE_URL": "http://127.0.0.1:8103",
            "T0_TIMEOUT_SECONDS": "5",
            "T0_RETRY_COUNT": "0",
        }
    )
    t2 = ThreadingHTTPServer(("127.0.0.1", 8102), T2StubHandler)
    processes: list[subprocess.Popen] = []
    try:
        t2_thread = __import__("threading").Thread(target=t2.serve_forever, daemon=True)
        t2_thread.start()
        for name, module, port in [
            ("t1", "t1.t1_service.api:create_app", 8101),
            ("t3", "t3.t3_service.api:create_app", 8103),
            ("t0", "t0.t0_orchestrator.api:create_app", 8000),
        ]:
            processes.append(start_service(name, module, port, output_dir, environment))
        wait_ready("http://127.0.0.1:8101")
        wait_ready("http://127.0.0.1:8103")
        time.sleep(0.5)

        request_payload = {
            "request_id": "req-t0-t1-t3-20260803-001",
            "publish": False,
            "documents": [
                {
                    "source_id": "PAPERCUT-T3-INTEGRATION-AUTH-001",
                    "source_uri": "https://example.org/ich/paper-cutting/t3-authorized",
                    "media_type": "text",
                    "title": "剪纸 T3 授权联调资料",
                    "authorization_status": "authorized",
                    "metadata": {
                        "text": "剪纸拥有悠久的历史。剪纸工艺包括折叠、刻剪和展开。",
                        "language": "zh-CN",
                        "version": "integration-0.1",
                        "section": "历史与工艺",
                    },
                },
                {
                    "source_id": "PAPERCUT-T3-INTEGRATION-UNKNOWN-001",
                    "source_uri": "https://example.org/ich/paper-cutting/t3-unknown",
                    "media_type": "text",
                    "title": "剪纸 T3 未知授权联调资料",
                    "authorization_status": "unknown",
                    "metadata": {
                        "text": "剪纸拥有悠久的历史。该资料授权状态未知。",
                        "language": "zh-CN",
                        "version": "integration-0.1",
                        "section": "授权说明",
                    },
                },
            ],
        }
        ingest = http_json(
            "http://127.0.0.1:8000",
            "POST",
            "/v1/knowledge/ingest",
            request_payload,
            trace_id="trace-t0-t1-t3-ingest",
            request_id="request-t0-t1-t3-ingest",
        )
        retrieve = http_json(
            "http://127.0.0.1:8103",
            "POST",
            "/v1/retrieve",
            {
                "query": "剪纸工艺",
                "language": "zh-CN",
                "top_k": 5,
                "filters": {"authorization_status": ["authorized", "public"]},
            },
            trace_id="trace-t0-t1-t3-retrieve",
            request_id="request-t0-t1-t3-retrieve",
        )
        result = {
            "http_status": ingest["status"],
            "ingest": ingest,
            "direct_t3_retrieve": retrieve,
            "assertions": {
                "t0_ingest_completed": ingest["status"] == 200 and ingest["body"].get("status") == "completed",
                "accepted_count_is_two": ingest["body"].get("accepted_count") == 2,
                "direct_t3_retrieve_ok": retrieve["status"] == 200,
                "unknown_source_filtered": all(
                    item.get("source_id") != "PAPERCUT-T3-INTEGRATION-UNKNOWN-001"
                    for item in retrieve["body"].get("chunks", [])
                ),
                "citation_fields_present": bool(retrieve["body"].get("chunks")) and all(
                    {"citation_id", "source_id", "title", "section", "uri", "excerpt", "score"}.issubset(item)
                    for item in retrieve["body"]["chunks"]
                ),
            },
        }
        (output_dir / "request.json").write_text(json.dumps(request_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (output_dir / "response.json").write_text(json.dumps(ingest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (output_dir / "t3-retrieve-response.json").write_text(json.dumps(retrieve, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (output_dir / "summary.json").write_text(json.dumps(result["assertions"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (output_dir / "README.md").write_text(
            "# T0 → T1 → T3 真实 HTTP 联调证据\n\n"
            "本目录由 `t3/smoke/run_t0_t1_t3_http.py` 生成。T2 使用临时 HTTP Stub，未替代真实 T1/T3。\n\n"
            "验证内容：T0 通过 HTTP 调用 T1 normalize，再调用 T3 index/upsert；随后直接调用 T3 retrieve，确认 authorized 资料可检索、unknown 资料默认被过滤，且引用字段可追溯。\n",
            encoding="utf-8",
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if all(result["assertions"].values()) else 1
    finally:
        t2.shutdown()
        t2.server_close()
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            for handle in getattr(process, "_codex_log_handles", ()):  # type: ignore[attr-defined]
                handle.close()


if __name__ == "__main__":
    raise SystemExit(main())

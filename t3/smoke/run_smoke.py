from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]


def request_json(base_url: str, method: str, path: str, payload: dict | None = None, trace_id: str = "") -> tuple[int, dict, dict[str, str]]:
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if trace_id:
        headers["X-Trace-ID"] = trace_id
        headers["X-Request-ID"] = f"request-for-{trace_id}"
    request = Request(f"{base_url.rstrip('/')}{path}", data=body, headers=headers, method=method)
    with urlopen(request, timeout=10) as response:
        response_body = json.loads(response.read().decode("utf-8"))
        response_headers = {
            "X-Trace-ID": response.headers.get("X-Trace-ID", ""),
            "X-Request-ID": response.headers.get("X-Request-ID", ""),
        }
        return response.status, response_body, response_headers


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8103")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    upsert_request = json.loads((ROOT / "t3/examples/upsert-request.json").read_text(encoding="utf-8-sig"))
    retrieve_request = json.loads((ROOT / "t3/examples/retrieve-request.json").read_text(encoding="utf-8-sig"))
    checks = {}
    for key, method, path, payload, trace in [
        ("health", "GET", "/healthz", None, "trace-t3-health"),
        ("ready", "GET", "/readyz", None, "trace-t3-ready"),
        ("upsert", "POST", "/v1/index/upsert", upsert_request, "trace-t3-upsert"),
        ("retrieve", "POST", "/v1/retrieve", retrieve_request, "trace-t3-retrieve"),
    ]:
        status, body, headers = request_json(args.base_url, method, path, payload, trace)
        checks[key] = {"status": status, "body": body, "headers": headers}
    text = json.dumps(checks, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if all(item["status"] == 200 for item in checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())

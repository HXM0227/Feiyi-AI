from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


T5_ROOT = Path(__file__).resolve().parents[1]
if str(T5_ROOT) not in sys.path:
    sys.path.insert(0, str(T5_ROOT))

from t5_cultural_adaptation.config import DEFAULT_POLICY_PATH
from t5_cultural_adaptation.schemas import AdaptationRequest
from t5_cultural_adaptation.service import AdaptationService


DEFAULT_CASES_PATH = Path(__file__).with_name("cases.json")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="运行 T5 确定性策略工程基线评测")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES_PATH)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY_PATH)
    return parser.parse_args()


def load_cases(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not payload:
        raise ValueError("evaluation cases must be a non-empty list")
    return payload


def request_for(case: dict[str, Any]) -> AdaptationRequest:
    case_id = str(case["id"])
    return AdaptationRequest.model_validate(
        {
            "query": f"基线问题-{case_id}",
            "target_language": case["target_language"],
            "audience": case["audience"],
            "graph_context": {"evaluation_sentinel": f"GRAPH-{case_id}"},
            "retrieval_context": [
                {
                    "citation_id": f"CIT-{case_id}",
                    "source_id": f"SRC-{case_id}",
                    "title": f"基线资料-{case_id}",
                    "excerpt": f"EXCERPT-{case_id}",
                    "score": 1.0,
                }
            ],
        }
    )


def evaluate_case(service: AdaptationService, case: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    request = request_for(case)
    response = service.adapt(request)
    joined = "\n".join(response.instructions)

    if response != service.adapt(request):
        errors.append("同一输入的两次输出不一致")
    if response.policy_version != service.policy.policy_version:
        errors.append("响应策略版本与载入策略不一致")
    if response.blocked_terms != case["expected_blocked_terms"]:
        errors.append("风险词列表与样例预期不一致")

    for fragment in case["expected_contains"]:
        if fragment not in joined:
            errors.append(f"缺少预期规则片段：{fragment}")

    forbidden_values = [
        request.query,
        request.retrieval_context[0].citation_id,
        request.retrieval_context[0].source_id,
        request.retrieval_context[0].title,
        request.retrieval_context[0].excerpt,
        request.graph_context["evaluation_sentinel"],
        request.audience.region,
    ]
    for value in forbidden_values:
        if value.casefold() != "global" and value in joined:
            errors.append(f"输出意外复制上游或受众原值：{value}")

    if len(response.instructions) != len(set(response.instructions)):
        errors.append("响应包含重复 instruction")
    return errors


def main() -> int:
    args = parse_args()
    service = AdaptationService.from_path(args.policy)
    results = []
    for case in load_cases(args.cases):
        errors = evaluate_case(service, case)
        results.append({"id": case["id"], "status": "passed" if not errors else "failed", "errors": errors})

    failed = sum(result["status"] == "failed" for result in results)
    print(json.dumps({
        "policy_version": service.policy.policy_version,
        "case_count": len(results),
        "passed": len(results) - failed,
        "failed": failed,
        "results": results,
        "scope": "engineering_rule_baseline_not_human_quality_acceptance"
    }, ensure_ascii=False, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

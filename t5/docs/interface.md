# T5 与 T0/T4 接口说明

T0 在导览主链路中调用 `POST http://127.0.0.1:8105/v1/adapt`，并透传 `X-Trace-ID`、`X-Request-ID` 和可选 `Authorization`。T5 接受但不保存或回显这些请求头。

## 请求

```json
{
  "query": "请介绍剪纸",
  "target_language": "en",
  "audience": {
    "region": "global",
    "age_band": "adult",
    "knowledge_level": "general",
    "style": "educational"
  },
  "graph_context": {},
  "retrieval_context": [
    {
      "citation_id": "CIT-001",
      "source_id": "SRC-001",
      "title": "剪纸资料",
      "section": "工艺",
      "uri": "https://example.org/source/1",
      "excerpt": "剪纸以纸张为主要材料。",
      "score": 0.95
    }
  ]
}
```

- `query`：T6 规范化后的非空问题，最多 4000 字符。
- `target_language`：首期支持 `zh-CN`、`en` 及 T4 已支持的别名。
- `audience`：字段和枚举与 T0 `AudienceProfile` 一致。
- `graph_context`：T2 的可选上游约束；T5 不用它创造事实。
- `retrieval_context`：T3 的可引用片段，必须非空且最多 20 项。

## 响应

```json
{
  "policy_version": "t5-cultural-policy-1.0.0",
  "instructions": ["只陈述上游上下文支持的事实。"],
  "blocked_terms": ["uncivilized people"]
}
```

T5 不返回新的事实或 citation。T0 把本响应原样放入 T4 请求的 `adaptation`；当前 T4 千问模式读取 `instructions`，尚不单独解析 `blocked_terms`，因此 T5 也会把风险词约束写入一条 instruction。

请求结构错误、空上下文、未知目标语言或非法受众枚举返回 HTTP 422：

```json
{
  "code": "VALIDATION_ERROR",
  "message": "请求不符合 T5 契约",
  "details": []
}
```

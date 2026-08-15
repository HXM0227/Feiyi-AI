# T2 MVP 测试与集成验收报告

日期：2026-08-15

## 1. 自动化回归

解释器：`C:\Users\sunbu\Documents\非遗AI解说\.venv\Scripts\python.exe`（Python 3.14.5）

| 模块 | 数量 | 结果 |
|---|---:|---|
| T0 | 12 | PASS |
| T1 | 18 | PASS |
| T2 | 6 | PASS |
| T3 | 9 | PASS |
| compileall | - | PASS |
| `git diff --check` | - | PASS |

T2 测试覆盖 health/ready/capabilities、trace/request ID、幂等 upsert、名称/别名/类型/实体 ID/关系查询、source/chunk 回链、授权状态变化、unknown/restricted 过滤、显式过滤绕过、实体详情和关系列表绕过、非法引用及空查询。

## 2. 真实 HTTP 集成验收

使用独立 Uvicorn 服务和独立 SQLite：T0 8120、T1 8121、T2 8122、T3 8123；另以 T0 8129 + 不可达 T2 8199 验证降级。

通过项：

- 正常 T0 → T1 → T3/T2 入库；
- T2/T3 `source_id/chunk_id` 一致回链；
- 相同请求重复入库后 T1 来源、T2 实体/关系、T3 chunk 均不重复；
- T2 重复 upsert 计数稳定；
- authorized/public 可见；
- unknown/restricted 不可见；
- name、alias、entity_id、predicate、详情接口和关系列表均不能绕过；
- T2 不可达时 T0 返回 `status=partial`，warnings 明确指出 T2 失败；
- partial 场景 T3 内容保留，T2 不产生该来源图谱；
- trace/request ID 可从响应头追踪。

证据：`C:\Users\sunbu\Documents\非遗AI解说\Feiyi-AI-fork\联调证据\2026-08-15-t2-integration-closure`。

## 3. 结论边界

本报告证明 T2 MVP 的契约、存储、授权过滤、回链、幂等和 T0 降级链路满足当前条件性验收基线；不等同于自动知识抽取、真实模型质量、专业复核、正式授权审核或生产部署完成。

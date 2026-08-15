# T2 知识图谱 MVP 交接文档

> 交接对象：项目统筹对话框 / 总集成负责人
> 交接模块：T2 知识图谱 MVP
> 交接日期：2026-08-14（北京时间）
> 当前仓库：`C:\Users\sunbu\Documents\非遗AI解说\Feiyi-AI-fork`

---

## 1. 交接结论

T2 知识图谱 MVP 已实现，并完成与 T0/T1/T3 的条件性 HTTP 契约联调。

当前可以确认：

- T2 已有独立 FastAPI 服务；
- T2 已使用 SQLite 完成实体、别名、关系、来源和 chunk 回链存储；
- T2 实体和关系 upsert 已具备幂等行为；
- T2 查询接口已具备名称、别名、实体类型、实体 ID、一跳关系和关系谓词查询能力；
- `authorized`、`public` 来源默认可查询；
- `unknown`、`restricted` 来源默认过滤，且不能通过显式过滤条件绕过；
- T0 已接入 T2 知识入库接口；
- 已完成 T0 → T1 → T3/T2 的真实 HTTP 入库链路联调；
- T2 自动化测试 6 项通过；
- T0、T1、T3 回归测试分别为 12、18、9 项通过；
- Python 编译检查和 `git diff --check` 通过。

准确的验收表述应为：

> T2 知识图谱 MVP 已实现，并完成与 T0/T1/T3 的条件性 HTTP 契约联调。

不能表述为生产级知识图谱系统已经完成。

---

## 2. 代码位置

T2 模块根目录：

```text
C:\Users\sunbu\Documents\非遗AI解说\Feiyi-AI-fork\t2\
```

主要文件：

```text
t2\main.py
 t2\requirements.txt
 t2\README.md
 t2\TEST_REPORT.md
 t2\t2_service\__init__.py
 t2\t2_service\api.py
 t2\t2_service\config.py
 t2\t2_service\models.py
 t2\t2_service\storage.py
 t2\docs\interface.md
 t2\examples\upsert-request.json
 t2\tests\test_api.py
```

T0 接入改动位置：

```text
t0\t0_orchestrator\models.py
t0\t0_orchestrator\orchestrator.py
t0\tests\test_orchestrator.py
```

项目交接文档和 T2 联调说明：

```text
项目交接文档.md
t2\TEST_REPORT.md
```

---

## 3. T2 已实现接口

### 3.1 系统接口

```http
GET /healthz
GET /readyz
GET /v1/capabilities
```

### 3.2 图谱写入接口

```http
POST /v1/graph/upsert
```

用途：接收 T1 标准化记录及人工标注的实体、关系，写入 T2 SQLite 图谱。

请求顶层结构：

```json
{
  "records": [
    {
      "source_id": "SRC-001",
      "title": "示例资料",
      "source_uri": "https://example.org/source/001",
      "media_type": "document",
      "authorization_status": "authorized",
      "metadata": {},
      "chunks": [],
      "entities": [],
      "relations": []
    }
  ],
  "publish": false
}
```

返回主要字段：

```json
{
  "contract_version": "1.0.0",
  "module": "T2",
  "status": "completed",
  "accepted_count": 1,
  "entity_count": 2,
  "relation_count": 1,
  "warnings": []
}
```

### 3.3 图谱查询接口

```http
POST /v1/graph/query
```

支持的查询条件：

- `entity_id`
- `name`
- `alias`
- `entity_type`
- `predicate`
- `include_relations`
- `limit`

授权过滤字段：

```json
{
  "filters": {
    "authorization_status": ["authorized", "public"]
  }
}
```

安全规则：

- 默认只返回 `authorized` 和 `public`；
- `unknown` 和 `restricted` 默认不返回；
- 即便请求中显式填入 `unknown` 或 `restricted`，也不能绕过服务端安全过滤；
- 关系的可见性按照关联来源当前授权状态判断；
- 来源授权状态更新为受限后，原来已经写入的实体和关系也会被过滤。

### 3.4 实体详情接口

```http
GET /v1/graph/entities/{entity_id}
```

返回实体详情、来源回链和关系。

### 3.5 关系查询接口

```http
GET /v1/graph/relations
```

支持按以下字段查询：

- `entity_id`
- `subject_id`
- `object_id`
- `predicate`
- `limit`

---

## 4. 数据模型

### 4.1 实体类型

```text
craft
person
place
tool
symbol
process
concept
```

### 4.2 关系类型

```text
belongs_to
related_to
uses
practiced_in
includes
has_symbol
has_process
has_tool
adapted_for
example_of
```

### 4.3 实体字段

```json
{
  "entity_id": "E-PAPERCUT",
  "entity_type": "craft",
  "canonical_name": "剪纸",
  "aliases": ["中国剪纸", "paper cutting"],
  "language": "zh-CN",
  "metadata": {}
}
```

### 4.4 关系字段

```json
{
  "relation_id": "R-001",
  "subject_id": "E-PAPERCUT",
  "predicate": "uses",
  "object_id": "E-SCISSORS",
  "source_id": "SRC-001",
  "chunk_id": "SRC-001-0001",
  "authorization_status": "authorized",
  "metadata": {}
}
```

约束：

- 关系的 `subject_id` 和 `object_id` 必须引用同一记录中存在的实体；
- 关系 `source_id` 若存在，必须和记录的 `source_id` 一致；
- 关系 `chunk_id` 若存在，必须引用同一记录中的 chunk；
- 不允许自动创建没有来源回链的实体或关系；
- 重复实体和关系写入不会导致重复数据。

---

## 5. T0/T1/T2/T3 接入方式

完整链路：

```text
客户端
  ↓
T0 /v1/knowledge/ingest
  ↓
T1 /v1/documents/normalize
  ↓
T0 根据 source_id 合并人工实体/关系标注
  ├──→ T3 /v1/index/upsert
  └──→ T2 /v1/graph/upsert
```

T0 入库请求中，实体和关系放在 `documents[]` 对应文档内：

```json
{
  "documents": [
    {
      "source_id": "SRC-T2-001",
      "source_uri": "https://example.org/t2/001",
      "media_type": "document",
      "title": "剪纸知识链路样例",
      "authorization_status": "authorized",
      "metadata": {
        "text": "蔚县剪纸是中国剪纸的地域性实践。",
        "language": "zh-CN",
        "version": "0.1"
      },
      "entities": [],
      "relations": []
    }
  ],
  "publish": true
}
```

重要注意事项：

1. `metadata.text` 必须存在，因为 T1 MVP 依赖该字段生成 chunk；
2. `media_type` 为 `document` 时必须提供预提取文本；
3. 关系的 `chunk_id` 必须匹配 T1 生成的 chunk ID；
4. T1 当前的 chunk ID 规则为：

```text
{source_id}-0001
```

5. T0 不绕过 T1；T3 仍只接收 T1 标准化 records；
6. T2 失败时，T0 保留 T3 成功结果并返回 `status=partial` 和警告。

---

## 6. 已完成自动化测试

执行命令：

```powershell
$repo = "C:\Users\sunbu\Documents\非遗AI解说\Feiyi-AI-fork"
$python = "C:\Users\sunbu\Documents\非遗AI解说\.venv\Scripts\python.exe"

Push-Location $repo
& $python -m unittest discover -s t0/tests -v
& $python -m unittest discover -s t1/tests -v
& $python -m unittest discover -s t2/tests -v
& $python -m unittest discover -s t3/tests -v
& $python -m compileall -q t0 t1 t2 t3
git diff --check
Pop-Location
```

最终结果：

```text
T0：12 tests，OK
T1：18 tests，OK
T2：6 tests，OK
T3：9 tests，OK
compileall：通过
git diff --check：通过
```

T2 测试覆盖：

- healthz；
- readyz；
- capabilities；
- trace/request ID；
- 实体和关系 upsert；
- 重复 upsert 幂等；
- 标准名称查询；
- 别名查询；
- 实体类型过滤；
- 一跳关系查询；
- source_id/chunk_id 回链；
- 授权过滤；
- 授权状态更新后的关系过滤；
- 无命中；
- 非法关系引用；
- 空查询错误。

---

## 7. 已完成真实 HTTP 联调

当前服务端口：

```text
T0：http://127.0.0.1:8100
T1：http://127.0.0.1:8101
T2：http://127.0.0.1:8102
T3：http://127.0.0.1:8103
```

已验证：

1. T0/T1/T2/T3 `/healthz` 均返回 HTTP 200；
2. T2 `/readyz` 返回 ready；
3. T2 `/v1/capabilities` 返回能力信息；
4. T2 独立 graph upsert 成功；
5. T2 重复 upsert 返回相同计数；
6. T2 按名称、别名、实体类型和实体 ID 查询成功；
7. T2 返回实体来源和 chunk 回链；
8. T2 返回关系来源和 chunk 回链；
9. 授权过滤生效；
10. T0 完整入库返回 `status=completed`；
11. T0 完整入库返回 `accepted_count=1`；
12. T3 成功写入标准化 chunk；
13. T2 成功写入人工标注实体和关系；
14. 重复完整入库请求成功，T2/T3 保持幂等；
15. T3 检索返回带 citation 的 chunk。

示例完整链路结果：

```json
{
  "contract_version": "1.0.0",
  "status": "completed",
  "accepted_count": 1,
  "warnings": []
}
```

T2 查询结果确认：

```text
实体数量：1
关系数量：1
source_id：SRC-T2-FULL-UTF8-002
chunk_id：SRC-T2-FULL-UTF8-002-0001
```

---

## 8. 联调证据位置

联调证据目录：

```text
C:\Users\sunbu\Documents\非遗AI解说\Feiyi-AI-fork\联调证据\2026-08-13-t2-mvp\
```

重要文件：

```text
README.md
test-results.txt

requests\t0-t1-t3-t2-ingest-utf8-002.json
responses\t0-t1-t3-t2-ingest-utf8-002.json
responses\t0-t1-t3-t2-ingest-utf8-repeat-002.json
responses\tt2-full-query-utf8-002.json
responses\tt3-full-retrieve-utf8-002.json

logs\t0.stderr.log
logs\t1.stderr.log
logs\tt2.stderr.log
logs\tt3.stderr.log
```

该目录记录了真实 Uvicorn 服务的端口联调结果，不是单纯 TestClient 测试结果。

---

## 9. 当前明确边界和未完成内容

以下内容没有在本次 T2 MVP 中实现：

- 自动实体抽取；
- 自动关系抽取；
- 大模型实体识别；
- OCR/ASR 自动采集；
- Neo4j；
- 图数据库集群；
- Embedding；
- 向量数据库；
- Rerank；
- 跨语言语义图谱对齐；
- 专家资料复核；
- 正式授权审核流程；
- 图谱版本管理和审核发布工作流；
- 生产级鉴权、限流、监控、备份和灾备；
- 多机共享 SQLite；
- 图谱删除、重建和增量维护接口。

当前实体和关系来自 T0 请求中的人工标注数据，不能解释为系统已经具备自动知识抽取能力。

---

## 10. 建议统筹对话框下一步处理顺序

### P0：先完成集成确认

1. 保留本交接文档和 `联调证据\2026-08-13-t2-mvp\`；
2. 检查 T0/T1/T2/T3 端口是否仍在运行；
3. 按本文第 5 节确认 T0 入库请求字段；
4. 在总集成测试中验证 T2 失败时 T0 的 `partial` 降级；
5. 确认 T3 检索和 T2 图谱查询的 `source_id/chunk_id` 能互相回链。

### P1：后续增强

1. 增加图谱专用集成测试脚本；
2. 增加 unknown/restricted 来源的完整 HTTP 过滤证据；
3. 增加 T2 API token 与下游鉴权联调；
4. 增加图谱导入、导出、删除和重建接口；
5. 根据实际数据量评估 SQLite 是否需要替换为 PostgreSQL 或 Neo4j；
6. 建立人工审核后的实体/关系发布流程；
7. 再考虑自动实体抽取、关系抽取、Embedding 和混合检索。

---

## 11. 给统筹对话框的简短结论

可以直接复制以下内容：

```text
T2 知识图谱 MVP 已完成并写入仓库：
C:\Users\sunbu\Documents\非遗AI解说\Feiyi-AI-fork\t2\

已实现 FastAPI + SQLite 图谱服务，支持实体、别名、关系、来源和 chunk 回链，支持幂等 upsert、名称/别名/实体类型/实体 ID/一跳关系查询，以及 authorized/public 默认可见、unknown/restricted 强制过滤。

T0 已接入 T2：
T0 /v1/knowledge/ingest → T1 /v1/documents/normalize → T3 /v1/index/upsert + T2 /v1/graph/upsert。
T2 失败时 T0 保留 T3 成功结果并返回 partial 降级。

测试结果：
T0 12 项通过，T1 18 项通过，T2 6 项通过，T3 9 项通过；compileall 和 git diff --check 通过。

真实 HTTP 联调已完成，服务端口为 8100/8101/8102/8103，证据目录：
C:\Users\sunbu\Documents\非遗AI解说\Feiyi-AI-fork\联调证据\2026-08-13-t2-mvp\

准确结论：T2 知识图谱 MVP 已实现，并完成与 T0/T1/T3 的条件性 HTTP 契约联调。
边界：当前实体/关系来自人工标注，尚未实现自动抽取、Neo4j、Embedding、向量库、Rerank、专业复核、正式授权审核和生产部署。
```

---

## 12. 工作区注意事项

- 本次没有执行 `git reset --hard`；
- 没有执行 `git clean -fd`；
- 没有删除已有的 `t3.zip`；
- 没有删除已有联调证据；
- 未覆盖用户已有的 T0/T1/T3 修改；
- 运行服务产生的 SQLite 数据库和日志属于联调产物，是否纳入最终提交应由统筹对话框统一决定。



---

## 13. 2026-08-15 集成收口与验收加固补充

本节为 2026-08-15 对 T2 MVP 进行的集成收口记录，补充并覆盖前文较早日期的联调结论；不改变 T2 的技术路线，也不代表已完成生产级能力。

### 13.1 本轮新增/确认的内容

- 新增统一真实 HTTP 验收脚本：
  `C:\Users\sunbu\Documents\非遗AI解说\Feiyi-AI-fork\t2\smoke\run_t2_integration_acceptance.py`
- 新增独立证据目录：
  `C:\Users\sunbu\Documents\非遗AI解说\Feiyi-AI-fork\联调证据\2026-08-15-t2-integration-closure\`
- 真实 HTTP 服务使用独立端口：T0 正常 8120、T1 8121、T2 8122、T3 8123；T0 降级场景使用 8129，T2 指向未监听的 8199。
- 独立验收使用证据目录内的独立 SQLite 数据库，避免污染历史联调数据。
- 验收脚本会保存请求、响应、错误、日志和结果摘要，失败时返回非零退出码。

### 13.2 真实 HTTP 验收结果

以下场景均已通过：

1. T0/T1/T2/T3 health；T1/T2/T3 readiness；T2 capabilities；
2. 正常链路：`T0 /v1/knowledge/ingest → T1 /v1/documents/normalize → T3 /v1/index/upsert + T2 /v1/graph/upsert`；
3. 正常链路返回 `status=completed`；
4. T2 实体、关系与 T3 citation 的 `source_id/chunk_id` 回链一致；
5. 重复 ingestion 后 T2/T3 不重复写入，查询和检索结果保持稳定；
6. `authorized`、`public` 来源默认可见；
7. `unknown`、`restricted` 来源默认过滤；
8. 通过 name、alias、entity_id、predicate、实体详情和关系列表等方式均不能绕过授权过滤；
9. T2 不可达时 T0 仍返回 HTTP 200、`status=partial`，warnings 明确说明 T2 图谱写入失败；
10. partial 场景下 T3 已写入内容仍可检索，T2 不生成没有来源依据的图谱数据；
11. 正常和 partial 响应均保留 `X-Trace-ID` / `X-Request-ID`；
12. 自动化回归、编译检查和 diff 检查均通过。

### 13.3 证据和测试结果

关键结果文件：

- `联调证据\2026-08-15-t2-integration-closure\test-results.txt`
- `联调证据\2026-08-15-t2-integration-closure\test-results-automated.txt`
- `联调证据\2026-08-15-t2-integration-closure\responses\normal-ingest-001.json`
- `联调证据\2026-08-15-t2-integration-closure\responses\normal-ingest-repeat-001.json`
- `联调证据\2026-08-15-t2-integration-closure\responses\chain-t2-query-001.json`
- `联调证据\2026-08-15-t2-integration-closure\responses\chain-t3-retrieve-001.json`
- `联调证据\2026-08-15-t2-integration-closure\responses\partial-ingest-001.json`
- `联调证据\2026-08-15-t2-integration-closure\responses\partial-t3-retrieve-001.json`
- `联调证据\2026-08-15-t2-integration-closure\responses\partial-t2-query-001.json`
- `联调证据\2026-08-15-t2-integration-closure\responses\sqlite-idempotency-counts.json`
- `联调证据\2026-08-15-t2-integration-closure\responses\automated-test-summary.json`

自动化回归：

```text
T0：12 tests，PASS
T1：18 tests，PASS
T2：6 tests，PASS
T3：9 tests，PASS
compileall：PASS
git diff --check：PASS
Python：3.14.5
```

### 13.4 幂等与回链核对

统一正常链路来源：`SRC-T2-CLOSURE-CHAIN-20260815`。

重复入库后的独立 SQLite 计数：

- T1 source ledger：1 条；
- T2 source：1 条；
- T2 chunk：1 条；
- T2 entity_sources：2 条；
- T2 relation：1 条；
- T3 chunk：1 条。

该结果证明本轮场景下 source、chunk、entity-source 关联、relation 和 T3 chunk 均保持幂等，且 T2/T3 能够通过相同的 `source_id` 与 `chunk_id` 互相回链。

### 13.5 当前验收表述

可以对外或向统筹对话框表述为：

> T2 知识图谱 MVP 已完成当前 T0/T1/T3 基线的真实 HTTP 集成收口与条件性验收加固。

仍不能表述为：自动实体/关系抽取完成、专业资料复核完成、正式授权审核完成、真实大模型质量验收完成、Neo4j/Embedding/向量库/Rerank/复杂图推理完成，或已达到生产部署标准。

---

# T2 接口说明

## 授权规则

查询默认只返回来源授权状态为：

```text
authorized
public
```

`unknown` 和 `restricted` 可以写入并保留原状态，但默认不会出现在实体、关系或来源回链中。即使客户端在 `filters.authorization_status` 中请求 `restricted` 或 `unknown`，服务也不会放行这些状态。

## 实体类型

```text
craft, person, place, tool, symbol, process, concept
```

## 关系类型

```text
belongs_to, related_to, uses, practiced_in, includes,
has_symbol, has_process, has_tool, adapted_for, example_of
```

## POST `/v1/graph/upsert`

请求：

```json
{
  "records": [
    {
      "source_id": "PAPERCUT-T2-DEMO-001",
      "title": "中国剪纸人工标注知识图谱样例",
      "source_uri": "https://example.org/feiyi/papercut-t2-demo",
      "media_type": "text",
      "authorization_status": "authorized",
      "metadata": {"language": "zh-CN", "version": "0.1"},
      "chunks": [
        {
          "chunk_id": "PAPERCUT-T2-DEMO-001-0001",
          "text": "中国剪纸是一种传统民间工艺。",
          "sequence": 1,
          "section": "基本概念",
          "language": "zh-CN"
        }
      ],
      "entities": [
        {
          "entity_id": "ENTITY-PAPERCUT",
          "entity_type": "craft",
          "canonical_name": "剪纸",
          "aliases": ["中国剪纸", "paper cutting"],
          "language": "zh-CN"
        }
      ],
      "relations": []
    }
  ],
  "publish": false
}
```

响应包括：

- `accepted_count`：接受的来源记录数；
- `entity_count`：本次处理的实体数；
- `relation_count`：本次处理的关系数；
- `warnings`：未授权状态等提示。

## POST `/v1/graph/query`

可按以下字段查询：

```json
{"name": "剪纸"}
{"alias": "paper cutting"}
{"entity_type": "craft", "name": "剪纸"}
{"entity_id": "ENTITY-PAPERCUT"}
{"predicate": "uses", "include_relations": false}
```

空查询、空名称、非法类型和非法关系会返回统一 `VALIDATION_ERROR`。

成功响应包含：

```json
{
  "contract_version": "1.0.0",
  "module": "T2",
  "entities": [],
  "relations": []
}
```

无命中使用空数组，不构造虚假实体或关系。

## GET `/v1/graph/entities/{entity_id}`

返回：

- `entity`：实体详情；
- `entity.sources[]`：来源、标题、URI、授权状态和 `chunk_id`；
- `relations[]`：实体一跳关系。

查询不到实体时 `entity` 为 `null`，`relations` 为空数组。

## GET `/v1/graph/relations`

支持查询参数：

```text
entity_id
subject_id
object_id
predicate
limit
```

关系结果保留：

```text
relation_id
subject_id
predicate
object_id
source_id
chunk_id
authorization_status
metadata
```

## T0 输入扩展

为保持 T1 原有 `KnowledgeDocument` 兼容，T0 在文档输入中允许可选：

```text
entities[]
relations[]
```

T0 先将文档发送给 T1 规范化，再把同一来源的人工标注实体/关系附加到 T1 生成的 record 上，发送给 T2。T3 仍然只接收 T1 的标准化 records，不会绕过 T1/T3。

# T0 技术架构与集成中枢

T0 是“非遗 AI 多语种智能解说传播项目”的统一 API 入口和流程编排层。它负责协议、路由、追踪、降级和联调，不实现 T1-T9 各模块内部的 OCR、RAG、生成、翻译或前端业务。

## 快速启动

```bash
cd t0
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn t0_orchestrator.api:create_app --factory --host 0.0.0.0 --port 8000
```

默认 `T0_MODE=mock`，不需要模型密钥或其他模块即可运行完整演示。

打开接口文档：`http://localhost:8000/docs`

运行全部测试（使用项目依赖，不调用真实模型或外部服务）：

```bash
python -m unittest discover -s tests -v
```

运行端到端示例：

```bash
python examples/run_demo.py
```

## 接入真实模块

将 `T0_MODE` 改为 `http`，并配置实际服务地址：

```bash
export T0_MODE=http
export T3_BASE_URL=http://rag-service:8103
export T4_BASE_URL=http://generation-service:8104
export T5_BASE_URL=http://adaptation-service:8105
export T6_BASE_URL=http://multimodal-service:8106
export T8_BASE_URL=http://content-service:8108
export T9_BASE_URL=http://ops-service:8109
```

所有下游服务均接收 `Content-Type: application/json`，并透传 `X-Trace-ID`、`X-Request-ID` 与 `Authorization`。详细字段、失败策略和联调顺序见项目根目录中的《T0 模块设计与集成技术说明书》。

## 统一入口

- `POST /v1/guide/query`：导览问答主链路。
- `POST /v1/content/generate`：传播内容生成链路。
- `POST /v1/knowledge/ingest`：知识入库编排链路。
- `POST /v1/feedback`：反馈写入。
- `GET /v1/capabilities`：能力和契约版本发现。
- `GET /healthz`、`GET /readyz`：存活与就绪检查。

## 目录

```text
t0/
├── t0_orchestrator/      # 核心包
│   ├── api.py            # FastAPI 入口、鉴权和错误映射
│   ├── config.py         # 环境配置
│   ├── contracts.py      # 模块客户端协议、HTTP/Mock 适配器
│   ├── errors.py         # 统一错误模型
│   ├── models.py         # v1 数据契约
│   ├── orchestrator.py   # T0 流程编排与降级策略
│   └── registry.py       # T1-T9 服务注册表
├── examples/             # 联调样例
├── tests/                # 编排单元测试与 ASGI API 冒烟测试
├── .env.example
└── requirements.txt
```

# T7 扫码导览端与内容管理界面

T7 是“非遗 AI 多语种智能解说传播项目”的游客交互端和轻量内容管理后台。
它采用 H5/PWA + FastAPI BFF，仅调用 T0 公开接口，不直接连接 T1–T9，
也不会在浏览器中暴露 T0 API Key。

> 当前版本：v1.0.0。已完成 T0 Mock 联调；真实 T3/T4/T6/T8/T9 由 T0
> 按相同接口契约替换。

## 功能

- 扫码进入：解析 `exhibit_id`、`lang` 等白名单参数。
- 游客问答：支持文字、展品编号、图片和音频输入。
- 多语展示：呈现回答、引用、告警、音频和 `trace_id`。
- 弱网处理：反馈失败后进入浏览器队列，联网时自动重试。
- 内容后台：生成、编辑、审核、批准、发布和归档传播内容。
- 知识入库：由后台代理调用 T0 知识入库接口。
- 安全代理：T0 密钥仅保存在服务端；限制上传类型和大小。
- PWA：缓存应用壳，不缓存 `/api` 业务回答。

## 架构

```text
游客浏览器 / 内容管理员
          │
          ▼
T7 H5/PWA + FastAPI BFF
  ├─ 静态页面与媒体上传
  ├─ T0 安全代理
  ├─ 弱网反馈队列
  └─ SQLite 内容审核状态
          │
          ▼
T0 /v1（统一编排 T1–T9）
```

## 环境要求

- Python 3.11 或 3.12
- 可访问的 T0 服务；默认地址为 `http://127.0.0.1:8000`
- macOS、Linux 或 Windows

没有启动 T0 时，T7 页面和后台仍可打开，但问答、反馈、内容生成和知识入库
功能会提示 T0 不可用。

## 快速启动

### 1. 安装 T7

在仓库根目录运行：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Windows PowerShell 激活虚拟环境：

```powershell
.venv\Scripts\Activate.ps1
```

修改 `.env`，至少替换管理员令牌：

```env
T7_ADMIN_TOKEN=请替换为随机且足够长的令牌
```

不要把 `.env` 提交到 GitHub。

### 2. 启动 T0

如果 T0 仓库位于 T7 的同级目录，可在另一个终端运行：

```bash
cd ../t0
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn t0_orchestrator.api:create_app --factory --host 127.0.0.1 --port 8000
```

如果使用远程 T0，请在 `.env` 中配置：

```env
T7_T0_BASE_URL=https://your-t0.example.com
T7_T0_API_KEY=your-t0-api-key
```

### 3. 启动 T7

```bash
python -m uvicorn t7_app.api:create_app --factory --host 127.0.0.1 --port 8007
```

访问：

- 游客端：<http://127.0.0.1:8007/>
- 模拟扫码：<http://127.0.0.1:8007/?exhibit_id=EXHIBIT-001&lang=zh-CN>
- 内容后台：<http://127.0.0.1:8007/admin>
- OpenAPI：<http://127.0.0.1:8007/docs>
- 健康检查：<http://127.0.0.1:8007/healthz>

后台登录令牌是 `.env` 中的 `T7_ADMIN_TOKEN`。

## 配置

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `T7_T0_BASE_URL` | `http://127.0.0.1:8000` | T0 地址 |
| `T7_T0_API_KEY` | 空 | T7 调用 T0 的密钥 |
| `T7_REQUEST_TIMEOUT_SECONDS` | `20` | T0 请求超时 |
| `T7_ADMIN_TOKEN` | 空 | 留空时关闭后台 API |
| `T7_DATABASE_PATH` | `data/t7.db` | SQLite 数据库 |
| `T7_UPLOAD_DIR` | `data/uploads` | 本地媒体目录 |
| `T7_MAX_UPLOAD_BYTES` | `10485760` | 单文件大小限制 |
| `T7_PUBLIC_BASE_URL` | 空 | 供外部 T6 读取媒体的地址 |

## T0 接口映射

| T7 BFF | T0 |
| --- | --- |
| `GET /api/config` | `GET /v1/capabilities` |
| `POST /api/guide/query` | `POST /v1/guide/query` |
| `POST /api/feedback` | `POST /v1/feedback` |
| `POST /api/admin/content/generate` | `POST /v1/content/generate` |
| `POST /api/admin/knowledge/ingest` | `POST /v1/knowledge/ingest` |

T7 自动生成 `X-Request-ID`，问答请求使用同一值作为
`Idempotency-Key`。T0 的错误状态和 JSON 错误主体会尽量保持不变。

## 内容审核状态

```text
draft → in_review → approved → published → archived
           └──────→ rejected → draft
```

当前 MVP 中，“发布”表示写入 T7 本地发布状态，并可通过
`GET /api/content/published` 查询，不表示已推送到真实社交媒体或 CMS。

## 测试

```bash
python -m unittest discover -s tests -v
```

测试使用 Fake T0 客户端，不调用真实模型或外部网络。GitHub Actions 会在
Python 3.11 和 3.12 上执行同一组测试。

## 仓库结构

```text
.
├── .github/workflows/tests.yml
├── docs/
│   └── 非遗AI多语种智能解说传播项目_T7模块设计与集成技术说明书.docx
├── examples/
│   └── guide-query.json
├── static/
│   ├── index.html
│   ├── admin.html
│   ├── css/app.css
│   ├── js/
│   ├── manifest.webmanifest
│   └── sw.js
├── t7_app/
│   ├── api.py
│   ├── config.py
│   ├── models.py
│   ├── store.py
│   └── t0_client.py
├── tests/test_api.py
├── .env.example
├── .gitignore
├── CHANGELOG.md
└── requirements.txt
```

## 上传媒体

游客端先把图片或音频上传到 T7，再把 `media_url` 传给 T0/T6。真实 T6
联调时，必须设置可被 T6 访问的 `T7_PUBLIC_BASE_URL`。生产环境建议使用
对象存储、短期签名 URL、病毒扫描和媒体清理任务。

## 生产部署前

- 使用 OAuth/OIDC 和 RBAC 替换共享管理员令牌。
- 将 SQLite 迁移到共享数据库，并增加并发控制。
- 将本地媒体目录替换为对象存储。
- 增加 HTTPS、CSRF/Origin 校验、限流和安全响应头。
- 对接真实 T6、T8、T9 以及实际内容发布平台。

## 文档

详细设计、接口边界、状态机、联调顺序和验收用例见：

[T7 模块设计与集成技术说明书](docs/非遗AI多语种智能解说传播项目_T7模块设计与集成技术说明书.docx)

## 许可

本仓库当前未附加开源许可证，默认仅用于本项目内部开发、课程展示和团队联调。
如需公开复用或开源分发，请由项目成员共同确定许可证。

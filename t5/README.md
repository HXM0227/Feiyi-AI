# T5 跨文化适配与提示词策略

T5 位于 T3/T2 与 T4 之间。它不翻译、不检索、不生成事实，而是把 T0 的受众画像转换成版本化、可审计的表达约束，供 T4 组织讲解时使用。

## MVP 边界

- 离线确定性规则，不调用模型或外部网络；
- 首期与 T4 一致，仅支持 `zh-CN` 和 `en`；
- 根据年龄、知识水平、叙事风格和地区字段组合指令；
- 地区字段不触发国家或民族刻板类比，只增加保守解释规则；
- 不改变 T3 的事实、excerpt 或 citation ID；
- 输出版本化 `instructions` 和 `blocked_terms`。

## 启动

在 `t5/` 下执行：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn t5_cultural_adaptation.api:app --host 0.0.0.0 --port 8105
```

接口文档位于 `http://127.0.0.1:8105/docs`。

## 测试

```powershell
python -m unittest discover -s tests -v
python evaluation/run_baseline.py
```

第二条命令覆盖语言、年龄、知识水平、表达风格、地区处理、风险词隔离和确定性。它属于工程规则基线，不等同于跨文化表达质量或专家审核已经通过。

测试完全离线。HTTP 联调时先启动 T5，再运行：

```powershell
python smoke/run_t0_t5_http.py
```

该脚本使用 T0 的现有 Mock 链路，仅把 T5 替换为真实 HTTP 客户端，并确认策略被继续传给 T4。

## T0 配置

真实全链路模式需要显式设置：

```ini
T0_MODE=http
T5_BASE_URL=http://127.0.0.1:8105
```

T0 当前默认端口计算存在已知错误，完整联调仍应显式设置 T3、T4、T5、T6 的 Base URL。

## 质量边界

本模块的规则和风险词只是工程级安全基线，不等同于跨文化质量验收。地区类比、禁忌和表达效果仍需国际学生、传承人或相关领域专家抽检后再扩展。

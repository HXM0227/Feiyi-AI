# T0 → T1 → T3 真实 HTTP 联调证据

本目录由 `t3/smoke/run_t0_t1_t3_http.py` 生成。T2 使用临时 HTTP Stub，未替代真实 T1/T3。

验证内容：T0 通过 HTTP 调用 T1 normalize，再调用 T3 index/upsert；随后直接调用 T3 retrieve，确认 authorized 资料可检索、unknown 资料默认被过滤，且引用字段可追溯。

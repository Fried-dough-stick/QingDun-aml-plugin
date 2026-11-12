# `docs/mocks`

从真后端抓的响应样例，供 A 在 Postgres ETL、登录页、总览/交易页尚未就绪时先写前端。抓取时间 2026-11-12，数据为全量 748,869 笔交易、3,000 条预警（25 high / 2,975 mid）。

| 文件 | 对应接口 |
|---|---|
| `health.json` | `GET /api/health` |
| `dashboard.json` | `GET /api/dashboard`（summary + distribution + trend + latest_alerts） |
| `transactions.json` | `GET /api/transactions?page_size=3&risk_level=high` |
| `transaction_detail.json` | `GET /api/transactions/{txn_id}` |
| `alerts.json` | `GET /api/alerts?page_size=3&risk_level=high` |
| `alert_detail.json` | `GET /api/alerts/{alert_id}?days=30` |
| `reports.json` | `GET /api/reports?page_size=5` |

注意：

- 这些是**真接口输出**，不是手写 mock；接真库后字段名和结构不变。
- 响应已用脚本递归扫描，确认不含 `is_suspicious`、`suspicion_reason`、`case_id`、`is_false_positive`。
- 演示账号 `demo / demo123456`；`AUTH_MODE=demo` 时未登录也能取到这些响应。
- 数据会随重新打分变化，页面应只依赖字段结构，不要把具体数字写死。

# 青盾 2.0 API（D6 版）

- 前缀：`/api`
- 交互文档：`/api/docs`
- 认证：httpOnly Cookie `qd_access_token`，或 `Authorization: Bearer <token>`
- 演示模式：`AUTH_MODE=demo` 时未登录落到 `demo` 用户；`strict` 时返回 401
- 分页：`page`（从 1 开始）、`page_size`（默认 20，上限 100）
- 错误：`{"detail": "中文错误信息"}`

## 1. 系统与认证

| 方法 | 路径 | 参数 | 说明 |
|---|---|---|---|
| GET | `/health` | — | `status/mode/model_version/txn_count/alert_count/scored_count`；模型缺失时 `mode=rule_only` |
| GET | `/config` | — | `app_name/env/auth_mode/default_page_size/max_page_size/max_export_rows` |
| POST | `/auth/login` | `{username,password}` | 校验密码，写 httpOnly Cookie，记审计 |
| POST | `/auth/logout` | — | 清 Cookie |
| GET | `/auth/me` | — | 当前用户 `id/username/email/role/display_name` |

注册接口由 A 的 `feat/auth` 提供，B 已留好 `api/auth.py` 挂载点。

## 2. 总览

| 方法 | 路径 | 参数 | 说明 |
|---|---|---|---|
| GET | `/dashboard` | — | 一次返回 `summary/trend/distribution/latest_alerts` |
| GET | `/dashboard/summary` | — | 4 个 KPI：交易数、账户数、预警数、高危占比 |
| GET | `/dashboard/trend` | `days=7..90` | 每日交易数、预警数、金额 |
| GET | `/dashboard/distribution` | — | 高/中/低危数量与占比 |
| GET | `/dashboard/latest-alerts` | `limit=1..20` | 最新预警 |

## 3. 交易

| 方法 | 路径 | 参数 | 说明 |
|---|---|---|---|
| GET | `/transactions` | `page/page_size/date_from/date_to/min_amount/max_amount/channel/direction/risk_level/q/sort` | `sort=ts_desc/ts_asc/amount_desc/risk_desc` |
| GET | `/transactions/{txn_id}` | 可选 `account_id` | 交易详情 + 风险分 + 关联预警；`txn_id` 撞号时用 `account_id` 指定，未指定则返回最早一笔 |
| GET | `/transactions/{txn_id}/risk` | 可选 `account_id` | 风险分 + 因子 + 提示；未指定 `account_id` 时取该 ID 下分数最高的一笔 |

交易列表项：

```json
{
  "txn_id": "e3143db4-...",
  "account_id": "dae25466-...",
  "ts_initiated": "2024-01-01T17:48:17",
  "amount": 15609.3271,
  "currency": "USD",
  "direction": "inbound",
  "channel": "ach",
  "category": "salary",
  "counterparty_name": "Employer",
  "counterparty_country": "US",
  "risk_score": 0.759661,
  "risk_level": "mid"
}
```

## 4. 预警与卷宗

| 方法 | 路径 | 参数 | 说明 |
|---|---|---|---|
| GET | `/alerts` | `page/page_size/risk_level/status/date_from/date_to/q/sort` | `sort=priority/risk_desc/time_desc` |
| GET | `/alerts/{alert_id}` | `days=7..90` | 交易 + 8 因子 + 时间线 |
| GET | `/alerts/{alert_id}/factors` | — | 8 行因子 |
| GET | `/alerts/{alert_id}/timeline` | `days=7..90` | 每日笔数/金额，`has_alert` 标记告警日 |
| GET | `/alerts/{alert_id}/flow` | — | 账户→类别→对手方资金流向 |
| PATCH | `/alerts/{alert_id}/status` | `{status,note?,assignee?}` | `pending/confirmed/dismissed`，记审计 |

卷宗响应（节选）：

```json
{
  "alert_id": "ALT-6E4E1D08EB38",
  "txn_id": "e3143db4-...",
  "account_id": "dae25466-...",
  "risk_score": 0.759661,
  "risk_level": "mid",
  "priority": 1,
  "tags": ["近30天金额Z分数", "近24小时对手方数"],
  "status": "pending",
  "summary": "账户 dae25466 单笔 15,609.33 USD……",
  "txn": { "txn_id": "...", "amount": 15609.3271, "risk": { "model_score": 0.9995, "rule_score": 0.2 } },
  "factors": [
    { "rank": 1, "feature": "velocity_features.amount_zscore", "feature_label": "近30天金额Z分数", "value": 322.1, "shap_value": 3.0575, "direction": "up" }
  ],
  "timeline": [
    { "date": "2024-01-01", "count": 3, "amount": 15924.67, "has_alert": true }
  ]
}
```

因子 `direction`：`up` 推高可疑、`down` 压低可疑；`shap_value` 单位是 log-odds。

## 5. 报告

| 方法 | 路径 | 参数 | 说明 |
|---|---|---|---|
| POST | `/reports` | `{alert_id,report_type="alert"}` | 生成 PDF，返回 `report_id/status` |
| GET | `/reports` | `page/page_size/alert_id/status` | 报告列表 |
| GET | `/reports/{report_id}` | — | 报告元数据 |
| GET | `/reports/{report_id}/pdf` | — | 下载 PDF（`application/pdf`） |

报告 8 段：报告头、账户信息、交易摘要、证据链、风险因子、初步分析、处置建议、声明。中文字体按 `PDF_FONT_PATH` → `frontend/assets/fonts/NotoSansSC-Regular.otf` → 系统微软雅黑/黑体/宋体 → `STSong-Light` 依次回退。

## 6. 导出

| 方法 | 路径 | 参数 | 说明 |
|---|---|---|---|
| GET | `/export/transactions.csv` | 同交易筛选 | UTF-8 BOM，流式 |
| GET | `/export/alerts.csv` | 同预警筛选 | UTF-8 BOM，流式 |

## 7. 安全边界

- 响应模型显式列出字段，`is_suspicious`、`suspicion_reason`、`case_id`、`is_false_positive` 不进任何 API。
- 查询全部走 SQLAlchemy 参数绑定。
- 密码 PBKDF2-SHA256（21 万次），不落明文。
- 审计动作：`login`、`view`、`dispose`、`export`；报告生成/下载记 `export`。

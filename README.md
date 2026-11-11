# `feat/report-pdf`

把预警卷宗落成 8 段式 PDF，并提供报告列表/预览/下载。D4–D6 完成，字体按多级回退，保证 Linux 容器里中文不出现方块。

## 文件

- `backend/app/services/report_pdf.py`：reportlab Platypus 排版，8 段：报告头、账户信息、交易摘要、证据链、风险因子、初步分析、处置建议、声明。
- `backend/app/api/reports.py`：生成、列表、元数据、PDF 下载；生成/下载写审计。
- `frontend/reports.html` + `frontend/js/reports.js`：按预警 ID 生成、列表筛选、预览、下载。

## 接口

```text
POST /api/reports              {alert_id, report_type="alert"}  → {report_id, status}
GET  /api/reports?page&page_size&alert_id&status
GET  /api/reports/{report_id}
GET  /api/reports/{report_id}/pdf
```

生成是同步的：创建 `report` 行 → 拼数据 → 出 PDF → 状态 `generated`；失败置 `failed` 并保留错误信息。PDF 落在 `outputs/reports/`（不进 git）。

## 字体回退

`PDF_FONT_PATH` → `frontend/assets/fonts/NotoSansSC-Regular.otf` → `C:/Windows/Fonts/msyh.ttc`/`simhei.ttf`/`simsun.ttc` → Linux Noto CJK → `STSong-Light`。

部署到 Linux 时优先在镜像里装 `fonts-noto-cjk`（Dockerfile 已加），或把字体放到 `frontend/assets/fonts/` 并设 `PDF_FONT_PATH`。验证方式：下载 PDF 打开第一页，中文标题和表格不能是方块。

## 内容口径

- 报告正文只用 `report + alert + alert_factor + txn + risk_score`，不读 `eval_label`。
- “证据链”同时列命中规则和 8 条 SHAP 因子；没有规则命中时写“未命中硬规则，由模型排序入队”。
- 每份报告固定带声明：“辅助分析，不构成定性结论；数据为合成数据”。
- 样例 PDF：本地跑一次 `POST /api/reports` 后从 `outputs/reports/` 取，仓库不提交。

## 交接给 A

- 服务器上第一件事是下载一份 PDF 看中文；字体失败时 PDF 仍能生成，但会退到 `STSong-Light` 或出现方块。
- 报告列表按 `created_at` 倒序；A 的总览页如果要放“最近报告”，直接复用 `GET /api/reports?page_size=5`。
- 报告状态只在 `generating/generated/failed` 三态内，阶段二再加草稿/已确认。

# `feat/ml-batch`

把原来的 `03_train_models.py` 拆成可复用链路，跑出 `xgb-v1` 和全量预警队列。D2 拆特征/训练，D3 批量打分并写 `alert`、`alert_factor`，D3 下午补模型卡和单测。

## 文件

```text
backend/ml/config.py                 14 特征、XGB 超参、阈值、8 条规则
backend/ml/feature_builder.py        读 parquet、编码、特征表、冻结映射
backend/ml/train.py                  四模型对比 + XGB 产物 + 两套切分
backend/ml/score_batch.py            748k 批量打分、规则分、入队、SHAP top8
backend/ml/experiments/train_compare.py  原 03 脚本，改 Agg 后端和相对路径
backend/ml/tests/test_feature_builder.py 确定性、未见类别、缺失值三个用例
artifacts/xgb_model.json             生产模型（全量重训）
artifacts/feature_meta.json          特征顺序 + 类别映射 + 中文标签
artifacts/metrics.json               两套切分指标、Top-K、数据口径
artifacts/model_comparison.csv       四模型指标表
artifacts/topk_precision.csv         Top-K 命中
artifacts/pr_curve.json              PR 曲线
model_card.md                        模型卡（用途、指标、缺陷、复现）
```

## 跑起来

```bash
python -m backend.ml.train
python -m backend.ml.score_batch --parquet data/raw/train-00000-of-00002.parquet data/raw/train-00001-of-00002.parquet --reset
```

全量训练在本机约几分钟；`score_batch` 要写 748,842 行 `risk_score`，SQLite 下是分钟级。只想冒烟可加 `--max-rows 30000`。

## 交接要点

- 先确认 A 的 ETL 已把 `txn` 灌到 748,842 行，再跑 `score_batch`；否则会提示“候选交易不在 txn 表中”。
- 验收 SQL：`select count(*) from alert;`（应 ≥3,000）、`select alert_id,count(*) from alert_factor group by 1 having count(*)<>8;`（应为空）。
- `feature_meta.json` 与 `config.py::MODEL_FEATURES` 顺序必须一致，否则打分前会直接抛错。
- `model_card.md` 里同时写了原始 748,869/411 和去重 748,842/384 两套口径，对外引用前核对，不要混用。
- 训练/打分会吃 CPU，笔记本请接电源再跑。

## 红线

真值字段只进 `eval_label`，不参与特征、不参与排序、不生成预警状态。处置状态是哈希种子 85% 待处理 / 15% 已处置。
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

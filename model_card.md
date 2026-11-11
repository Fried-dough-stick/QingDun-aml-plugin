# 模型卡 · `xgb-v1`

> 青盾 2.0 反洗钱风险打分模型。只用于课程大创演示与合成数据研究，不对真实客户或交易作任何法律定性。

## 1. 用途

- 输入一笔交易的 14 个字段（9 个账户速度特征 + `mcc` + `spoofing_intensity` + `channel` + `direction` + `is_authorized`）。
- 输出 `model_score ∈ [0,1]`，再与规则分合成 `final_score = 0.3 * rule_score + 0.7 * model_score`。
- 用途是**排序**：把更值得人工复核的交易排到预警队列前面，不是自动判定可疑。
- 风险等级只看综合分：`high ≥ 0.8`、`mid ≥ 0.5`、其余 `low`。等级与 `is_suspicious` 等真值字段无关。

## 2. 数据

来源：VynFi AML-100K 合成个人卡交易（两份 parquet）。

| 口径 | 数值 | 说明 |
|---|---|---|
| 原始行数 | 748,869 | 两份 parquet 直接相加 |
| 去重后行数 | 748,842 | 按 `transaction_id` 去重，27 条重复 |
| 账户数 | 1,311 | |
| 可疑交易（原始） | 411 | 0.055% |
| 可疑交易（去重后） | 384 | 入库 `eval_label` 的口径 |
| 可疑账户 | 8 | |
| case / 手法 | 11 个 case / 7 类手法 | `account_takeover` 165、`authorized_push_payment` 117、`first_party_fraud` 53、`money_mule` 38、`layering` 5、`structuring` 4、`funnel_account` 2（去重后） |
| 时间范围 | 2024-01-01 08:01 ～ 2025-01-01 21:59 (UTC) | |
| `is_false_positive` | 37,419 条 | 只进 `eval_label` |

**原始与去重的差异必须写进论文和答辩**：所有建模、指标、入库都以去重后的 748,842 / 384 为准；引用 748,869 / 411 时说明这是未去重的原始行数。两个数字都对，但不能混着用。

真值字段（`is_suspicious`、`suspicion_reason`、`case_id`、`is_false_positive`）只进 `eval_label` 表，不参与特征、不参与入队、不由 API 返回、不在页面展示。处置状态用哈希种子生成 85% 待处理 / 15% 已处置，不按真值造。

## 3. 特征

| 组 | 字段 |
|---|---|
| 速度（9） | `txn_count_1h`、`txn_count_24h`、`txn_count_7d`、`txn_count_30d`、`amount_sum_24h`、`amount_max_24h`、`amount_zscore`、`unique_counterparties_24h`、`unique_countries_7d` |
| 商户 | `mcc` |
| 环境 | `spoofing_intensity` |
| 类别（3） | `channel`、`direction`、`is_authorized` |

- 类别编码 `LabelEncoder` 只在训练集 `fit`；映射冻结在 `artifacts/feature_meta.json`；推理遇到未见类别映射 `-1`；特征顺序固定为 `backend/ml/config.py::MODEL_FEATURES`。
- 生产模型用全量数据重训一次，编码映射也来自全量数据。这是**有意的偏离**：线上只有一份映射，无法再区分训练/测试。分组切分的评估模型只用训练集编码，指标不受影响。

## 4. 训练与评估

- 模型：XGBoost `n_estimators=200, max_depth=4, learning_rate=0.1, tree_method=hist, random_state=42`。
- 主评估：`GroupShuffleSplit(groups=account_id)`，529,214 训练 / 219,628 测试，避免同一账户跨集泄漏。
- 副评估：时间切分，`≤2024-05-31` 训练（302,605 行）、之后测试（446,237 行）。
- 类别不平衡：不加 SMOTE；四模型对比统一用默认权重。分类阈值固定 0.5，业务等级另按综合分 0.8/0.5 划分。
- 对照模型：逻辑回归、随机森林、MLP（`64` 隐层），同一套特征与切分。

## 5. 指标（分组切分，测试集 219,628 行 / 267 条可疑）

| 模型 | F1 | AUC | PR-AUC | MCC |
|---|---|---|---|---|
| 逻辑回归 | 0.0029 | 0.5671 | 0.0014 | 0.0045 |
| 随机森林 | 0.0000 | 0.5017 | 0.0013 | -0.0007 |
| **XGBoost** | **0.0025** | **0.6040** | **0.0018** | **0.0004** |
| MLP | 0.0000 | 0.4975 | 0.0012 | 0.0000 |

时间切分（XGBoost）：F1 0.0019 / AUC 0.6874 / PR-AUC 0.0008 / MCC 0.0088。

指标低是数据本身决定的：可疑率 0.051%，训练集里只有约 5 个可疑账户，树模型学不到可泛化的模式。`0.5` 阈值下的 F1/PR 没有业务意义，Top-K 才是业务口径：

| K | 命中可疑 | 精确率 | 召回率 | 随机抽取期望命中 |
|---|---|---|---|---|
| 50 | 0 | 0.0% | 0.00% | 0.06 |
| 100 | 0 | 0.0% | 0.00% | 0.12 |
| 200 | 0 | 0.0% | 0.00% | 0.24 |
| 500 | 0 | 0.0% | 0.00% | 0.61 |
| 1,000 | 0 | 0.0% | 0.00% | 1.22 |
| 2,000 | 3 | 0.15% | 1.12% | 2.43 |
| 5,000 | 6 | 0.12% | 2.25% | 6.08 |

**必须如实说：在这个切分上，模型排序前 2,000 只命中 3 条，前 5,000 命中 6 条，与随机抽取的期望（2.4 / 6.1）基本一致，没有可证明的排序增益。** AUC 0.60 略高于 0.5，但 Top-K 没有转化为业务价值。这不是接口写错，是 8 个可疑账户、384 条正样本、合成数据信号弱共同导致的。

产品上的兜底是**规则分**：未授权、短时高频、大额、Z 分数、多对手方这些硬条件仍能把明显异常排到前面；模型分只作为 `final_score` 的一部分参与排序，不能单独宣称“模型能识别洗钱”。

另需注意：线上打分用的是**全量重训模型**，对训练过的交易属于样本内打分，队列靠前不代表泛化能力；泛化结论只看上面的分组/时间切分。

## 6. 打分与入队

- `rule_score`：8 条硬规则加权求和后截断到 1：

| 规则 | 条件 | 权重 |
|---|---|---|
| 未授权交易 | `is_authorized = 0` | 0.35 |
| 1 小时频次 | `txn_count_1h ≥ 5` | 0.25 |
| 设备/环境仿冒 | `spoofing_intensity > 0` | 0.20 |
| 24 小时频次 | `txn_count_24h ≥ 8` | 0.20 |
| 30 天金额 Z 分数 | `amount_zscore ≥ 5` | 0.20 |
| 24 小时金额合计 | `amount_sum_24h ≥ 10,000` | 0.15 |
| 24 小时单笔峰值 | `amount_max_24h ≥ 5,000` | 0.15 |
| 24 小时对手方数 | `unique_counterparties_24h ≥ 6` | 0.15 |

- 入队：`final_score` Top 3,000 ∪ `rule_score ≥ 0.67`，两者取并集去重。
- 等级阈值按计划保留：`high ≥ 0.8`、`mid ≥ 0.5`。注意规则权重只有 0.3，规则全中也只能到 0.3，**高危必须由模型分推高**；本批全量打分实际得到 22 条 high / 2,978 条 mid，队列里没有 low（队列本身就是高分切片）。
- 每条预警取 `pred_contribs` 绝对值 Top 8 写入 `alert_factor`，`direction` 由贡献正负决定。
- 优先级按综合分降序；`alert_id = "ALT-" + sha1(txn_id)[:12]`，确定性生成，重跑不漂移。

## 7. 解释口径

- 因子值是**编码后的模型输入**：`channel`、`direction`、`is_authorized` 存的是类别编码（如 0/1/2），不是原始中文。阶段二再把编码翻译回文字。
- `alert_factor` 里的 `shap_value` 是 XGBoost `pred_contribs`（TreeSHAP）在原始特征上的边际贡献，单位为 log-odds，不是概率。
- `feature_meta.json` / `metrics.json` 里的特征重要性若用 `gain`，与 SHAP 不是同一口径，不能互相替代，报告里要注明用的是哪一种。

## 8. 已知缺陷

1. 信号弱：AUC 0.60，Top-2,000 仅命中 3 条，排序接近随机；演示中的排序价值主要来自规则分，不能把模型当识别器。
2. 类别编码直接当数值喂给树模型，`channel` 等存在虚假序关系；阶段二可换 one-hot 或目标编码。
3. 生产模型在全量数据上重训，线上打分是样本内打分，无法再做真正的样本外评估；泛化指标只能引用分组切分结果。
4. 时点特征由离线 parquet 直接计算，线上新增交易需要 A 的 ETL 同步更新速度特征，否则模型输入会滞后。
5. 未做概率校准，`model_score` 只能排序，不能解释为“可疑概率”。
6. 原始/去重两套计数并存，任何材料引用前必须核对口径。
7. 未评估公平性（账户类型、地区、金额段），演示版不涉及真实人群。

## 9. 复现

```bash
python -m backend.ml.train            # 训练 + 评估 + 写 artifacts/
python -m backend.ml.score_batch --reset   # 批量打分 + 入队
python -m backend.ml.experiments.train_compare  # 四模型对比图（matplotlib Agg）
```

产物：`artifacts/xgb_model.json`、`feature_meta.json`、`metrics.json`（含两套切分与 Top-K）、`model_comparison.csv`、`topk_precision.csv`、`pr_curve.json`。

## 10. 使用限制

- 仅限 VynFi 合成数据、课程演示和离线评测。
- 不得把模型输出当作可疑结论、监管报送依据或对客户的指控。
- 任何对外材料引用指标时，同时给出基率（0.055%）和 Top-K 口径。

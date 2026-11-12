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
| 行数 | 748,869 | 两份 parquet 直接相加，也是入库口径 |
| 账户数 | 1,311 | |
| 可疑交易 | 411 | 0.0549% |
| 可疑账户 | 12 | |
| case / 手法 | 12 个 case / 7 类手法 | `account_takeover` 165、`authorized_push_payment` 117、`first_party_fraud` 53、`money_mule` 49、`structuring` 11、`funnel_account` 11、`layering` 5 |
| 时间范围 | 2024-01-01 08:01 ～ 2025-01-01 21:59 (UTC) | |
| `is_false_positive` | 37,419 条 | 只进 `eval_label` |
| `spoofing_intensity` 非空 | 36 行 | 36 行全部是可疑交易，其余 748,833 行按 0 处理 |
| 币种 | 8 种（USD 610,435 行） | `fx_rate` 全空，金额跨币种直接相加只作演示，不是折算后的总额 |
| `counterparty.country` 非空 | 30 行 | 交易页不要依赖该字段；`device_id` / `ip_address` 非空也只有 108,541 / 54,336 行 |

**本版只有一套口径：748,869 行 / 411 条可疑。** 有 11 个 `transaction_id` 被 3–4 个账户复用，共 38 行（比唯一 ID 多 27 行），38 行全部为可疑交易、跨 5 个 case、落在 5 个账户上——它们是不同账户上的不同欺诈事件，不是重复抓取。若按 `transaction_id` 去重，会丢掉 27 条可疑、4 个可疑账户、4 个 case，并让同一账户的交易跨训练/测试集，所以主键统一为 `(txn_id, account_id)`，建模、指标、入库、API 都按配对处理。旧材料里的 748,842 / 384 / 8 / 11 是去重口径，**不要再引用**。

真值字段（`is_suspicious`、`suspicion_reason`、`case_id`、`is_false_positive`）只进 `eval_label` 表，不参与特征、不参与入队、不由 API 返回、不在页面展示。处置状态用哈希种子生成 85% 待处理 / 15% 已处置，不按真值造。

## 3. 特征

| 组 | 字段 |
|---|---|
| 速度（9） | `txn_count_1h`、`txn_count_24h`、`txn_count_7d`、`txn_count_30d`、`amount_sum_24h`、`amount_max_24h`、`amount_zscore`、`unique_counterparties_24h`、`unique_countries_7d` |
| 商户 | `mcc` |
| 环境 | `spoofing_intensity` |
| 类别（3） | `channel`、`direction`、`is_authorized` |

- 类别编码 `LabelEncoder` 只在训练集 `fit`；映射冻结在 `artifacts/feature_meta.json`；推理遇到未见类别映射 `-1`；特征顺序固定为 `backend/ml/config.py::MODEL_FEATURES`。
- `spoofing_intensity` 只有 36 行非空，且这 36 行全部是可疑交易（`money_mule` 32 行、`structuring` 4 行），全部落在分组切分的训练账户里，测试集为 0 行。它更像是合成数据自带的欺诈标注代理，不是稳定的行为特征：线上样本内排序会被它推高，但分组切分那 6 条 Top-50 命中与它无关。
- 原始数据有 14 个速度特征，模型只用 9 个；`amount_sum_7d`、`amount_sum_30d`、`unique_counterparties_7d`、`avg_amount_30d`、`std_amount_30d` 存进 `txn` 但不进模型。
- 生产模型用全量数据重训一次，编码映射也来自全量数据。这是**有意的偏离**：线上只有一份映射，无法再区分训练/测试。分组切分的评估模型只用训练集编码，指标不受影响。

## 4. 训练与评估

- 模型：XGBoost `n_estimators=200, max_depth=4, learning_rate=0.1, tree_method=hist, random_state=42`。
- 主评估：`GroupShuffleSplit(groups=account_id)`，529,236 训练 / 219,633 测试（测试集 272 条可疑），避免同一账户跨集泄漏。
- 副评估：时间切分，`≤2024-05-31` 训练（302,632 行）、之后测试（446,237 行）。
- 类别不平衡：不加 SMOTE；四模型对比统一用默认权重。分类阈值固定 0.5，业务等级另按综合分 0.8/0.5 划分。
- 对照模型：逻辑回归、随机森林、MLP（`64` 隐层），同一套特征与切分。

## 5. 指标（分组切分，测试集 219,633 行 / 272 条可疑）

| 模型 | F1 | AUC | PR-AUC | MCC |
|---|---|---|---|---|
| 逻辑回归 | 0.0029 | 0.5723 | 0.0036 | 0.0034 |
| 随机森林 | 0.0055 | 0.5123 | 0.0021 | 0.0055 |
| **XGBoost** | **0.0043** | **0.6217** | **0.0240** | **0.0043** |
| MLP | 0.0000 | 0.4908 | 0.0012 | 0.0000 |

时间切分（XGBoost）：F1 0.0019 / AUC 0.6932 / PR-AUC 0.0007 / MCC 0.0083。

指标低是数据本身决定的：可疑率 0.055%，训练集里只有少数可疑账户，树模型学不到可泛化的模式。`0.5` 阈值下的 F1/PR 没有业务意义，Top-K 才是业务口径：

| K | 命中可疑 | 精确率 | 召回率 | 随机抽取期望命中 |
|---|---|---|---|---|
| 50 | 6 | 12.0% | 2.21% | 0.06 |
| 100 | 6 | 6.0% | 2.21% | 0.12 |
| 200 | 6 | 3.0% | 2.21% | 0.25 |
| 500 | 6 | 1.2% | 2.21% | 0.62 |
| 1,000 | 6 | 0.6% | 2.21% | 1.24 |
| 2,000 | 6 | 0.3% | 2.21% | 2.48 |
| 5,000 | 13 | 0.26% | 4.78% | 6.19 |

**必须如实说：模型排序前 50 命中 6 条，约为随机期望（0.06）的 100 倍，说明极端头部有信号；但 K 从 50 拉到 2,000，命中数一直是 6 条，头部以外没有增益；K=5,000 命中 13 条，约为随机期望（6.2）的 2.1 倍。** AUC 0.62 说明有排序信息，但能捞出的可疑交易集中在极窄的头部，远不足以支撑“模型能识别洗钱”。这不是接口写错，是 12 个可疑账户、411 条正样本、合成数据信号弱共同导致的。

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

> 本数据集 `is_authorized` 恒为 `True`、`status` 恒为 `completed`，"未授权交易"规则从未触发；它保留是为了兼容真实数据，不能把它写成本数据集的检出能力。

- 入队：`final_score` Top 3,000 ∪ `rule_score ≥ 0.67`，两者取并集去重。
- 等级阈值按计划保留：`high ≥ 0.8`、`mid ≥ 0.5`。注意规则权重只有 0.3，规则全中也只能到 0.3，**高危必须由模型分推高**；本批全量打分实际得到 25 条 high / 2,975 条 mid，队列里没有 low（队列本身就是高分切片）。
- 每条预警取 `pred_contribs` 绝对值 Top 8 写入 `alert_factor`，`direction` 由贡献正负决定。
- 优先级按综合分降序；`alert_id = "ALT-" + sha1(f"{txn_id}:{account_id}")[:12]`，确定性生成，重跑不漂移；`transaction_id` 撞号时必须把 `account_id` 一起哈希，否则同 ID 的不同交易会被合并成一条预警。

## 7. 解释口径

- 因子值是**编码后的模型输入**：`channel`、`direction`、`is_authorized` 存的是类别编码（如 0/1/2），不是原始中文。阶段二再把编码翻译回文字。
- `alert_factor` 里的 `shap_value` 是 XGBoost `pred_contribs`（TreeSHAP）在原始特征上的边际贡献，单位为 log-odds，不是概率。
- `feature_meta.json` / `metrics.json` 里的特征重要性若用 `gain`，与 SHAP 不是同一口径，不能互相替代，报告里要注明用的是哪一种。

## 8. 已知缺陷

1. 信号弱且集中：AUC 0.62，可疑只出现在排序最前面的几十条；K 从 50 扩到 2,000 命中数不增加，K=5,000 也仅 13 条。演示中的排序价值主要来自规则分，不能把模型当识别器。
2. 类别编码直接当数值喂给树模型，`channel` 等存在虚假序关系；阶段二可换 one-hot 或目标编码。
3. 生产模型在全量数据上重训，线上打分是样本内打分，无法再做真正的样本外评估；泛化指标只能引用分组切分结果。
4. 时点特征由离线 parquet 直接计算，线上新增交易需要 A 的 ETL 同步更新速度特征，否则模型输入会滞后。
5. 未做概率校准，`model_score` 只能排序，不能解释为“可疑概率”。
6. 11 个 `transaction_id` 在多个账户下复用：交易详情/风险接口需带可选 `account_id` 才能唯一定位，不带时详情返回最早一笔、风险返回分数最高一笔；列表、预警、导出都已按 `(txn_id, account_id)` 配对。
7. `spoofing_intensity` 在合成数据里只出现在可疑交易上（36/36），构成标注代理/泄漏风险；严谨的泛化评估应剔除该特征重训，本版为了和原始设计对齐保留。
8. 未评估公平性（账户类型、地区、金额段），演示版不涉及真实人群。

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

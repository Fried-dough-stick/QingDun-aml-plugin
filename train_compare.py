import pandas as pd
import os
from pathlib import Path
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from xgboost import XGBClassifier
from sklearn.neural_network import MLPClassifier
from sklearn.metrics import f1_score, roc_auc_score, average_precision_score, matthews_corrcoef, precision_recall_curve
from imblearn.over_sampling import SMOTE
import warnings
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.preprocessing import LabelEncoder
warnings.filterwarnings('ignore')

from backend.ml.feature_builder import load_dataset

OUTPUT_DIR = Path(__file__).resolve().parents[3] / "outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
os.chdir(OUTPUT_DIR)
plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus'] = False

print("1. 正在加载清洗好的数据...")
df = load_dataset()

y = df['is_suspicious']
X = df.drop(columns=['is_suspicious', 'is_spoofed', 'is_false_positive', 'scenario_sequence'], errors='ignore')

# 3. 对分类列做 LabelEncoder 编码
categorical_cols = ['channel','direction','counterparty_type']
for col in categorical_cols:
    if col in X.columns:                 # ← 检查列是否在 X 中
        le = LabelEncoder()
        X[col] = le.fit_transform(X[col])

# 3. 过滤掉剩余的字符串列，模型只认识数字
X = X.select_dtypes(include=['number', 'bool'])
# 把所有数值列的剩余空值统一填 0
X = X.fillna(0)

# 把 True/False 转成 1/0
for col in X.columns:
    if X[col].dtype == 'bool':
        X[col] = X[col].astype(int)

print(f"特征数量：{X.shape[1]}，样本数量：{X.shape[0]}")

# 4. 划分训练集和测试集 (7:3)
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.3, stratify=y, random_state=42
)

print("5. 正在对训练集进行 SMOTE 平衡...")
smote = SMOTE(random_state=42)
X_train_bal, y_train_bal = smote.fit_resample(X_train, y_train)

print("平衡后训练集可疑率：", y_train_bal.mean())

# 6. 定义评估函数
def evaluate(name, y_true, y_pred, y_prob):
    return {
        "模型": name,
        "F1分数": round(f1_score(y_true, y_pred), 4),
        "AUC": round(roc_auc_score(y_true, y_prob), 4),
        "PR_AUC": round(average_precision_score(y_true, y_prob), 4),
        "MCC": round(matthews_corrcoef(y_true, y_pred), 4)
    }

results = []

# 7. 训练模型1：逻辑回归
print("\n正在训练：逻辑回归...")
lr = LogisticRegression(class_weight='balanced', max_iter=1000, random_state=42)
lr.fit(X_train_bal, y_train_bal)
results.append(evaluate("逻辑回归", y_test, lr.predict(X_test), lr.predict_proba(X_test)[:,1]))

# 8. 训练模型2：随机森林
print("正在训练：随机森林...")
rf = RandomForestClassifier(n_estimators=100, class_weight='balanced', random_state=42, n_jobs=-1)
rf.fit(X_train_bal, y_train_bal)
results.append(evaluate("随机森林", y_test, rf.predict(X_test), rf.predict_proba(X_test)[:,1]))

# 9. 训练模型3：XGBoost
print("正在训练：XGBoost...")
scale_pos_weight = (y_train == 0).sum() / (y_train == 1).sum()
xgb = XGBClassifier(
    n_estimators=200, max_depth=4, learning_rate=0.1,
    scale_pos_weight=scale_pos_weight, eval_metric='logloss', random_state=42
)
xgb.fit(X_train, y_train)
results.append(evaluate("XGBoost", y_test, xgb.predict(X_test), xgb.predict_proba(X_test)[:,1]))

feature_importances = pd.Series(xgb.feature_importances_, index=X.columns)
top_features = feature_importances.nlargest(15)

plt.figure(figsize=(10, 6))
sns.barplot(x=top_features.values, y=top_features.index)
plt.title('Top 15 Feature Importances (XGBoost)')
plt.xlabel('Importance Score')
plt.tight_layout()
plt.savefig('outputs/feature_importance.png') # 保存下来！报告里要用！
plt.close()


##PR曲线
y_prob = xgb.predict_proba(X_test)[:, 1]
precision, recall, _ = precision_recall_curve(y_test, y_prob)
ap_score = average_precision_score(y_test, y_prob)

plt.figure(figsize=(8, 6))
plt.plot(recall, precision, label=f'XGBoost (AP = {ap_score:.4f})', color='darkorange', lw=2)
plt.xlabel('Recall (召回率)')
plt.ylabel('Precision (精确率)')
plt.title('Precision-Recall Curve (极度不平衡数据)')
plt.legend(loc="best")
plt.grid(alpha=0.3)
plt.savefig('outputs/pr_curve.png')
plt.close()


# ============================================================================
# Top-K 排序精度分析（论文 4.1 / 4.3 可补充：模型在实际业务中"只看前 K 条"的命中效果）
# 意义：PR-AUC 是全局排序质量，Top-K 更贴近银行实际工作流——
#       反洗钱团队每天只能人工核查有限笔数，K 就是那个核查预算。
# ============================================================================
y_true_arr = np.asarray(y_test)
total_suspicious = int(y_true_arr.sum())
print(f"\n===== Top-K 排序精度（测试集 {len(y_true_arr)} 条，可疑 {total_suspicious} 条）=====")
topk_rows = []
for k in [50, 100, 200, 500, 1000, 2000, 5000]:
    topk_idx = np.argsort(y_prob)[::-1][:k]
    hit = int(y_true_arr[topk_idx].sum())
    rec = hit / total_suspicious
    prec = hit / k
    topk_rows.append({"K": k, "命中可疑数": hit, "召回率": round(rec, 4), "精确率": round(prec, 4)})
    print(f"  K={k:>5}  命中={hit:>3}  召回率={rec:.4f}  精确率={prec:.4f}")

topk_df = pd.DataFrame(topk_rows)
topk_df.to_csv("outputs/topk_precision.csv", index=False, encoding="utf-8-sig")
print("Top-K 结果已保存至 outputs/topk_precision.csv\n")


# ============================================================================
# 12.5 稳健性检验：异常值截尾（winsorization）
#     目的：论文 3.2 只写了"缺失值填 0"，未说明异常值如何处理。金额类 velocity
#     特征存在极端值，审稿人常追问"你的排序结论是否被个别极端账户带偏"。
#     做法：对三个关键 velocity 特征按【训练集】1%/99% 分位数做截尾（截尾分位数
#     必须来自训练集，测试集复用同一分位数，避免数据泄漏），重训 XGBoost，
#     对比截尾前后的 AUC / PR-AUC / F1 与 Top-50 命中。
#     产出：outputs/winsorize_robustness.csv（贴进论文 4.1 后的"稳健性检验"小表）
# ============================================================================
print("\n===== 12.5 稳健性检验：异常值截尾（1%/99% winsorization）=====")
winsor_cols = ['velocity_features.txn_count_30d',
               'velocity_features.std_amount_30d',
               'velocity_features.amount_zscore']

def _metrics(y_true, y_prob, y_pred):
    return {
        'F1': round(f1_score(y_true, y_pred), 4),
        'AUC': round(roc_auc_score(y_true, y_prob), 4),
        'PR_AUC': round(average_precision_score(y_true, y_prob), 4),
        'MCC': round(matthews_corrcoef(y_true, y_pred), 4),
        'Top50命中': int(np.asarray(y_true)[np.argsort(y_prob)[::-1][:50]].sum()),
    }

# 基线：直接复用上面已训练的 xgb（同一环境、同一超参，保证前后可比）
base_row = _metrics(y_test, xgb.predict_proba(X_test)[:, 1], xgb.predict(X_test))

# 截尾：分位数取自训练集，测试集复用同一分位数
X_train_w = X_train.copy()
X_test_w = X_test.copy()
for c in winsor_cols:
    lo = X_train[c].quantile(0.01)
    hi = X_train[c].quantile(0.99)
    X_train_w[c] = X_train_w[c].clip(lo, hi)
    X_test_w[c] = X_test_w[c].clip(lo, hi)

xgb_w = XGBClassifier(
    n_estimators=200, max_depth=4, learning_rate=0.1,
    scale_pos_weight=scale_pos_weight, eval_metric='logloss', random_state=42
)
xgb_w.fit(X_train_w, y_train)
wins_row = _metrics(y_test, xgb_w.predict_proba(X_test_w)[:, 1], xgb_w.predict(X_test_w))

rob_df = pd.DataFrame([base_row, wins_row], index=['截尾前(基线)', '截尾后(1%/99%)'])
rob_df.to_csv('outputs/winsorize_robustness.csv', encoding='utf-8-sig')
print(rob_df.to_string())
print("变化量（截尾后 − 截尾前）：",
      {k: round(wins_row[k] - base_row[k], 4) for k in ['F1', 'AUC', 'PR_AUC', 'MCC']})
print("稳健性检验结果已保存至 outputs/winsorize_robustness.csv\n")


# ============================================================================
# 13. SHAP 可解释性分析（放在 MLP 之前执行：SHAP 只依赖已训练好的 XGBoost，
#     MLP 是全程最慢的一步，先出图可省约 20 分钟等待）
#     产出：图9  全局 SHAP beeswarm（带方向，弥补 gain 重要性只有大小没有方向的缺陷）
#           图10 单样本 waterfall —— 真跑分样本（模型为什么判它可疑）
#           图11 单样本 waterfall —— 高频但正常的样本（"兼职发薪"画像，自证报告的核心证据）
#           图12 单样本 waterfall —— 正常却被打高分的样本（诚实呈现误伤风险）
#           附表 shap_mean_abs.csv / self_proof_evidence.csv（可直接贴进论文 4.2 与 5.4）
#
#     依赖：pip install "shap>=0.40"（装在你跑这个脚本的 conda 环境里）
#           注意：shap 在这里【只负责画图】。SHAP 值由 xgboost 原生
#           booster.predict(pred_contribs=True) 计算，绕开 shap.TreeExplainer
#           与 xgboost>=3 的 base_score 序列化不兼容问题。
#
#     读图口径（答辩必说，别说错）：
#         本项目的 XGBoost 是在【未过采样】数据 + scale_pos_weight 上训练的，
#         SHAP 值单位是 log-odds（对数发生比 / margin 空间），不是概率。
#         SHAP>0 推高可疑概率，SHAP<0 压低可疑概率；
#         base value = 模型截距（log-odds），base + 所有 SHAP 值之和
#         = 该样本的 raw margin，sigmoid 后即 predict_proba（代码里有自检）。
# ============================================================================
RUN_SHAP = True          # 只想重跑前面模型对比时改成 False
SHAP_SAMPLE_N = 900      # 参与 SHAP 计算的测试集样本数（越大越慢，14 特征 / 200 棵树时 900 约十几秒）
SHAP_MAX_DISPLAY = 14    # 图里最多显示的特征条数

if RUN_SHAP:
    try:
        import shap
    except ImportError:
        raise SystemExit(
            "\n[中止] 当前环境没有 shap。请先执行：pip install \"shap>=0.40\"\n"
            "       注意要装在你跑这个脚本的那个 conda 环境里，不是 base 也不是系统 Python。\n"
        )
    import joblib
    import xgboost as xgb_mod

    # shap 的 waterfall 柱内标签用 U+2212 数学负号，SimHei 没有该字形会显示成方框。
    # 实测：SimHei 打头会阻断 matplotlib 的逐字形回退，必须把 Microsoft YaHei 放第一位
    # （雅黑同时覆盖 U+2212 与中文）。段尾会还原成 SimHei，不影响你其他图的字体。
    _FONT_BACKUP = list(plt.rcParams['font.sans-serif'])
    plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans']

    # ---- 13.0 中文显示名（让图能直接放进中文论文，否则全是 velocity_features.xxx 长名字）----
    FEAT_LABELS = {
        'velocity_features.txn_count_1h': '1小时交易次数',
        'velocity_features.txn_count_24h': '24小时交易次数',
        'velocity_features.txn_count_7d': '7天交易次数',
        'velocity_features.txn_count_30d': '30天交易次数',
        'velocity_features.unique_counterparties_24h': '24小时对手方数',
        'velocity_features.unique_counterparties_7d': '7天对手方数',
        'velocity_features.unique_countries_7d': '7天国家数',
        'velocity_features.std_amount_30d': '30天金额标准差',
        'velocity_features.amount_zscore': '金额Z分数',
        'spoofing_intensity': '伪造强度',
        'mcc': '商户类别码MCC',
        'channel': '交易渠道',
        'direction': '交易方向',
        'is_authorized': '是否已授权',
    }

    print("\n===== 13. SHAP 可解释性分析 =====")
    joblib.dump(xgb, "outputs/xgb_model.pkl")   # 存下来，下次单独调 SHAP 不用重训四个模型

    # ---- 13.1 抽样：测试集里全部可疑样本 + 随机正常样本（保证少数类不丢）----
    y_test_arr = np.asarray(y_test).astype(int)
    idx_pos = np.where(y_test_arr == 1)[0]
    idx_neg = np.where(y_test_arr == 0)[0]
    n_neg = max(SHAP_SAMPLE_N - len(idx_pos), 100)
    rng = np.random.default_rng(42)
    idx_neg_s = rng.choice(idx_neg, size=min(n_neg, len(idx_neg)), replace=False)
    idx_shap = np.concatenate([idx_pos, idx_neg_s])

    X_shap = X_test.iloc[idx_shap].reset_index(drop=True)
    y_shap = y_test_arr[idx_shap]
    labels = [FEAT_LABELS.get(c, c) for c in X_shap.columns]
    print(f"可疑 {len(idx_pos)} 条 + 正常 {len(idx_neg_s)} 条，共 {len(X_shap)} 条参与 SHAP")
    print("模型实际使用的特征：", list(X_shap.columns))

    # ---- 13.2 计算 SHAP 值 ----
    # 用 xgboost 原生 TreeSHAP（booster.predict(pred_contribs=True)），不用 shap.TreeExplainer。
    # 原因：xgboost>=3 把 base_score 序列化成向量字符串 '[5E-1]'，shap<=0.49 的 TreeExplainer
    # 从 save_raw(ubj) 读该字段时 float() 会抛 ValueError（shap 已知问题）。
    # 原生路径不经过 shap 的模型加载器，同样是精确 TreeSHAP 解；shap 在这里只负责画图。
    dmat = xgb_mod.DMatrix(X_shap)
    contribs = np.asarray(xgb.get_booster().predict(dmat, pred_contribs=True), dtype=float)
    if contribs.ndim == 3:                   # 多输出时形如 (n, m+1, k)
        contribs = contribs[:, :, -1]
    sv = contribs[:, :-1]                    # 最后一列是 base value，单独取
    ev = float(contribs[:, -1].mean())
    print(f"sv.shape = {sv.shape}   base value（训练集平均 log-odds）= {ev:.4f}")

    # 可加性自检：base + ΣSHAP 还原模型 raw margin，sigmoid 后应等于 predict_proba。
    # 这步是图能不能用的前提，答辩被质疑"你的解释是真的吗"时可以直接甩这个数。
    recon = 1.0 / (1.0 + np.exp(-(ev + sv.sum(axis=1))))
    max_err = float(np.abs(recon - xgb.predict_proba(X_shap)[:, 1]).max())
    print(f"SHAP 可加性自检：max |sigmoid(base+ΣSHAP) - predict_proba| = {max_err:.3e}")
    assert max_err < 1e-6, "SHAP 值与模型输出不一致，图不能用"

    explanation = shap.Explanation(
        values=sv,
        base_values=ev,
        data=X_shap.to_numpy(dtype=float),
        feature_names=labels,
    )

    # ---- 13.3 图9：全局 SHAP beeswarm + mean|SHAP| 表 ----
    plt.figure(figsize=(10, 8))
    shap.plots.beeswarm(explanation, max_display=SHAP_MAX_DISPLAY, show=False)
    plt.title(' XGBoost 特征 SHAP 全局影响分布（单位：log-odds，红=取值高 蓝=取值低）', fontsize=11)
    plt.tight_layout()
    plt.savefig('outputs/shap_summary_beeswarm.png', dpi=200)
    plt.close()

    mean_abs = pd.Series(np.abs(sv).mean(axis=0), index=labels).sort_values(ascending=False)
    mean_abs.to_frame('mean_abs_SHAP(logodds)').to_csv('outputs/shap_mean_abs.csv', encoding='utf-8-sig')
    print("\nmean|SHAP| 排序（论文 4.2 可与 gain 重要性并列对照）：")
    print(mean_abs.round(4).to_string())

    # ---- 13.4 挑三个有故事的样本 ----
    prob_shap = xgb.predict_proba(X_shap)[:, 1]

    def arr(name, default=0.0):
        if name in X_shap.columns:
            return pd.to_numeric(X_shap[name], errors='coerce').fillna(default).to_numpy(float)
        print(f"  [提示] {name} 不在模型输入中，按常数 {default} 处理")
        return np.full(len(X_shap), default, float)

    c_txn30 = arr('velocity_features.txn_count_30d')
    c_txn24 = arr('velocity_features.txn_count_24h')
    c_cp7 = arr('velocity_features.unique_counterparties_7d')
    c_ctry7 = arr('velocity_features.unique_countries_7d')
    c_spoof = arr('spoofing_intensity')

    normal_mask = y_shap == 0
    suspicious_mask = y_shap == 1

    # (A) 真跑分样本：可疑样本里模型打分最高的 —— 证明模型抓对了什么
    idx_a_list = np.where(suspicious_mask)[0]
    i_a = idx_a_list[np.argmax(prob_shap[idx_a_list])] if len(idx_a_list) else int(np.argmax(prob_shap))

    # (B) 高频但正常样本：30天/24天交易频次在前 10%、无跨境、伪造强度低于中位数，
    #     在这些"看着像跑分其实正常"的样本里取模型打分最低的 —— 自证报告的理想画像
    thr_hi = np.percentile(c_txn30, 90)
    thr_spoof = np.median(c_spoof)
    mask_b = normal_mask & (c_txn30 >= thr_hi) & (c_ctry7 == 0) & (c_spoof <= thr_spoof)
    if mask_b.sum() == 0:
        mask_b = normal_mask & (c_txn30 >= np.percentile(c_txn30, 75))
        print("  [提示] 严格条件下的『高频正常』样本为空，已放宽到 30 天频次前 25%")
    if mask_b.sum() == 0:
        mask_b = normal_mask
        print("  [提示] 仍为空，退化为随机正常样本")
    idx_b_list = np.where(mask_b)[0]
    i_b = idx_b_list[np.argmin(prob_shap[idx_b_list])]

    # (C) 误伤风险样本：真实标签正常、但模型打分最高 —— 诚实呈现 PR-AUC 0.1379 的代价
    idx_n_all = np.where(normal_mask)[0]
    i_c = idx_n_all[np.argmax(prob_shap[idx_n_all])]

    picks = [
        (i_a, '跑分样本（真实可疑·模型高分）', 'shap_waterfall_suspicious.png'),
        (i_b, '高频正常样本（真实正常·模型低分，可自证）', 'shap_waterfall_normal_pass.png'),
        (i_c, '疑似误伤样本（真实正常·模型高分）', 'shap_waterfall_false_positive.png'),
    ]

    for i, desc, fname in picks:
        plt.figure(figsize=(10, 7))
        shap.plots.waterfall(explanation[i], max_display=SHAP_MAX_DISPLAY, show=False)
        plt.title(f'单样本 SHAP 归因 · {desc}\n'
                  f'可疑概率 = {prob_shap[i]:.4f}   base = {ev:.2f} → 该样本 margin = {ev + sv[i].sum():.2f} (log-odds)',
                  fontsize=11)
        plt.tight_layout()
        plt.savefig(f'outputs/{fname}', dpi=200)
        plt.close()

    # ---- 13.5 自证报告证据表：把 SHAP 变成论文 5.4 那个功能的数据底座 ----
    evidence_rows = []
    for i, desc, _ in picks:
        v = sv[i]
        order = np.argsort(-np.abs(v))[:6]
        for rank, j in enumerate(order, 1):
            evidence_rows.append({
                '样本类型': desc,
                '排名': rank,
                '特征': labels[j],
                '该账户取值': X_shap.iloc[i, j],
                'SHAP(logodds)': round(float(v[j]), 4),
                '作用方向': '推高可疑' if v[j] > 0 else '压低可疑',
            })
    ev_df = pd.DataFrame(evidence_rows)
    ev_df.to_csv('outputs/self_proof_evidence.csv', index=False, encoding='utf-8-sig')
    print("\n三类样本的 Top-6 SHAP 归因：")
    print(ev_df.to_string(index=False))

    # ---- 13.6 gain 重要性 vs SHAP 分歧诊断（论文 4.2 的护身符，务必看这段）----
    # 背景：XGBClassifier.feature_importances_ 默认是 gain（平均分裂增益）。
    # 一个只在极少数样本上非零、但那几次分裂能把样本近乎完全分开的特征，
    # gain 会排得很高，mean|SHAP| 却接近 0 —— 因为它对 99.9% 的样本没有贡献。
    # 本数据集里 spoofing_intensity 非零仅 36/748,869 条，正属于这种"稀疏决定性信号"。
    gain_imp = pd.Series(xgb.feature_importances_, index=list(X.columns)).reindex(X_shap.columns)
    # 注意：稀疏度/方差必须按【全量 X】算，不能按 SHAP 抽样算 ——
    # 抽样把可疑样本过采到 13.7%（真实 0.055%），会把 spoofing_intensity 这类
    # 只在可疑样本上非零的特征占比虚高近 300 倍。
    Xpop = X[X_shap.columns].to_numpy(dtype=float)
    diag = pd.DataFrame({
        'gain重要性': gain_imp.to_numpy(),
        'mean_abs_SHAP': np.abs(sv).mean(axis=0),
        '全量非零占比': (Xpop != 0).mean(axis=0),
        '全量取值种数': [len(np.unique(Xpop[:, k])) for k in range(Xpop.shape[1])],
    }, index=labels).sort_values('mean_abs_SHAP', ascending=False)
    g_rank = diag['gain重要性'].rank(ascending=False)
    s_rank = diag['mean_abs_SHAP'].rank(ascending=False)

    def _verdict(name, row):
        if row['mean_abs_SHAP'] < 1e-6:
            return 'SHAP≈0：模型对该特征几乎无贡献（取值退化/近乎常数），不可作为风险评分依据'
        if row['全量非零占比'] < 0.01 or row['全量取值种数'] <= 2:
            return '稀疏或低方差信号：绝大多数样本上不起作用，宜作"硬标记"而非连续健康分特征'
        if g_rank[name] <= 5 and s_rank[name] > 5:
            return 'gain 高但 SHAP 低：平均增益被少数高分裂放大，对连续风险的贡献有限'
        return '稠密主导特征：可作为银行卡健康分的主特征'

    diag['判读'] = [_verdict(n, diag.loc[n]) for n in diag.index]
    diag.round(6).to_csv('outputs/shap_vs_gain_diagnosis.csv', encoding='utf-8-sig')
    print("\n===== gain 重要性 vs SHAP 分歧诊断（论文 4.2 要按这张表改口径）=====")
    print(diag.round(6).to_string())
    degenerate = [n for n in diag.index if diag.loc[n, 'mean_abs_SHAP'] < 1e-6]
    sparse = [n for n in diag.index if diag.loc[n, '全量非零占比'] < 0.01]
    if degenerate or sparse:
        print(f"\n[重要] SHAP 约等于 0 的特征：{degenerate}")
        print(f"[重要] 全量非零占比小于 1% 的稀疏特征：{sparse}")
        print("[重要] 论文 4.2 里凡把这些特征说成『最具判别力』的表述都需要改写，"
              "否则任何拿到数据的人跑一遍就能推翻。")

    # ---- 13.7 自动生成陈述（只陈述事实，不做法律结论）----
    def _phrase(i):
        v = sv[i]
        order = np.argsort(-np.abs(v))
        down = [j for j in order if v[j] < -1e-6][:3]
        up = [j for j in order if v[j] > 1e-6][:3]

        def fmt(js):
            return '、'.join(f'{labels[j]}={X_shap.iloc[i, j]:g}（{v[j]:+.2f}）' for j in js) or '无'
        return fmt(down), fmt(up)

    dn_txt, up_txt = _phrase(i_b)
    weak = '、'.join(sorted(set(degenerate + sparse))) or '无'
    with open('outputs/self_proof_report_sample.txt', 'w', encoding='utf-8') as f:
        f.write('【断卡申诉自证报告 · 证据片段（由 SHAP 自动生成，示例）】\n')
        f.write(f'样本：测试集抽样第 {i_b} 条交易；真实标签：正常（非可疑）；模型可疑概率：{prob_shap[i_b]:.6f}\n\n')
        f.write(f'基准值 base = {ev:.4f} (log-odds)，各特征贡献（|SHAP| 前 8）：\n')
        for j in np.argsort(-np.abs(sv[i_b]))[:8]:
            sign = '推高' if sv[i_b][j] > 0 else '压低'
            f.write(f'  {sign}可疑风险 | {labels[j]} = {X_shap.iloc[i_b, j]:g} '
                    f'| 贡献 {sv[i_b][j]:+.4f} log-odds\n')
        f.write(
            f'\n陈述：在本模型看来，该账户把风险往低方向推的因素为 {dn_txt}；'
            f'往高方向推的因素为 {up_txt}。综合可疑概率 {prob_shap[i_b]:.6f}。'
            f'上述归因仅反映模型内部的数值贡献；其中 {weak} '
            '在本数据集上取值退化或极度稀疏，不得单独作为对外结论依据。'
            '本报告仅作为用户风险告知与银行复核线索，不构成对交易合法性的认定。\n'
        )
    print("\n已生成：outputs/self_proof_report_sample.txt（论文 5.4 与 demo 的『生成自证报告』按钮共用这份结构）")
    print("SHAP 图输出目录：outputs/shap_*.png")

    # 还原字体设置，避免影响后面图1（模型对比柱状图）的观感
    plt.rcParams['font.sans-serif'] = _FONT_BACKUP


# 10. 训练模型4：多层感知机 MLP
print("正在训练：多层感知机 MLP...")
mlp = MLPClassifier(hidden_layer_sizes=(64,), max_iter=300, random_state=42)
mlp.fit(X_train_bal, y_train_bal)
results.append(evaluate("MLP", y_test, mlp.predict(X_test), mlp.predict_proba(X_test)[:,1]))

# 11. 输出最终结果表
print("\n===== 模型评估结果对比 =====")
results_df = pd.DataFrame(results)
print(results_df.to_string(index=False))

# 12. 保存结果


results_df.to_csv("outputs/model_comparison.csv", index=False)
print("\n结果已保存至 outputs/model_comparison.csv")

new_file_path = "outputs/model_comparison.csv"   # 原本写死 Desktop 绝对路径，会读到上一次运行的旧结果，
                                                  # 导致图1 与表2 数字不一致（MLP 对线程数敏感，跨 run 会浮动）
df_new = pd.read_csv(new_file_path, encoding="utf-8")
print(df_new.head())
score_cols = ['F1分数', 'AUC', 'PR_AUC', 'MCC']
colors = ['#4C78A8', '#54A24B', '#E45756', '#72B7B2']
models = df_new['模型'].tolist()
x = np.arange(len(models))
width = 0.18

fig, ax = plt.subplots(figsize=(10, 6))
for i, col in enumerate(score_cols):
    ax.bar(x + i * width, df_new[col], width, label=col, color=colors[i])

ax.set_xticks(x + width * (len(score_cols) - 1) / 2)
ax.set_xticklabels(models)
ax.set_xlabel('models')
ax.set_ylabel('scores')
ax.legend()
plt.tight_layout()
plt.close()


import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score, average_precision_score
from xgboost import XGBClassifier

# 关键：重置索引，避免 X/y 索引断裂导致的报错
X = X.reset_index(drop=True)
y = y.reset_index(drop=True)

seeds = [0, 1, 42, 123, 2024]
results = []

for seed in seeds:
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.3, stratify=y, random_state=seed
    )

    # 关键：每个种子重新计算正负比，不要写死 1819
    spw = (y_train == 0).sum() / max((y_train == 1).sum(), 1)

    model = XGBClassifier(
        n_estimators=200, max_depth=4, learning_rate=0.1,
        scale_pos_weight=spw, eval_metric='logloss',
        random_state=seed, n_jobs=-1
    )
    model.fit(X_train, y_train)

    y_prob = model.predict_proba(X_test)[:, 1]
    auc = roc_auc_score(y_test, y_prob)
    pr_auc = average_precision_score(y_test, y_prob)

    # 关键：用 .values 转 numpy 再索引，避免 iloc 报错
    top50_idx = np.argsort(y_prob)[::-1][:50]
    hits = int(y_test.values[top50_idx].sum())

    # 关键：返回特征名，不是列下标
    imp = model.feature_importances_
    top4_idx = np.argsort(imp)[-4:][::-1]
    top4_names = [X.columns[i] for i in top4_idx]

    results.append({
        'seed': seed,
        'AUC': round(float(auc), 4),
        'PR_AUC': round(float(pr_auc), 4),
        'Top50命中': hits,
        'Top4特征': ', '.join(top4_names),
    })
    print(f"seed={seed}  AUC={auc:.4f}  PR_AUC={pr_auc:.4f}  Top50命中={hits}")

res_df = pd.DataFrame(results)
print("\n", res_df.to_string(index=False))
print(f"\nAUC 均值±标准差：{res_df['AUC'].mean():.4f} ± {res_df['AUC'].std():.4f}")
print(f"PR_AUC 均值±标准差：{res_df['PR_AUC'].mean():.4f} ± {res_df['PR_AUC'].std():.4f}")
res_df.to_csv("outputs/seed_robustness.csv", index=False, encoding="utf-8-sig")
print("已保存至 outputs/seed_robustness.csv")
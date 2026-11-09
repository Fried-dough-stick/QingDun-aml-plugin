
| 事项 | D6 演示站 | 行内/生产版 |
|---|---|---|
| 访问 | 公网 IP + 非 80 端口或域名 | 行内网，不暴露公网 |
| HTTPS | 有域名就上，没域名先 HTTP 演示 | 必须 HTTPS |
| 备案 | 大陆 80/443 + 域名要备案；赶时间用香港服务器/非 80 端口 | 按行内合规走 |
| 数据库 | Postgres 只开容器内网，不映射公网 | 同左，加白名单 |
| 账号 | 开放注册 + 固定演示账号 | 管理员开号，接行内 SSO |
| 密码 | bcrypt 哈希，登录限流 | 加密码策略、锁定、MFA |
| 密钥 | `.env` 不进 git，示例只放占位符 | 密钥托管 |
| 数据 | 合成数据，无真实客户信息 | 脱敏/不出域 |

---

## 1. 总体：3 个阶段，6+3+3 天

**阶段一不按“先搭骨架再补功能”做，而是把每项基本功能都做出一条能跑的粗线。D6 结束就是可以交的网站；阶段二只加深度，阶段三只做包装和缓冲。** D7 之后出任何问题，退回 D6 的 `v0.1` 也能交。

| 阶段 | 时间 | 目标 | 结束时必须能做到 |
|---|---|---|---|
| 阶段一 | D1–D6 | **全功能垂直打通（丑但能用）** | 注册/登录、总览、交易、预警、报告、CSV/PDF/PNG、公网部署，每项都有最低可用版本。**D6 打 `v0.1`，这是保底交付物** |
| 阶段二 | D7–D9 | **只打磨，不加新功能** | 因子中文/方向/红蓝条、30 天时间线、资金流向、图表联动、报告精修、查询性能、安全加固、移动端 |
| 阶段三 | D10–D12 | 包装、彩排、缓冲 | D10 写材料、D11 从零复现+录视频、D12 只打包不写代码 |

**三条硬规矩：**

1. D6 之后不允许再出现“只在我分支上、没合 `dev`”的功能。所有基本功能 D6 前合进 `dev`。
2. 阶段二发现 D6 有功能没走通，**D7 上午先补通**，补通之前不做打磨。
3. 阶段二想出来的新点子一律写进 `docs/backlog.md`，不进代码；阶段三不碰功能。

---

## 2. 阶段一：D1–D6，全功能跑通

| 谁 / 分支 | 时间 | 放什么文件 | 实现什么功能（D6 及格线版） | 交接给对方看什么 |
|---|---|---|---|---|
| A / `feat/db-data` | D1–D2 | `db/schema.sql`、`indexes.sql`、`views.sql`；`etl/load_parquet.py`、`clean.py`；`scripts/seed_demo.py`；`docs/data_dictionary.md` | 建 9 张表：`app_user`、`account`、`txn`、`risk_score`、`alert`、`alert_factor`、`report`、`audit_log`、`model_run`、`eval_label`；ETL 选 25 列，灌 748,869 行、1,115 账户；`v_alert_queue`、`v_case_360`、`v_dashboard_daily` 三个视图；`seed_demo.py` 造演示账号和 85/15 处置状态（不按真值造） | D1 晚先给 B 表结构（B 第二天照着写 API）；D2 给数据字典 + 3 条示例 SQL。B 跑 `select count(*) from txn`（=748869）、`select count(*) from account`（=1115）、`select * from v_alert_queue limit 10` |
| A / `feat/auth` | D2–D3 | `backend/app/api/auth.py`、`core/security.py`、`schemas/auth.py`、`frontend/login.html`、`js/auth.js` | 注册（用户名/邮箱/密码，重复校验）、登录、登出、`/me`；bcrypt 哈希；JWT 放 httpOnly Cookie（同时支持 Bearer 方便调 API）；登录失败限流；固定演示账号；401 前端回登录 | 给 B：`/docs` 里的 auth 接口 + 一个能登录的演示账号。B 在 `main.py` D1 先留好 auth router 的挂载点，A 只填 `api/auth.py` |
| A / `feat/pages-overview-txn` | D3–D5 | `frontend/index.html`、`transactions.html`、`profile.html`、`css/pages.css`、`js/dashboard.js`、`transactions.js`、`profile.js` | 总览：4 个 KPI、7/30 天趋势、风险分布、最新预警；交易：列表、6 个筛选、分页、详情弹窗、风险建议卡；账号页：用户名/角色/登录时间/登出；D3–D4 先用 mock，D5 换真 API | 给 B：页面截图 + 缺哪些接口字段。B 按 `/api/dashboard/*`、`/api/transactions/*`、`/api/auth/me` 对一遍，缺的补进 API |
| A / `feat/export-csv` | D4–D5 | `backend/app/api/export.py`、`services/export_csv.py`、前端导出按钮 | 交易/预警 CSV 按**当前筛选**导出，流式返回，带 BOM 防 Excel 乱码；文件名带日期；大数据量不一次性读内存 | 给 B：两条导出 URL 样例 + 字段顺序。B 在预警页加“导出当前筛选”按钮 |
| A / `feat/deploy` | D1、D5–D6 | `deploy/docker-compose.web.yml`、`nginx.conf`、`.env.example`、`README.md`、`scripts/backup.sh` | D1 先起 hello-world 容器验证服务器和端口；D5 起四个容器：Postgres + api + web + nginx；演示模式公网只开网站端口；数据库不映射公网；固定演示账号；`pg_dump` 备份脚本 | 给 B：公网 URL、演示账号、`docker compose up -d` 一条命令。B 用手机 4G 打开登录页/总览/交易页 |
| B / `feat/api-core` | D1–D3 | `backend/app/main.py`、`core/config.py`、`db/session.py`、`models/`、`schemas/`、`api/dashboard.py`、`transactions.py`、`alerts.py`、`reports.py`、`health.py`；`requirements.txt`、`Dockerfile` | D1 起 FastAPI 骨架 + `/api/health` + auth router 挂载点；D2 出总览 4 个接口 + 交易列表/详情 + 预警列表/详情；D3 补齐因子、状态修改、报告接口、分页/筛选；所有查询参数化；响应模型显式排除真值字段；审计中间件先记登录/查看/处置/导出/报告五类 | 给 A：`/docs` + `docs/mocks/*.json`。A 从 D3 起按 mock 写页面，不等真库；D4 换成真接口 |
| B / `feat/ml-batch` | D2–D3 | `backend/ml/feature_builder.py`、`train.py`、`score_batch.py`、`config.py`、`README.md`；`backend/ml/experiments/train_compare.py`（原 03 脚本）；`backend/ml/tests/test_feature_builder.py`；`artifacts/xgb_model.json`、`feature_meta.json`、`metrics.json`、`model_comparison.csv`、`topk_precision.csv`；`model_card.md` | 复用 14 特征和 XGB 超参；路径改 `data/`、`Agg` 后端；LabelEncoder 只在训练集 fit，映射写 `feature_meta.json`；补按 `account_id` 分组 + 时间切分两套指标；748k 批量打分；`final_score=0.3*rule+0.7*model`；高危≥0.8、中危≥0.5；入队 top 3,000 + 规则≥0.67；top8 SHAP 写 `alert_factor`（D6 先存原始特征名和数值，中文名/红蓝条阶段二再做） | 给 A：`score_batch.py`、`metrics.json`、模型卡。A 跑 `select risk_level,count(*) from alert group by 1`，确认预警 3k+、每条 8 个因子 |
| B / `feat/frontend-shell` | D2–D3 | `frontend/css/app.css`、`table.css`、`js/api.js`、`router.js`、`format.js`、`charts.js` | 全站壳：复用旧 header/logo/nav/card/pill/timeline/modal；hash 路由；`api.js` 统一 fetch（带 Cookie、401 回登录、错误提示）；表格/分页/弹窗/格式化公共函数；`charts.js` 折线/柱状/环图 + `downloadPng`；D2 晚交给 A 写页面 | 给 A：`js/api.js` 怎么调、页面骨架怎么套。A 不再自己写一套请求和表格 |
| B / `feat/pages-alerts` | D3–D5 | `frontend/alerts.html`、`js/alerts.js`、`css/alerts.css` | 预警队列：列表、按风险级别/状态/日期筛选、分页；详情：账户/交易/8 条因子/时间线列表；按钮“确认可疑/标记排除”能改 `alert.status`；图表 PNG 下载；D3–D4 用 mock，D5 换真 API | 给 A：预警页面截图 + 字段清单。A 确认总览“最新预警”能跳转到详情 |
| B / `feat/report-pdf` | D4–D6 | `backend/app/services/report_pdf.py`、`api/reports.py`、`templates/report.html`、`frontend/reports.html`、`js/reports.js`、`assets/fonts/NotoSansSC-Regular.otf` | 报告 8 段“朴素版”：报告头/账户信息/交易摘要/证据链/风险因子/初步分析/建议/声明；reportlab + NotoSansSC 出 PDF；报告列表/预览/下载；PNG 先用 ECharts `getDataURL` 能下载即可 | 给 A：一份 PDF 样例 + 字体路径。A 在服务器上确认中文不是方块 |
| 两人 / `dev` 联调（不新建分支） | D5–D6 | 只修阻塞问题，不接新功能 | 把登录、总览、交易、预警、报告全部切到真 API；跑通“注册/登录→看总览→筛交易→看预警→改状态→生成报告→下载 PDF/CSV/PNG”整条链路；D6 下午照 2.3 清单逐项打勾 | 两人交换浏览器点一遍；每项标“过/不过”，不过的当场记 Issue，D6 晚只允许修阻塞项 |

### 2.1 D6 功能及格线（每项基本功能最低可交付版本）

| 功能 | D6 必须过（及格线） | 阶段二再优化 | 谁验 |
|---|---|---|---|
| 注册/登录 | 新用户能注册；重复用户名/邮箱报错；密码 bcrypt；登录成功进总览；登出后回登录页 | 邮箱验证、找回密码、登录锁定、角色管理 | A |
| 总览 | 4 个 KPI 是库里的真实数；趋势/分布能显示；最新预警能点进详情 | 时间范围切换、图表联动、Top 账户、模型卡 | A |
| 交易 | 列表能显示；按账户/日期/金额/渠道/方向/风险级别筛；分页正确；详情能打开；风险建议卡有分数/等级/因子 | 排序、列配置、批量导出、相似交易 | A |
| 预警 | 队列 3k+；筛选/分页；详情有 8 条原始因子、时间线列表；状态能改 | 因子中文名/方向/红蓝条、30 天时间线、资金流向图 | B |
| 报告 | 8 段齐全；能生成 PDF；中文不是方块；能预览/下载 | 账户卡、因子表、手法选择、页码、报告状态流 | B |
| 下载 | 交易/预警 CSV 按当前筛选导出；PDF 能下；至少一张图能下 PNG | 全部图表 PNG、导出任务进度、压缩包 | A/B |
| 公网部署 | `docker compose up -d` 起 4 个容器；手机 4G 能打开；固定账号能登录 | HTTPS、域名、备份、资源限制、一键回滚 | A |
| 安全底线 | 真值字段不出现在 API/页面；SQL 全部参数化；密码不落明文；`.env` 不进 git；登录有限流 | CSP、Cookie Secure、审计页、登录锁定、输入校验 | 两人 |
| 审计 | 登录/查看/处置/导出/报告五类动作落 `audit_log` | 审计页筛选/导出、操作人/耗时字段补全 | B |
| 文档 | README 能照着跑；`docs/api.md` 有接口表；数据字典有 25 列 | 架构图、效果报告、部署文档、答辩 QA | 两人 |

**这张表就是保底交付清单。D6 全部打勾，最差也是一个能注册登录、能看数、能下载、公网能打开的 `v0.1`；阶段二任何一项没做完，都不影响交这个版本。**

### 2.2 `03_train_models.py` 怎么拆（B，D2–D3，分支 `feat/ml-batch`）

**先给结论：不是废了，70–80% 能直接搬。** 要做的是把“一个 557 行的实验脚本”拆成“能上线调用的推理链路 + 一份离线对比实验”，不是重写。

| 时间 | 做什么 | 当天结束时手里有什么 |
|---|---|---|
| D2 上午 | 拆特征和训练：把读 parquet、编码、选列、填 0 抽成 `feature_builder.py`；切分、训练、评估放 `train.py`；路径/超参/阈值集中到 `config.py` | `python -m backend.ml.train` 能跑完并打印四个模型指标 |
| D2 下午 | 训练 XGB 并固化产物：按 `account_id` 分组切分 + 时间切分各跑一遍；保存 `xgb_model.json`、`feature_meta.json`、`metrics.json` | 三个产物进 `artifacts/`，`feature_meta.json` 里的列顺序能和训练时逐一对上 |
| D3 上午 | 批量打分：`score_batch.py` 读全量 748,869 行 → 规则分 + 模型分 → 写 `risk_score`、`alert`、`alert_factor` | 库里预警 3k+，每条预警 8 条因子 |
| D3 下午 | 补模型卡和质检：记录分组/时间切分指标、Top-K 命中、已知缺陷；跑 `tests/test_feature_builder.py` | `model_card.md` + 测试通过；交 A 对数字 |

**文件怎么分（原脚本按行号搬）：**

| 新文件 | 从原脚本搬什么 | 改什么 |
|---|---|---|
| `backend/ml/config.py` | 第 1–27 行的路径、随机种子、XGB 超参、阈值 | 路径改 `data/`；阈值 `0.8/0.5`、权重 `0.3/0.7`、入队 `top 3000 + 规则≥0.67` 全写这里，别散落 |
| `backend/ml/feature_builder.py` | 第 29–47 行：合并 parquet、`LabelEncoder`、`select_dtypes`、`fillna(0)`、bool→int | 编码器只在训练集上 `fit`；映射存 `feature_meta.json`；未见过的类别映射成 `-1`；列顺序固定 |
| `backend/ml/train.py` | 第 49–68 行：切分、SMOTE、`evaluate()` | 增加 `GroupShuffleSplit(groups=account_id)` 和时间切分（训练 ≤2024-05-31，测试在其后）；两套指标都写进 `metrics.json` |
| `backend/ml/score_batch.py` | 第 104–133 行 Top-K 的排序思路 + 第 193 行以后的 SHAP 计算 | 新增：读库/读 parquet → `feature_builder` 变换 → `booster.predict` + `pred_contribs` → 算 `final_score` → 批量写 `risk_score`/`alert`/`alert_factor`（每条 top8） |
| `backend/ml/experiments/train_compare.py` | 第 72–101 行四模型 + 图1、第 137–190 行 winsorize、第 193–430 行 SHAP 画图、第 433 行以后 MLP 和最终对比图 | 基本原样保留，只改导入路径和 `Agg` 后端；它只产出报告用的图/表，API 不 import 它 |
| `backend/ml/tests/test_feature_builder.py` | 无 | 新写：同一输入两次变换结果一致、列顺序等于 `feature_meta.json`、未知类别不报错 |
| `backend/ml/README.md` | 无 | 新写：怎么训练、怎么打分、产物在哪、怎么复现指标 |
| `artifacts/` | `xgb_model.pkl` 改格式 | 存 `xgb_model.json` + `feature_meta.json` + `metrics.json`；跨环境加载用 `Booster.load_model`，别用 pkl（xgboost 3 / sklearn 版本不一致会炸） |
| `model_card.md` | 无 | 新写：数据口径、14 特征、超参、两套切分指标、Top-K、SHAP 与 gain 的分歧、已知缺陷 |

**必须修的三处（不修就别上线）：**

1. 原脚本在切分**之前**就对全量 `X` 做了 `LabelEncoder.fit`（第 31–35 行），这是标签泄漏式的前置处理；改成 `fit` 只在训练集，测试集 `transform`。
2. 原脚本 `train_test_split` 是随机的，同一账户的交易会同时出现在训练和测试里；补一套按 `account_id` 分组切分，论文/模型卡两套数都报。
3. 原脚本 `joblib.dump` 藏在 `if RUN_SHAP:` 里（第 255 行），关掉 SHAP 就没有模型文件；模型保存要提到训练结束处。

另外：`plt.show()` 全改 `matplotlib.use('Agg')`；分级用 `final_score` 的 0.8/0.5，不要用 0.5 的模型概率阈值，否则 F1 好看但业务队列不对。

**兜底**：D2 晚上还没拆完，就只拆“推理路径”（`feature_builder.py` + `score_batch.py`），四模型对比继续用 `train_compare.py` 出图；D3 的入队不能等。

### 2.3 阶段一验收（D6 打勾清单）

| # | 验收动作 | 通过标准 | 谁验 |
|---|---|---|---|
| 1 | `docker compose -f deploy/docker-compose.web.yml up -d` | 4 个容器全 `running`，无重启 | A |
| 2 | `curl http://<IP>:8000/api/health` | 返回 `{"status":"ok","mode":"model+rule"}` | B |
| 3 | 新用户注册 → 登录 → 登出 → 再登录 | 全流程通；重复用户名报错；密码不是明文 | A |
| 4 | `select count(*) from txn` / `account` | 748,869 / 1,115 | A |
| 5 | `select risk_level, count(*) from alert group by 1` | 总数 3k+，high/mid/low 都有 | B |
| 6 | 打开总览 | 4 个 KPI 与库一致；趋势/分布有图；最新预警能点进详情 | A |
| 7 | 交易页筛选 + 翻页 + 打开详情 | 筛选结果正确；分页不重复不丢；风险建议卡有分数/等级/因子 | A |
| 8 | 预警详情 | 8 条因子、时间线、状态修改都可用 | B |
| 9 | 生成并下载报告 PDF | 8 段齐全，中文不是方块 | B |
| 10 | 导出交易/预警 CSV | 按当前筛选；Excel 打开不乱码；行数对得上 | A |
| 11 | 下载一张图 PNG | 图片能打开，标题/图例清楚 | B |
| 12 | 手机 4G 打开公网地址 | 能注册/登录，能看总览/交易/预警 | A |
| 13 | 页面搜 `is_suspicious` / 真值字段 | 页面和 API 都不出现，预警状态不是按真值造的 | 两人 |
| 14 | 查 `audit_log` | 登录/查看/处置/导出/报告五类都有记录 | B |

**D6 全部打勾后：`git tag v0.1`，`dev` 保持可运行。从这一刻起，任何阶段二改动都不能让 `v0.1` 跑不起来。**

### 2.4 如果 D5 发现要崩，按这个顺序保

| 优先级 | 必须保 | 可以先降级成 |
|---|---|---|
| P0（少一项就不算交付） | 注册/登录、748,869 入库、3k+ 预警、总览、交易页、预警页、CSV、PDF、公网能开 | 无 |
| P1（保底体验） | 报告 8 段、PNG、状态修改、审计落库 | PDF 用最简排版；审计只落库不做页面 |
| P2（有更好） | 图表联动、资金流向、模型卡、账号页细节 | 图表只留趋势和分布；模型卡放 README |

**砍的顺序：先砍 P2，再砍 P1 的排版，最后砍 P1 的页面；P0 九项不许砍。** D6 晚上只要 P0 全通、P1 有替代方案，就能交 `v0.1`。

---

## 3. 阶段二：D7–D9，只打磨，不加新功能

**开始前先做一件事：照 2.3 清单重跑一遍。哪项不过，D7 上午先补哪项；全过了才开始下面的打磨。** 阶段二不新增页面、不新增表、不新增接口，只把 D6 的粗线做细。

| 打磨项 | 谁 / 分支 | 时间 | 具体做什么 | 通过标准 |
|---|---|---|---|---|
| 因子从“能看”到“好懂” | B / `feat/explain-shap` | D7 | `/alerts/{id}/factors` 返回 8 行 `{feature_label, value, shap_value, direction}`；中文特征名、正负方向、红蓝条；`/timeline` 补近 30 天；`/flow` 返回“账户→类别→对手方”资金流向图 | 每条预警 8 行中文因子，方向与 SHAP 正负一致；时间线标出告警交易；资金流向能打开，金额对得上 |
| 总览从“静态”到“可查” | A / `feat/dashboard-polish` | D7–D8 | 时间范围切换（7/30/90 天）；KPI 点击联动列表；Top 10 高风险账户；模型卡（AUC/PR-AUC/Top-K）放总览底部或报告页 | KPI 与筛选联动正确；Top 账户能点进交易页；模型卡数字与 `metrics.json` 一致 |
| 报告从模板到能用 | B / `feat/reports-v2` | D8 | 正文从 `report + alert_factor + txn` 拼；账户卡、因子表、建议；选手法（跑分/漏斗/分层/拆分/盗用/首方欺诈/代付）；报告状态（草稿→已确认→已导出） | 实际生成 3 份不同手法的报告，8 段无漏项，改状态能保存 |
| 查询性能 | A / `feat/query-perf` | D8–D9 | 按 `ts_initiated/risk_level/status/account_id` 补索引；优化 `v_alert_queue` / `v_case_360`；748k 筛选分页稳定 | 交易/预警首页 < 300ms，翻到第 100 页不超时；`EXPLAIN` 走索引 |
| 安全加固 | B / `feat/security` | D8–D9 | 登录失败锁定/限流；Cookie `Secure`/`SameSite`；CSP；输入校验；审计页；错误信息不泄露 SQL/堆栈 | 连续错 5 次锁定；HTTPS 下 Cookie 带 Secure；审计页能查五类动作 |
| 导出与图表收尾 | B / `feat/export-polish` | D9 | 所有图表 PNG；CSV 导出当前筛选；PDF 加页码/附件声明；导出失败有提示 | 4 个页面至少各 1 张图能下；CSV 行数与页面总数一致；PDF 页码连续 |
| 移动端与空态 | A / `feat/ux-polish` | D9 | 窄屏表格横向滚动/卡片化；加载态、空态、错误提示；文案统一（“预警/交易/报告”，不要混用“告警/工单”） | 手机 4G 走完登录→总览→交易→预警→报告；断网/空数据不白屏 |

### 3.1 阶段二验收

- **2.3 的 14 项清单仍然全过**——打磨不能把 D6 已通的功能改坏；任何一项退化，当条 PR 不合。
- 没有新增页面、接口、表；`git diff v0.1..dev` 里没有“新功能”，只有“同一功能的细化”。
- 因子 8 条中文名、红/蓝方向正确；30 天时间线标出告警交易；资金流向图能打开。
- 报告 8 段齐全；3 种手法各生成一份；PDF 有页码，中文正常。
- 总览 KPI 与筛选联动；Top 账户能跳转；模型卡数字与 `metrics.json` 一致。
- 交易/预警首页 < 300ms；10 并发无 500，p95 < 2s。
- 连续登录失败 5 次会锁定；HTTPS 下 Cookie 带 `Secure`；审计页能查五类动作。
- 手机 4G 能完成整条链路；空数据/断网有提示，不白屏。

---

## 4. 阶段三：D10–D12，包装、彩排、缓冲

**D6 已经把功能做完了，这里不补功能。** D10 写材料，D11 从零复现+录视频，D12 只打包和上传；D12 出现任何阻塞，退回 D6 的 `v0.1` 交。

| 谁 / 分支 | 时间 | 放什么文件 | 实现什么功能 | 交接给对方看什么 |
|---|---|---|---|---|
| 两人 / `release/v1.0`（从 `dev` 切） | D10 | `README.md`、`docs/architecture.md`、`docs/api.md`、`docs/deploy.md`、`docs/effect_report.md`、`docs/defense_qa.md`、`docs/申报书素材.md`、`docs/screenshots/` | 只写材料：架构图、接口表、部署文档、效果报告、数据卡/模型卡、竞品/ROI；把 2.3 清单和 `metrics.json` 的数字抄进去 | 两人互查：所有数字与 `metrics.json` / `model_comparison.csv` 一致；效果报告不写“15 分钟→3 分钟”这种没实测的说法 |
| 两人 / `release/v1.0` | D11 | `docs/demo_script.md`、PPT、3–5 分钟视频、`release_notes.md` | 从零 clone→compose up 复现一遍；按脚本录视频；PPT 定稿；3 分钟 demo 彩排两遍 | 互相当评委：计时走完注册/登录→总览→交易→预警→报告→下载，卡壳就删步骤 |
| 两人 / `release/v1.0` | D12 | 只打包 | `docker save` 出 `web-v1.0.tar`；合 `main`、打 `v1.0` tag；提交申报书/视频/PPT；**不写新代码** | 提交前最后一眼：公网链接能打开、账号能登录、PDF/CSV/PNG 能下载 |
| A / `fix/deploy` | D10–D12 | 只修部署/数据/PDF 的阻塞问题 | 服务器、备份、HTTPS、PDF 中文字体、镜像导出 | 给 B：最终 URL、镜像 tar、账号、备份文件 |
| B / `fix/ui` | D10–D12 | 只修页面错位/文案/空态 | 不影响功能的最后一轮修补 | 给 A：最终截图/视频 |

### 4.1 阶段三验收

- 新电脑 `git clone` → `cp .env.example .env` → `docker compose -f deploy/docker-compose.web.yml up -d` → `curl /api/health` 能通。
- 3 分钟 demo 按脚本走完：注册/登录→总览→交易→预警→报告→PDF/CSV/PNG。
- `docker save` 出一个 `web-v1.0.tar`，科技岗能加载。
- 申报书技术段、PPT、视频、数据卡、模型卡、效果报告齐全；数字与 `metrics.json` 一致。
- **即使 D10–D12 全部翻车，仓库里仍有 D6 的 `v0.1` 可交：4 个容器能起、能登录、能看数、能下载。**

---

## 5. 交付物清单

| 给谁 | 交付物 | 谁负责 |
|---|---|---|
| 银行科技岗 | 源码 + Docker 镜像 + 架构图 + 部署文档 + 数据字典 + 效果报告 | A |
| 银行合规岗 | 演示站 + 交易/预警/报告页 + PDF 样例 + 风险建议口径说明 | B/A |
| 评委/投资人 | 商业计划书 + 竞品对比 + ROI + 数据卡/模型卡 + 3 分钟 demo | 两人 |
| 自己团队 | 可复用代码骨架 + README + API 文档 + 演示脚本 | 两人 |

**效果报告口径（别照抄图里的数字）**

| 图里的说法 | 我们怎么写 |
|---|---|
| 一条告警 15 min → 3 min | 写成“模拟分析师步骤数：6 步 → 2 步”，标注“流程模拟，不是实测” |
| 误报压降 30–50% | 没有真实分析师基线，改说“Top-K 命中率/前 30% 队列命中”，不写 30–50% |
| SAR 2 h → 改 20% | 写成“模板生成初稿，人工修改/复核”，演示口径 |

---

## 6. 分支合并顺序（照着走）

1. **阶段一（全功能，必须全合）**：`feat/db-data` 先合 `dev`；同时 `feat/api-core`、`feat/ml-batch`；接着 `feat/auth`、`feat/frontend-shell`、`feat/pages-overview-txn`、`feat/pages-alerts`、`feat/export-csv`、`feat/report-pdf`；`feat/deploy` 在 D5 合。**D6 下午按 2.3 清单验完，打 `v0.1`。任何功能没合进 `dev` 就不算完成，D6 晚上不许在分支上留功能。**
2. **阶段二（只打磨）**：`feat/explain-shap` → `feat/reports-v2` → `feat/dashboard-polish` → `feat/query-perf` → `feat/security` → `feat/export-polish` → `feat/ux-polish`；D9 打 `v0.2`。每条 PR 都要说明“这是对 D6 哪一项的细化”，说不出来就进 `docs/backlog.md`。
3. **阶段三（只包装）**：从 `dev` 切 `release/v1.0`，只改文档/文案/配置；D12 合 `main`，打 `v1.0`。

## 7. 交接只交代三样

1. **文件在哪**：给对方具体路径，不要让他在仓库里翻。
2. **先做什么**：打开哪个页面、跑哪条命令、连哪个库。
3. **什么算通过**：一个具体数字或动作，比如“`count(*)` 是 748869”“注册后能登录”“PDF 中文不是方块”“手机 4G 能打开”。

## 8. 两个规矩

- 每个人只改自己目录；公共的 `js/api.js`、`css/app.css`、`table.css`、`main.py` 归 B，A 要加接口先发 Issue。一个分支只做一件事，PR 不超过 20 个文件。
- 合进 `dev` 才算交接完成，发微信发文件不算。

## 9. 一句话记

**A 负责“数据进库、注册登录、总览/交易页、CSV、部署”；B 负责“模型出分、API、预警/报告页、PDF/PNG”。做网站，不做补丁；D6 全功能保底，D7–D9 只打磨，D10–D12 只包装——D6 过了，这仗就不会输。**

---

## 10. 旧文档保留说明

- 补丁版分工：`青盾2.0_分工与分支.md`（保留，不删除、不改动；需要切回补丁形态时直接看这份）。
- 早期思路记录：`讨论初步思路之中小银行反洗钱.md`（保留，作为产品背景）。
- 本文档：`青盾2.0_网站版_分工与分支.md`（当前执行版）。

(function () {
  "use strict";

  const fmt = window.QD.fmt;
  const api = window.QD.api;
  const router = window.QD.router;

  const state = {
    page: 1,
    page_size: 20,
    sort: "priority",
    filters: { risk_level: "", status: "", date_from: "", date_to: "", q: "" },
    chart: null,
    detail: null,
  };

  const queueView = document.getElementById("view-queue");
  const detailView = document.getElementById("view-detail");
  const queueBody = document.getElementById("queue-body");
  const detailBody = document.getElementById("detail-body");
  const filterForm = document.getElementById("filter-form");

  function readFilters() {
    const from = document.getElementById("f-from").value;
    const to = document.getElementById("f-to").value;
    state.filters = {
      risk_level: document.getElementById("f-risk").value,
      status: document.getElementById("f-status").value,
      date_from: from ? from + "T00:00:00" : "",
      date_to: to ? to + "T23:59:59" : "",
      q: document.getElementById("f-q").value.trim(),
    };
    state.sort = document.getElementById("f-sort").value;
    state.page = 1;
  }

  function listQuery() {
    return Object.assign({}, state.filters, {
      page: state.page,
      page_size: state.page_size,
      sort: state.sort,
    });
  }

  function showQueue() {
    queueView.hidden = false;
    detailView.hidden = true;
    if (state.chart) {
      state.chart.dispose();
      state.chart = null;
    }
    loadQueue();
  }

  function showDetail(id) {
    queueView.hidden = true;
    detailView.hidden = false;
    loadDetail(id);
  }

  async function loadQueue() {
    fmt.setLoading(queueBody, "加载预警队列");
    try {
      const data = await api.get("/alerts", listQuery());
      document.getElementById("queue-count").textContent =
        "共 " + fmt.number(data.total) + " 条预警" + (state.filters.status ? "" : "（演示状态：85% 待处理 / 15% 已处置）");
      renderQueue(data);
    } catch (err) {
      fmt.setError(queueBody, err.message || "加载失败", loadQueue);
    }
  }

  function renderQueue(data) {
    if (!data.items.length) {
      queueBody.innerHTML = '<div class="empty"><div class="empty-title">没有符合条件的预警</div>' +
        '<div class="small">调整筛选条件后再试</div></div>';
      return;
    }

    const rows = data.items.map((item) => {
      const tags = (item.tags || []).slice(0, 2)
        .map((tag) => '<span class="pill pill-blue">' + fmt.escapeHtml(tag) + "</span>").join(" ");
      return '<tr class="clickable" data-id="' + fmt.escapeHtml(item.alert_id) + '">' +
        '<td class="mono nowrap">' + fmt.escapeHtml(item.alert_id) + "</td>" +
        '<td class="nowrap">' + fmt.dateTime(item.ts_initiated) + "</td>" +
        '<td class="mono">' + fmt.escapeHtml(item.account_id.slice(0, 10)) + "</td>" +
        '<td>' + fmt.escapeHtml(item.counterparty_name || "—") + "</td>" +
        '<td class="right nowrap">' + fmt.money(item.amount) + "</td>" +
        "<td>" + fmt.scoreBar(item.risk_score, item.risk_level) + "</td>" +
        "<td>" + fmt.riskPill(item.risk_level) + "</td>" +
        "<td>" + fmt.statusPill(item.status) + "</td>" +
        '<td class="nowrap">' + fmt.number(item.priority) + "</td>" +
        "<td>" + (tags || '<span class="muted">—</span>') + "</td>" +
        "</tr>";
    }).join("");

    const html = '<div class="table-wrap"><table class="data"><thead><tr>' +
      "<th>预警编号</th><th>交易时间</th><th>账户</th><th>对手方</th><th class=\"right\">金额</th>" +
      "<th>风险分</th><th>等级</th><th>状态</th><th>优先级</th><th>标签</th>" +
      "</tr></thead><tbody>" + rows + "</tbody></table></div>";

    queueBody.innerHTML = html;
    queueBody.appendChild(fmt.pager(data, (page) => {
      state.page = page;
      loadQueue();
      window.scrollTo({ top: 0, behavior: "smooth" });
    }));

    queueBody.querySelectorAll("tr[data-id]").forEach((tr) => {
      tr.addEventListener("click", () => router.navigate("/alerts/" + tr.dataset.id));
    });
  }

  async function loadDetail(id) {
    fmt.setLoading(detailBody, "加载卷宗");
    try {
      const data = await api.get("/alerts/" + encodeURIComponent(id));
      state.detail = data;
      renderDetail(data);
    } catch (err) {
      fmt.setError(detailBody, err.message || "卷宗加载失败", () => loadDetail(id));
    }
  }

  function factorHtml(factors) {
    if (!factors || !factors.length) {
      return '<div class="empty">暂无因子</div>';
    }
    const maxAbs = Math.max.apply(null, factors.map((f) => Math.abs(f.shap_value) || 0.000001));
    return '<div class="factor-list">' + factors.map((f) => {
      const width = Math.max(4, Math.min(50, (Math.abs(f.shap_value) / maxAbs) * 50));
      const dir = f.direction === "down" ? "down" : "up";
      return '<div class="factor-row">' +
        '<div><div class="factor-name"><span class="rank">' + f.rank + "</span>" +
        fmt.escapeHtml(f.feature_label || f.feature) + "</div>" +
        '<div class="factor-meta">取值 ' + fmt.number(f.value, 4) +
        " · SHAP " + (f.shap_value >= 0 ? "+" : "") + Number(f.shap_value).toFixed(4) +
        (dir === "up" ? " · 推高可疑" : " · 压低可疑") + "</div>" +
        '<div class="factor-bar ' + dir + '" style="margin-top:6px"><i style="width:' + width + '%"></i></div></div>' +
        '<div class="factor-value">' + (dir === "up" ? "风险 ↑" : "风险 ↓") + "</div>" +
        "</div>";
    }).join("") + "</div>";
  }

  function timelineHtml(points) {
    const recent = (points || []).slice().reverse()
      .filter((point) => point.count > 0 || point.has_alert)
      .slice(0, 10);
    if (!recent.length) return '<div class="empty">近 30 天无交易</div>';
    return '<ul class="timeline">' + recent.map((point) => {
      return '<li class="timeline-item' + (point.has_alert ? " alert" : "") + '">' +
        '<div class="timeline-time">' + fmt.escapeHtml(point.date) + "</div>" +
        '<div class="timeline-title">' + fmt.number(point.count) + " 笔 · " + fmt.money(point.amount) + "</div>" +
        '<div class="timeline-desc">' + (point.has_alert ? "本笔预警交易发生在该日" : "账户当日交易汇总") + "</div>" +
        "</li>";
    }).join("") + "</ul>";
  }

  function renderDetail(data) {
    const txn = data.txn || {};
    const risk = txn.risk || {};
    const statusText = fmt.statusLabel(data.status);
    const actionButtons = data.status === "pending"
      ? '<button class="btn btn-primary" id="confirm-btn">确认可疑</button>' +
        '<button class="btn btn-danger" id="dismiss-btn">标记排除</button>'
      : '<button class="btn" id="reopen-btn">改回待处理</button>';

    detailBody.innerHTML =
      '<div class="card">' +
        '<div class="alert-detail-head">' +
          '<div><h2>预警 ' + fmt.escapeHtml(data.alert_id) + "</h2>" +
            '<div class="meta">优先级 #' + fmt.number(data.priority) + " · 账户 " +
            fmt.escapeHtml(data.account_id) + " · 交易 " + fmt.escapeHtml(data.txn_id) + "</div>" +
            '<div style="margin-top:8px">' + fmt.riskPill(data.risk_level) + " " + fmt.statusPill(data.status) + "</div>" +
          "</div>" +
          '<div class="risk-badge risk-' + fmt.escapeHtml(data.risk_level) + '">' +
            '<div><div class="score">' + Number(data.risk_score).toFixed(3) + "</div>" +
            '<div class="label">综合风险分 · ' + fmt.escapeHtml(fmt.riskLabel(data.risk_level)) + "</div></div>" +
          "</div>" +
        "</div>" +
        '<div class="summary-box">' + fmt.escapeHtml(data.summary || "无摘要") + "</div>" +
        '<div class="kv-grid" style="margin-top:16px">' +
          kv("交易时间", fmt.dateTime(txn.ts_initiated)) +
          kv("金额", fmt.money(txn.amount) + " " + (txn.currency || "USD")) +
          kv("方向 / 渠道", fmt.directionLabel(txn.direction) + " / " + (txn.channel || "—")) +
          kv("类别 / MCC", (txn.category || "—") + " / " + (txn.mcc === null || txn.mcc === undefined ? "—" : txn.mcc)) +
          kv("对手方", (txn.counterparty_name || "—") + "（" + (txn.counterparty_country || "—") + "）") +
          kv("授权状态", txn.is_authorized ? "已授权" : "未授权") +
          kv("模型分", risk.model_score === undefined ? "—" : Number(risk.model_score).toFixed(4)) +
          kv("规则分", risk.rule_score === undefined ? "—" : Number(risk.rule_score).toFixed(4)) +
          kv("处置人", data.assignee || "—") +
        "</div>" +
        '<div class="alert-toolbar">' + actionButtons +
          '<button class="btn" id="report-btn">生成 SAR 报告</button>' +
          '<button class="btn" id="csv-btn">导出当前队列 CSV</button>' +
        "</div>" +
        '<div class="field" style="margin-top:14px"><label for="note-input">处置备注（可选，随状态一起保存）</label>' +
          '<input class="input" id="note-input" placeholder="例如：已电话核实客户交易背景" value="' +
          fmt.escapeHtml(data.note || "") + '" /></div>' +
      "</div>" +

      '<div class="split-2" style="margin-top:16px">' +
        '<div class="stack">' +
          '<div class="card"><h3 class="card-title">近 30 天账户交易<span class="card-sub">告警交易在图中标记</span></h3>' +
            '<div class="chart-box" id="timeline-chart"></div>' +
            '<div class="toolbar" style="margin:8px 0 0"><div class="left small muted">折线：每日交易笔数</div>' +
            '<div class="right"><button class="btn" id="png-btn" type="button">下载 PNG</button></div></div>' +
          "</div>" +
          '<div class="card"><h3 class="card-title">交易时间线</h3>' + timelineHtml(data.timeline) + "</div>" +
        "</div>" +
        '<div class="card"><h3 class="card-title">风险因子<span class="card-sub">Top 8 · SHAP 归因</span></h3>' +
          factorHtml(data.factors) +
        "</div>" +
      "</div>";

    bindDetailActions(data);
    renderTimelineChart(data.timeline || []);
  }

  function kv(label, value) {
    return '<div class="kv"><div class="k">' + fmt.escapeHtml(label) + "</div>" +
      '<div class="v">' + fmt.escapeHtml(value) + "</div></div>";
  }

  function currentNote() {
    const input = document.getElementById("note-input");
    return input ? input.value.trim() : "";
  }

  async function changeStatus(status) {
    const data = state.detail;
    if (!data) return;
    const buttons = document.querySelectorAll(".alert-toolbar .btn");
    buttons.forEach((btn) => { btn.disabled = true; });
    try {
      const payload = { status: status };
      const note = currentNote();
      if (note) payload.note = note;
      await api.patch("/alerts/" + encodeURIComponent(data.alert_id) + "/status", payload);
      fmt.toast("状态已更新为「" + fmt.statusLabel(status) + "」", "success");
      await loadDetail(data.alert_id);
    } catch (err) {
      fmt.toast(err.message || "状态更新失败", "error");
      buttons.forEach((btn) => { btn.disabled = false; });
    }
  }

  function bindDetailActions(data) {
    const confirmBtn = document.getElementById("confirm-btn");
    const dismissBtn = document.getElementById("dismiss-btn");
    const reopenBtn = document.getElementById("reopen-btn");
    if (confirmBtn) confirmBtn.addEventListener("click", () => changeStatus("confirmed"));
    if (dismissBtn) dismissBtn.addEventListener("click", () => changeStatus("dismissed"));
    if (reopenBtn) reopenBtn.addEventListener("click", () => changeStatus("pending"));

    document.getElementById("csv-btn").addEventListener("click", exportCurrent);
    document.getElementById("png-btn").addEventListener("click", () => {
      window.QD.charts.downloadPng(state.chart, "alert_" + data.alert_id + "_timeline.png");
    });
    document.getElementById("report-btn").addEventListener("click", async function () {
      const btn = this;
      btn.disabled = true;
      btn.textContent = "生成中…";
      try {
        const report = await api.post("/reports", { alert_id: data.alert_id, report_type: "alert" });
        await api.download("/reports/" + encodeURIComponent(report.report_id) + "/pdf", report.report_id + ".pdf");
        fmt.toast("报告已生成并开始下载", "success");
      } catch (err) {
        fmt.toast(err.message || "报告生成失败", "error");
      } finally {
        btn.disabled = false;
        btn.textContent = "生成 SAR 报告";
      }
    });
  }

  function renderTimelineChart(points) {
    const el = document.getElementById("timeline-chart");
    if (!el) return;
    if (state.chart) {
      state.chart.dispose();
      state.chart = null;
    }
    const labels = points.map((p) => p.date.slice(5));
    const values = points.map((p) => p.count);
    state.chart = window.QD.charts.line(el, labels, values, "交易笔数");
  }

  async function exportCurrent() {
    const params = new URLSearchParams();
    Object.entries(state.filters).forEach(([key, value]) => {
      if (value) params.set(key, value);
    });
    try {
      const stamp = new Date().toISOString().slice(0, 10);
      await api.download("/export/alerts.csv?" + params.toString(), "alerts_" + stamp + ".csv");
      fmt.toast("CSV 已开始下载", "success");
    } catch (err) {
      fmt.toast(err.message || "导出失败", "error");
    }
  }

  filterForm.addEventListener("submit", (event) => {
    event.preventDefault();
    readFilters();
    loadQueue();
  });

  document.getElementById("f-sort").addEventListener("change", () => {
    state.sort = document.getElementById("f-sort").value;
    state.page = 1;
    loadQueue();
  });

  document.getElementById("reset-btn").addEventListener("click", () => {
    filterForm.reset();
    readFilters();
    loadQueue();
  });

  document.getElementById("refresh-btn").addEventListener("click", loadQueue);
  document.getElementById("export-btn").addEventListener("click", exportCurrent);

  window.QD.layout.renderHeader();
  router.start([
    { pattern: /^\/alerts$/, handler: showQueue },
    { pattern: /^\/alerts\/([^/]+)$/, handler: (match) => showDetail(decodeURIComponent(match[1])) },
  ], () => router.navigate("/alerts"));
})();

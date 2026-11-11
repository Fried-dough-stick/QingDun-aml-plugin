(function () {
  "use strict";

  const fmt = window.QD.fmt;
  const api = window.QD.api;

  const state = {
    page: 1,
    page_size: 20,
    filters: { alert_id: "", status: "" },
  };

  const body = document.getElementById("reports-body");

  function statusPill(status) {
    if (status === "generated") return '<span class="pill pill-green">已生成</span>';
    if (status === "failed") return '<span class="pill pill-high">生成失败</span>';
    return '<span class="pill pill-mid">生成中</span>';
  }

  async function loadReports() {
    fmt.setLoading(body, "加载报告列表");
    try {
      const data = await api.get("/reports", {
        page: state.page,
        page_size: state.page_size,
        alert_id: state.filters.alert_id || undefined,
        status: state.filters.status || undefined,
      });
      render(data);
    } catch (err) {
      fmt.setError(body, err.message || "加载失败", loadReports);
    }
  }

  function render(data) {
    if (!data.items.length) {
      body.innerHTML = '<div class="empty"><div class="empty-title">还没有报告</div>' +
        '<div class="small">在上方输入预警编号生成第一份 PDF</div></div>';
      return;
    }

    const rows = data.items.map((item) => {
      const actions = item.status === "generated"
        ? '<button class="btn small" data-preview="' + fmt.escapeHtml(item.report_id) + '">预览</button> ' +
          '<button class="btn small btn-primary" data-download="' + fmt.escapeHtml(item.report_id) + '">下载 PDF</button>'
        : '<span class="muted small">' + fmt.escapeHtml(item.error || "等待生成") + "</span>";
      return "<tr>" +
        '<td class="mono nowrap">' + fmt.escapeHtml(item.report_id) + "</td>" +
        '<td class="mono">' + fmt.escapeHtml(item.alert_id) + "</td>" +
        "<td>" + fmt.escapeHtml(item.title) + "</td>" +
        "<td>" + statusPill(item.status) + "</td>" +
        "<td>" + fmt.escapeHtml(item.created_by || "—") + "</td>" +
        '<td class="nowrap">' + fmt.dateTime(item.created_at) + "</td>" +
        '<td class="actions">' + actions + "</td>" +
        "</tr>";
    }).join("");

    body.innerHTML = '<div class="table-wrap"><table class="data"><thead><tr>' +
      "<th>报告编号</th><th>预警编号</th><th>标题</th><th>状态</th><th>生成人</th><th>生成时间</th><th>操作</th>" +
      "</tr></thead><tbody>" + rows + "</tbody></table></div>";

    body.appendChild(fmt.pager(data, (page) => {
      state.page = page;
      loadReports();
    }));

    body.querySelectorAll("[data-download]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const id = btn.dataset.download;
        try {
          await api.download("/reports/" + encodeURIComponent(id) + "/pdf", id + ".pdf");
        } catch (err) {
          fmt.toast(err.message || "下载失败", "error");
        }
      });
    });

    body.querySelectorAll("[data-preview]").forEach((btn) => {
      btn.addEventListener("click", () => {
        window.open("/api/reports/" + encodeURIComponent(btn.dataset.preview) + "/pdf", "_blank");
      });
    });
  }

  document.getElementById("filter-form").addEventListener("submit", (event) => {
    event.preventDefault();
    state.filters.alert_id = document.getElementById("f-alert").value.trim();
    state.filters.status = document.getElementById("f-status").value;
    state.page = 1;
    loadReports();
  });

  document.getElementById("reset-btn").addEventListener("click", () => {
    document.getElementById("filter-form").reset();
    state.filters = { alert_id: "", status: "" };
    state.page = 1;
    loadReports();
  });

  document.getElementById("refresh-btn").addEventListener("click", loadReports);

  document.getElementById("create-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const alertId = document.getElementById("c-alert").value.trim();
    if (!alertId) return;
    const btn = document.getElementById("create-btn");
    btn.disabled = true;
    btn.textContent = "生成中…";
    try {
      const report = await api.post("/reports", {
        alert_id: alertId,
        report_type: document.getElementById("c-type").value,
      });
      fmt.toast("报告已生成，开始下载 PDF", "success");
      await api.download("/reports/" + encodeURIComponent(report.report_id) + "/pdf", report.report_id + ".pdf");
      state.page = 1;
      await loadReports();
    } catch (err) {
      fmt.toast(err.message || "报告生成失败", "error");
    } finally {
      btn.disabled = false;
      btn.textContent = "生成 PDF";
    }
  });

  const prefill = fmt.qs("alert_id");
  if (prefill) {
    document.getElementById("c-alert").value = prefill;
    document.getElementById("f-alert").value = prefill;
    state.filters.alert_id = prefill;
  }

  window.QD.layout.renderHeader();
  loadReports();
})();

(function (global) {
  "use strict";

  const RISK_LABELS = { high: "高危", mid: "中危", low: "低危" };
  const STATUS_LABELS = { pending: "待处理", confirmed: "确认可疑", dismissed: "已排除" };
  const DIRECTION_LABELS = { inbound: "收入", outbound: "支出" };

  function escapeHtml(value) {
    if (value === undefined || value === null) return "";
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function number(value, digits) {
    const n = Number(value);
    if (!Number.isFinite(n)) return "—";
    return n.toLocaleString("zh-CN", {
      minimumFractionDigits: digits === undefined ? 0 : digits,
      maximumFractionDigits: digits === undefined ? 0 : digits,
    });
  }

  function money(value, digits) {
    const n = Number(value);
    if (!Number.isFinite(n)) return "—";
    return n.toLocaleString("zh-CN", {
      minimumFractionDigits: digits === undefined ? 2 : digits,
      maximumFractionDigits: digits === undefined ? 2 : digits,
    });
  }

  function percent(value, digits) {
    const n = Number(value);
    if (!Number.isFinite(n)) return "—";
    return (n * 100).toFixed(digits === undefined ? 2 : digits) + "%";
  }

  function pad(n) {
    return String(n).padStart(2, "0");
  }

  function dateTime(value) {
    if (!value) return "—";
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return String(value).replace("T", " ").slice(0, 19);
    return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()) +
      " " + pad(d.getHours()) + ":" + pad(d.getMinutes());
  }

  function riskLabel(level) {
    return RISK_LABELS[level] || level || "—";
  }

  function statusLabel(status) {
    return STATUS_LABELS[status] || status || "—";
  }

  function directionLabel(value) {
    return DIRECTION_LABELS[value] || value || "—";
  }

  function riskPill(level) {
    return '<span class="pill pill-' + escapeHtml(level) + '">' + escapeHtml(riskLabel(level)) + "</span>";
  }

  function statusPill(status) {
    const cls = status === "confirmed" ? "pill-green" : status === "dismissed" ? "pill-low" : "pill-mid";
    return '<span class="pill ' + cls + '">' + escapeHtml(statusLabel(status)) + "</span>";
  }

  function scoreBar(score, level) {
    const width = Math.max(2, Math.min(100, Number(score || 0) * 100));
    return '<div class="score-cell"><span class="mono">' + Number(score || 0).toFixed(3) +
      '</span><span class="score-bar risk-' + escapeHtml(level || "low") + '"><i style="width:' + width + '%"></i></span></div>';
  }

  function qs(name) {
    return new URLSearchParams(window.location.search).get(name);
  }

  function debounce(fn, wait) {
    let timer = null;
    return function () {
      const args = arguments;
      clearTimeout(timer);
      timer = setTimeout(() => fn.apply(null, args), wait || 300);
    };
  }

  function toast(message, type) {
    let wrap = document.querySelector(".toast-wrap");
    if (!wrap) {
      wrap = document.createElement("div");
      wrap.className = "toast-wrap";
      document.body.appendChild(wrap);
    }
    const item = document.createElement("div");
    item.className = "toast " + (type || "");
    item.textContent = message;
    wrap.appendChild(item);
    setTimeout(() => item.remove(), 3200);
  }

  function pager(info, onChange) {
    const pages = info.pages || 0;
    const current = info.page || 1;
    const total = info.total || 0;
    let buttons = "";
    const start = Math.max(1, current - 2);
    const end = Math.min(pages, start + 4);
    if (start > 1) buttons += '<button class="pager-btn" data-page="1">1</button>';
    if (start > 2) buttons += '<span class="muted">…</span>';
    for (let p = start; p <= end; p += 1) {
      buttons += '<button class="pager-btn ' + (p === current ? "active" : "") + '" data-page="' + p + '">' + p + "</button>";
    }
    if (end < pages - 1) buttons += '<span class="muted">…</span>';
    if (end < pages) buttons += '<button class="pager-btn" data-page="' + pages + '">' + pages + "</button>";

    const html = '<div class="pager"><div class="pager-info">共 ' + number(total) + " 条 · 第 " +
      number(current) + " / " + number(Math.max(pages, 1)) + " 页</div><div class=\"pager-btns\">" +
      '<button class="pager-btn" data-page="' + (current - 1) + '" ' + (current <= 1 ? "disabled" : "") + ">上一页</button>" +
      buttons +
      '<button class="pager-btn" data-page="' + (current + 1) + '" ' + (current >= pages ? "disabled" : "") + ">下一页</button>" +
      "</div></div>";

    const node = document.createElement("div");
    node.innerHTML = html;
    node.querySelectorAll("[data-page]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const page = Number(btn.dataset.page);
        if (page >= 1 && page <= pages && page !== current) onChange(page);
      });
    });
    return node;
  }

  function setLoading(container, text) {
    container.innerHTML = '<div class="loading"><span class="spinner"></span>' + escapeHtml(text || "加载中") + "</div>";
  }

  function setError(container, message, retry) {
    container.innerHTML = '<div class="error-box">' + escapeHtml(message) + "</div>";
    if (retry) {
      const btn = document.createElement("button");
      btn.className = "btn";
      btn.style.marginTop = "10px";
      btn.textContent = "重试";
      btn.addEventListener("click", retry);
      container.appendChild(btn);
    }
  }

  global.QD = global.QD || {};
  global.QD.fmt = {
    escapeHtml, number, money, percent, dateTime,
    riskLabel, statusLabel, directionLabel,
    riskPill, statusPill, scoreBar, qs, debounce,
    toast, pager, setLoading, setError,
  };
})(window);

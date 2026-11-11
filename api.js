(function (global) {
  "use strict";

  const BASE = "/api";

  class ApiError extends Error {
    constructor(message, status, payload) {
      super(message);
      this.name = "ApiError";
      this.status = status;
      this.payload = payload;
    }
  }

  function buildUrl(path, query) {
    const url = new URL(BASE + path, window.location.origin);
    if (query) {
      Object.entries(query).forEach(([key, value]) => {
        if (value === undefined || value === null || value === "") return;
        url.searchParams.set(key, value);
      });
    }
    return url.pathname + url.search;
  }

  async function request(path, options) {
    const opts = options || {};
    const headers = Object.assign({ Accept: "application/json" }, opts.headers || {});
    const token = localStorage.getItem("qd_token");
    if (token) headers.Authorization = "Bearer " + token;

    let body = opts.body;
    if (body !== undefined && !(body instanceof FormData)) {
      headers["Content-Type"] = "application/json";
      body = JSON.stringify(body);
    }

    const response = await fetch(buildUrl(path, opts.query), {
      method: opts.method || "GET",
      headers,
      body,
      credentials: "same-origin",
    });

    if (response.status === 401) {
      const next = encodeURIComponent(window.location.pathname + window.location.hash);
      if (!/login\.html/.test(window.location.pathname)) {
        window.location.href = "/login.html?next=" + next;
      }
      throw new ApiError("登录已失效，请重新登录", 401, null);
    }

    const contentType = response.headers.get("content-type") || "";
    const payload = contentType.includes("application/json")
      ? await response.json().catch(() => null)
      : await response.text();

    if (!response.ok) {
      const detail = payload && payload.detail ? payload.detail : "请求失败（HTTP " + response.status + "）";
      throw new ApiError(typeof detail === "string" ? detail : JSON.stringify(detail), response.status, payload);
    }
    return payload;
  }

  async function download(path, filename) {
    const response = await fetch(BASE + path, { credentials: "same-origin" });
    if (!response.ok) {
      let detail = "下载失败（HTTP " + response.status + "）";
      try {
        const payload = await response.json();
        if (payload && payload.detail) detail = payload.detail;
      } catch (err) {
        /* keep default */
      }
      throw new ApiError(detail, response.status, null);
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename || "download";
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
  }

  global.QD = global.QD || {};
  global.QD.api = {
    ApiError,
    get: (path, query) => request(path, { query }),
    post: (path, body) => request(path, { method: "POST", body }),
    patch: (path, body) => request(path, { method: "PATCH", body }),
    del: (path) => request(path, { method: "DELETE" }),
    download,
  };
})(window);

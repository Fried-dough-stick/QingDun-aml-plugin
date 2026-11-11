(function (global) {
  "use strict";

  const GREEN = "#10b981";
  const COLORS = ["#10b981", "#3b82f6", "#f59e0b", "#ef4444", "#8b5cf6", "#14b8a6"];
  const registry = new Set();

  function init(el) {
    if (!el || !global.echarts) return null;
    if (el.__qdChart) el.__qdChart.dispose();
    const chart = global.echarts.init(el, null, { renderer: "canvas" });
    el.__qdChart = chart;
    registry.add(chart);
    return chart;
  }

  function line(el, labels, values, name) {
    const chart = init(el);
    if (!chart) return null;
    chart.setOption({
      grid: { left: 46, right: 16, top: 24, bottom: 30 },
      tooltip: { trigger: "axis" },
      xAxis: {
        type: "category",
        data: labels,
        axisLine: { lineStyle: { color: "#e2e8f0" } },
        axisLabel: { color: "#64748b", fontSize: 10, hideOverlap: true },
      },
      yAxis: {
        type: "value",
        splitLine: { lineStyle: { color: "#f1f5f9" } },
        axisLabel: { color: "#64748b", fontSize: 10 },
      },
      series: [{
        name: name || "交易笔数",
        type: "line",
        data: values,
        smooth: true,
        symbolSize: 5,
        lineStyle: { color: GREEN, width: 2 },
        itemStyle: { color: GREEN },
        areaStyle: { color: "rgba(16,185,129,.12)" },
      }],
    });
    return chart;
  }

  function bars(el, categories, values, name) {
    const chart = init(el);
    if (!chart) return null;
    chart.setOption({
      grid: { left: 46, right: 16, top: 24, bottom: 30 },
      tooltip: { trigger: "axis" },
      xAxis: {
        type: "category",
        data: categories,
        axisLine: { lineStyle: { color: "#e2e8f0" } },
        axisLabel: { color: "#64748b", fontSize: 10 },
      },
      yAxis: {
        type: "value",
        splitLine: { lineStyle: { color: "#f1f5f9" } },
        axisLabel: { color: "#64748b", fontSize: 10 },
      },
      series: [{
        name: name || "数量",
        type: "bar",
        data: values,
        barMaxWidth: 32,
        itemStyle: { color: GREEN, borderRadius: [5, 5, 0, 0] },
      }],
    });
    return chart;
  }

  function donut(el, data) {
    const chart = init(el);
    if (!chart) return null;
    chart.setOption({
      color: COLORS,
      tooltip: { trigger: "item" },
      legend: { bottom: 0, textStyle: { color: "#64748b", fontSize: 11 } },
      series: [{
        type: "pie",
        radius: ["46%", "68%"],
        center: ["50%", "44%"],
        avoidLabelOverlap: true,
        itemStyle: { borderColor: "#fff", borderWidth: 2 },
        label: { show: false },
        data: data,
      }],
    });
    return chart;
  }

  function downloadPng(chart, filename) {
    if (!chart) return;
    const url = chart.getDataURL({ type: "png", pixelRatio: 2, backgroundColor: "#ffffff" });
    const link = document.createElement("a");
    link.href = url;
    link.download = filename || "chart.png";
    document.body.appendChild(link);
    link.click();
    link.remove();
  }

  window.addEventListener("resize", () => registry.forEach((chart) => chart.resize()));

  global.QD = global.QD || {};
  global.QD.charts = { init, line, bars, donut, downloadPng, COLORS };
})(window);

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from backend.app.core.config import BASE_DIR, get_settings
from backend.app.models.entities import Account, Alert, AlertFactor, RiskScore, Txn

_FONT_NAME: str | None = None


def _register_font() -> str:
    global _FONT_NAME
    if _FONT_NAME:
        return _FONT_NAME

    settings = get_settings()
    candidates: list[tuple[Path, int]] = [
        (Path(os.getenv("PDF_FONT_PATH", "")), 0),
        (settings.frontend_dir / "assets" / "fonts" / "NotoSansSC-Regular.otf", 0),
        (Path("C:/Windows/Fonts/msyh.ttc"), 0),
        (Path("C:/Windows/Fonts/simhei.ttf"), 0),
        (Path("C:/Windows/Fonts/simsun.ttc"), 0),
        (Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"), 0),
        (Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"), 0),
    ]
    for path, index in candidates:
        if not path or not str(path) or not path.exists():
            continue
        try:
            pdfmetrics.registerFont(TTFont("QDCN", str(path), subfontIndex=index))
            _FONT_NAME = "QDCN"
            return _FONT_NAME
        except Exception:
            continue

    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    _FONT_NAME = "STSong-Light"
    return _FONT_NAME


def _styles():
    font = _register_font()
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "QDTitle",
            parent=base["Title"],
            fontName=font,
            fontSize=20,
            leading=28,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#0f172a"),
            spaceAfter=4,
        ),
        "subtitle": ParagraphStyle(
            "QDSubtitle",
            parent=base["Normal"],
            fontName=font,
            fontSize=9,
            leading=14,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#64748b"),
        ),
        "h2": ParagraphStyle(
            "QDH2",
            parent=base["Heading2"],
            fontName=font,
            fontSize=12.5,
            leading=18,
            textColor=colors.HexColor("#0e9f6e"),
            spaceBefore=12,
            spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "QDBody",
            parent=base["BodyText"],
            fontName=font,
            fontSize=9.5,
            leading=16,
            textColor=colors.HexColor("#334155"),
            alignment=TA_LEFT,
        ),
        "small": ParagraphStyle(
            "QDSmall",
            parent=base["BodyText"],
            fontName=font,
            fontSize=8,
            leading=12,
            textColor=colors.HexColor("#64748b"),
        ),
        "cell": ParagraphStyle(
            "QDCell",
            parent=base["BodyText"],
            fontName=font,
            fontSize=8.5,
            leading=13,
            textColor=colors.HexColor("#334155"),
        ),
    }


def _p(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(escape(str(text)), style)


def _kv_table(rows: list[tuple[str, str]], styles) -> Table:
    data = [[_p(k, styles["cell"]), _p(v, styles["cell"])] for k, v in rows]
    table = Table(data, colWidths=[42 * mm, 122 * mm], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f8fafc")),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e2e8f0")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def _factor_table(factors: list[AlertFactor], styles) -> Table:
    header = ["排名", "特征", "取值", "SHAP (log-odds)", "方向"]
    data = [[_p(item, styles["cell"]) for item in header]]
    for factor in factors:
        data.append(
            [
                _p(str(factor.rank), styles["cell"]),
                _p(factor.feature_label, styles["cell"]),
                _p(f"{factor.value:.4g}", styles["cell"]),
                _p(f"{factor.shap_value:+.4f}", styles["cell"]),
                _p("推高可疑" if factor.direction == "up" else "压低可疑", styles["cell"]),
            ]
        )
    if len(data) == 1:
        data.append([_p("暂无因子", styles["cell"])] + [""] * 4)
    table = Table(data, colWidths=[14 * mm, 50 * mm, 32 * mm, 34 * mm, 34 * mm], repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8f8f1")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#0e7a5f")),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e2e8f0")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def _analysis_text(alert: Alert, risk: RiskScore | None, factors: list[AlertFactor]) -> str:
    up = [f for f in factors if f.direction == "up"][:3]
    down = [f for f in factors if f.direction == "down"][:3]
    parts = [
        f"该笔交易的综合风险分为 {alert.risk_score:.4f}，等级为 {alert.risk_level}。",
    ]
    if risk:
        parts.append(f"其中模型分 {risk.model_score:.4f}，规则分 {risk.rule_score:.4f}。")
    if up:
        parts.append(
            "推高可疑度的主要因素为："
            + "；".join(f"{f.feature_label}（取值 {f.value:.4g}，SHAP {f.shap_value:+.3f}）" for f in up)
            + "。"
        )
    if down:
        parts.append(
            "压低可疑度的主要因素为："
            + "；".join(f"{f.feature_label}（取值 {f.value:.4g}，SHAP {f.shap_value:+.3f}）" for f in down)
            + "。"
        )
    parts.append(
        "以上归因反映模型与规则的综合评分，不代表对交易性质的最终认定；"
        "应结合客户尽调、交易背景和账户历史行为由分析师复核。"
    )
    return "".join(parts)


def build_report_pdf(
    out_path: Path,
    report_id: str,
    alert: Alert,
    txn: Txn,
    risk: RiskScore | None,
    account: Account | None,
    factors: list[AlertFactor],
    account_txn_count: int,
    account_total_amount: float,
) -> Path:
    styles = _styles()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now()

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont(_register_font(), 7.5)
        canvas.setFillColor(colors.HexColor("#94a3b8"))
        canvas.drawString(20 * mm, 12 * mm, "青盾 2.0 · 反洗钱风险分析（合成数据演示）")
        canvas.drawRightString(190 * mm, 12 * mm, f"第 {doc.page} 页")
        canvas.restoreState()

    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=f"可疑交易分析报告 {report_id}",
        author="青盾 2.0",
    )

    story = [
        _p("可疑交易分析报告", styles["title"]),
        _p(f"报告编号：{report_id} · 生成时间：{now:%Y-%m-%d %H:%M} · 模型版本：xgb-v1", styles["subtitle"]),
        Spacer(1, 6 * mm),
        _p("一、报告头", styles["h2"]),
        _kv_table(
            [
                ("预警编号", alert.alert_id),
                ("数据来源", "VynFi AML-100K 合成数据"),
                ("报告用途", "分析师复核辅助，不构成对交易合法性的认定"),
                ("风险等级", {"high": "高危", "mid": "中危", "low": "低危"}.get(alert.risk_level, alert.risk_level)),
            ],
            styles,
        ),
        _p("二、账户信息", styles["h2"]),
        _kv_table(
            [
                ("账户编号", alert.account_id),
                ("账户交易数", f"{account_txn_count:,}"),
                ("账户累计金额", f"{account_total_amount:,.2f}"),
                ("账户状态", "正常（合成数据）"),
            ],
            styles,
        ),
        _p("三、交易摘要", styles["h2"]),
        _kv_table(
            [
                ("交易编号", txn.txn_id),
                ("交易时间", txn.ts_initiated.strftime("%Y-%m-%d %H:%M:%S")),
                ("金额 / 币种", f"{float(txn.amount):,.2f} {txn.currency}"),
                ("方向 / 渠道", f"{txn.direction} / {txn.channel}"),
                ("类别 / MCC", f"{txn.category} / {txn.mcc if txn.mcc is not None else '—'}"),
                ("对手方", f"{txn.counterparty_name or '—'}（{txn.counterparty_country or '—'}）"),
                ("授权状态", "已授权" if txn.is_authorized else "未授权"),
            ],
            styles,
        ),
        _p("四、证据链", styles["h2"]),
        _p(
            "规则命中："
            + ("；".join(risk.rule_hits or []) if risk and risk.rule_hits else "无"),
            styles["body"],
        ),
        Spacer(1, 2 * mm),
        _p(
            f"综合评分：{alert.risk_score:.4f}（模型 {risk.model_score:.4f} + 规则 {risk.rule_score:.4f}）"
            if risk
            else f"综合评分：{alert.risk_score:.4f}",
            styles["body"],
        ),
        _p("五、风险因子", styles["h2"]),
        _factor_table(factors, styles),
        _p("六、初步分析", styles["h2"]),
        _p(_analysis_text(alert, risk, factors), styles["body"]),
        _p("七、处置建议", styles["h2"]),
        _p("1. 由分析师复核账户历史行为、对手方背景和交易目的，必要时补充客户尽调材料。", styles["body"]),
        _p("2. 如复核仍无法排除可疑，按行内流程提交可疑交易报告（SAR）草稿并走复核。", styles["body"]),
        _p("3. 本系统只提供风险建议，不拦截交易；任何限制措施须由人工按制度决定。", styles["body"]),
        _p("八、声明", styles["h2"]),
        _p(
            "本报告基于合成数据与模型输出自动生成，仅用于产品演示和风险分析辅助。"
            "报告中的评分、因子和排序不构成对任何交易、账户或个人的法律定性。",
            styles["small"],
        ),
    ]

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return out_path

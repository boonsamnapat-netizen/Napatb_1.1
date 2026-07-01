"""Render the performance analytics payload as a self-contained HTML dashboard.

No external JS/CSS/CDN — charts are inline SVG so the file opens anywhere
(browser, GitHub preview, mobile) and survives being committed to the repo.
Also exports a couple of matplotlib PNGs for Telegram (optional dependency).

Public:
  render_html(report)     -> str (full HTML document)
  save_pngs(report, dir)  -> list[str] (equity + R-distribution PNGs, if matplotlib)
"""

from __future__ import annotations

import html
import pathlib

# ---- palette (dark, honest, readable) --------------------------------------
BG = "#0d1117"
CARD = "#161b22"
GRID = "#30363d"
FG = "#e6edf3"
MUTED = "#8b949e"
GREEN = "#3fb950"
RED = "#f85149"
BLUE = "#58a6ff"
AMBER = "#d29922"


def _fmt(v, pct=False, r=False, signed=False):
    if v is None:
        return "—"
    if isinstance(v, str):
        return html.escape(v)
    s = f"{v:+.2f}" if signed else f"{v:.2f}"
    if pct:
        s += "%"
    if r:
        s += "R"
    return s


# ---------------------------------------------------------------- charts -----
def _line_svg(values, dates=None, w=760, h=220, pad=34, color=BLUE, zero_line=True):
    if not values:
        return "<div class='muted'>ไม่มีข้อมูล</div>"
    lo, hi = min(values), max(values)
    if hi == lo:
        hi += 1
        lo -= 1
    span = hi - lo

    def x(i):
        return pad + (w - 2 * pad) * (i / max(1, len(values) - 1))

    def y(v):
        return pad + (h - 2 * pad) * (1 - (v - lo) / span)

    pts = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(values))
    area = f"{pad},{h - pad} " + pts + f" {x(len(values) - 1):.1f},{h - pad}"
    zero = ""
    if zero_line and lo < 0 < hi:
        zy = y(0)
        zero = f"<line x1='{pad}' y1='{zy:.1f}' x2='{w - pad}' y2='{zy:.1f}' stroke='{MUTED}' stroke-dasharray='4 4' stroke-width='1'/>"
    # y-axis labels (min / max)
    labels = (
        f"<text x='4' y='{y(hi) + 4:.1f}' fill='{MUTED}' font-size='11'>{hi:.1f}</text>"
        f"<text x='4' y='{y(lo) + 4:.1f}' fill='{MUTED}' font-size='11'>{lo:.1f}</text>"
    )
    xlab = ""
    if dates and dates[0] and dates[-1]:
        xlab = (
            f"<text x='{pad}' y='{h - 8}' fill='{MUTED}' font-size='11'>{html.escape(str(dates[0]))}</text>"
            f"<text x='{w - pad}' y='{h - 8}' fill='{MUTED}' font-size='11' text-anchor='end'>{html.escape(str(dates[-1]))}</text>"
        )
    return (
        f"<svg viewBox='0 0 {w} {h}' width='100%' preserveAspectRatio='xMidYMid meet'>"
        f"<polygon points='{area}' fill='{color}' opacity='0.10'/>"
        f"{zero}<polyline points='{pts}' fill='none' stroke='{color}' stroke-width='2'/>"
        f"{labels}{xlab}</svg>"
    )


def _bars_svg(labels, counts, w=760, h=230, pad=34):
    if not counts or max(counts) == 0:
        return "<div class='muted'>ไม่มีข้อมูล</div>"
    n = len(counts)
    mx = max(counts)
    bw = (w - 2 * pad) / n
    bars = []
    for i, c in enumerate(counts):
        bh = (h - 2 * pad) * (c / mx)
        bx = pad + i * bw
        by = h - pad - bh
        # colour: negative buckets red, positive green (label like "-1..-0.5")
        neg = labels[i].strip().startswith("-")
        col = RED if neg else GREEN
        bars.append(
            f"<rect x='{bx + 3:.1f}' y='{by:.1f}' width='{bw - 6:.1f}' height='{bh:.1f}' fill='{col}' opacity='0.75' rx='2'/>"
            f"<text x='{bx + bw / 2:.1f}' y='{by - 4:.1f}' fill='{FG}' font-size='10' text-anchor='middle'>{c}</text>"
            f"<text x='{bx + bw / 2:.1f}' y='{h - pad + 14:.1f}' fill='{MUTED}' font-size='9' text-anchor='middle'>{html.escape(labels[i])}</text>"
        )
    return f"<svg viewBox='0 0 {w} {h}' width='100%'>{''.join(bars)}</svg>"


# ---------------------------------------------------------------- pieces -----
def _kpi(label, value, tone="", sub=""):
    color = {"good": GREEN, "bad": RED, "warn": AMBER}.get(tone, FG)
    subhtml = f"<div class='kpi-sub'>{html.escape(sub)}</div>" if sub else ""
    return (
        f"<div class='kpi'><div class='kpi-label'>{html.escape(label)}</div>"
        f"<div class='kpi-val' style='color:{color}'>{value}</div>{subhtml}</div>"
    )


def _table(headers, rows):
    head = "".join(f"<th>{html.escape(h)}</th>" for h in headers)
    body = ""
    for r in rows:
        cells = ""
        for c in r:
            cls = ""
            if isinstance(c, tuple):
                c, cls = c
            cells += f"<td class='{cls}'>{c}</td>"
        body += f"<tr>{cells}</tr>"
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _tone_cell(v, pct=False, r=False):
    if v is None:
        return ("—", "muted")
    cls = "pos" if v > 0 else ("neg" if v < 0 else "")
    return (_fmt(v, pct=pct, r=r, signed=True), cls)


# ------------------------------------------------------------- top render ----
def render_html(report: dict) -> str:
    s = report.get("summary", {})
    if not s or s.get("trades", 0) == 0:
        return _shell("<p class='muted'>ยังไม่มี trade ให้วิเคราะห์</p>", report)

    exp = s.get("expectancy_r")
    exp_tone = "good" if (exp or 0) > 0 else "bad"
    kpis = "".join([
        _kpi("Trades (OOS)", s["trades"], sub="walk-forward, net of fees"),
        _kpi("Expectancy", _fmt(exp, r=True, signed=True), exp_tone, "edge ต่อไม้"),
        _kpi("Win rate", _fmt(s["win_rate"] * 100, pct=True), sub=f"{s['wins']}W / {s['losses']}L"),
        _kpi("Total R", _fmt(s["total_r"], r=True, signed=True),
             "good" if s["total_r"] > 0 else "bad"),
        _kpi("Profit factor", _fmt(s.get("profit_factor")),
             "good" if (s.get("profit_factor") or 0) > 1 else "bad"),
        _kpi("Payoff", _fmt(s.get("payoff_ratio")), sub="avg win / avg loss"),
        _kpi("Max DD", _fmt(s["max_drawdown_r"], r=True), "warn",
             f"{_fmt(s['max_drawdown_pct'], pct=True)} @ {s['risk_per_trade_pct']}%/ไม้"),
        _kpi("Sharpe (ต่อไม้)", _fmt(s.get("sharpe")), sub=f"Sortino {_fmt(s.get('sortino'))}"),
        _kpi("Compounded", _fmt(s.get("return_pct"), pct=True, signed=True),
             "good" if (s.get("return_pct") or 0) > 0 else "bad",
             f"@ {s['risk_per_trade_pct']}%/ไม้"),
        _kpi("Kelly", _fmt(s.get("kelly_fraction")), sub="ขนาดพนันเชิงทฤษฎี (ระวัง)"),
        _kpi("Best / Worst", f"{_fmt(s['best_r'], r=True, signed=True)} / {_fmt(s['worst_r'], r=True, signed=True)}"),
        _kpi("Streaks", f"{s['longest_win_streak']}W / {s['longest_loss_streak']}L",
             sub="ชนะ/แพ้ติดต่อกันยาวสุด"),
    ])

    eq = report.get("equity", {})
    dd = report.get("drawdown", {})
    hist = report.get("r_histogram", {})

    # per-coin table
    coin_rows = []
    for c in report.get("by_symbol", []):
        coin_rows.append([
            html.escape(str(c["key"])), str(c["trades"]),
            (_fmt(c["win_rate"] * 100, pct=True), ""),
            _tone_cell(c["expectancy_r"], r=True),
            _tone_cell(c["total_r"], r=True),
            (_fmt(c["max_drawdown_r"], r=True), "muted"),
            (_fmt(c.get("profit_factor")), ""),
        ])
    coin_tbl = _table(["เหรียญ", "ไม้", "WR", "Exp/ไม้", "Total R", "Max DD", "PF"], coin_rows)

    # confidence buckets
    conf_rows = [[
        html.escape(str(c["key"])), str(c["trades"]),
        (_fmt(c["win_rate"] * 100, pct=True), ""),
        _tone_cell(c["expectancy_r"], r=True),
        _tone_cell(c["total_r"], r=True),
    ] for c in report.get("by_confidence", [])]
    conf_tbl = _table(["Confidence", "ไม้", "WR", "Exp/ไม้", "Total R"], conf_rows)

    # direction
    dir_rows = [[
        html.escape(str(c["key"])), str(c["trades"]),
        (_fmt(c["win_rate"] * 100, pct=True), ""),
        _tone_cell(c["expectancy_r"], r=True),
        _tone_cell(c["total_r"], r=True),
    ] for c in report.get("by_direction", [])]
    dir_tbl = _table(["ทิศทาง", "ไม้", "WR", "Exp/ไม้", "Total R"], dir_rows)

    # month
    mon_rows = [[
        html.escape(str(c["key"])), str(c["trades"]),
        _tone_cell(c["total_r"], r=True),
        _tone_cell(c["expectancy_r"], r=True),
    ] for c in report.get("by_month", [])]
    mon_tbl = _table(["เดือน", "ไม้", "Total R", "Exp/ไม้"], mon_rows)

    fwd_html = _forward_section(report.get("forward"))

    body = f"""
    <section class='kpis'>{kpis}</section>

    <div class='grid2'>
      <div class='card'><h2>Equity curve — สะสม R</h2>{_line_svg(eq.get('equity_r', []), eq.get('dates'), color=GREEN)}</div>
      <div class='card'><h2>Drawdown (R)</h2>{_line_svg(dd.get('dd_r', []), eq.get('dates'), color=RED, zero_line=False)}</div>
    </div>
    <p class='note'>ℹ️ Equity/Drawdown/Compounded ด้านล่างเป็นการ<b>ต่อทุกไม้ของทุกเหรียญเรียงกันเป็นสายเดียว</b>
      (เสมือนถือทีละไม้ เสี่ยง {s['risk_per_trade_pct']}%/ไม้) — เป็นมุมมอง<b>แย่สุด</b>ที่ไม่นับการกระจายพอร์ต
      ดังนั้น max DD รวม (−{abs(s['max_drawdown_r']):.0f}R) จะเกินจริง; DD ที่เจอต่อเหรียญจริงดูจากคอลัมน์ “Max DD” ในตารางรายเหรียญ
      (ราว −5..−24R). ตัวเลขที่เชื่อถือได้สุดคือ <b>expectancy/ไม้</b> และ <b>Total R</b>.</p>

    <div class='grid2'>
      <div class='card'><h2>Equity แบบทบต้น (%) @ {s['risk_per_trade_pct']}%/ไม้</h2>{_line_svg(eq.get('equity_pct', []), eq.get('dates'), color=BLUE)}</div>
      <div class='card'><h2>การกระจาย R ต่อไม้</h2>{_bars_svg(hist.get('labels', []), hist.get('counts', []))}</div>
    </div>

    {fwd_html}

    <div class='grid2'>
      <div class='card'><h2>รายเหรียญ</h2>{coin_tbl}</div>
      <div class='card'>
        <h2>ตาม Confidence</h2>{conf_tbl}
        <h2 style='margin-top:18px'>ตามทิศทาง</h2>{dir_tbl}
      </div>
    </div>

    <div class='card'><h2>รายเดือน</h2>{mon_tbl}</div>
    """
    return _shell(body, report)


def _forward_section(fwd: dict | None) -> str:
    if not fwd:
        return ""
    closed = fwd.get("closed", 0)
    delta = fwd.get("delta_r")
    tone = "" if delta is None else ("pos" if delta >= 0 else "neg")
    note = (
        "ยังไม่มีสัญญาณ live ที่ปิดแล้วพอจะสรุป (log กำลังสะสม)"
        if not closed else
        f"live เฉลี่ย {_fmt(fwd.get('live_avg_r'), r=True, signed=True)} เทียบ backtest "
        f"{_fmt(fwd.get('backtest_expectancy_r'), r=True, signed=True)} "
        f"→ ส่วนต่าง <span class='{tone}'>{_fmt(delta, r=True, signed=True)}</span>"
    )
    cards = "".join([
        _kpi("สัญญาณทั้งหมด", fwd.get("total", 0)),
        _kpi("ยังเปิด", fwd.get("open", 0)),
        _kpi("ปิดแล้ว", closed),
        _kpi("Live total R", _fmt(fwd.get("total_r"), r=True, signed=True) if fwd.get("total_r") is not None else "—"),
    ])
    return f"""
    <div class='card'>
      <h2>Forward-test (สัญญาณจริงที่ยิงเข้า Telegram)</h2>
      <section class='kpis small'>{cards}</section>
      <p class='muted' style='margin-top:8px'>{note}</p>
    </div>"""


def _shell(body: str, report: dict) -> str:
    gen = html.escape(str(report.get("generated_at") or ""))
    label = html.escape(str(report.get("config_label") or ""))
    return f"""<!doctype html><html lang='th'><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width, initial-scale=1'>
<title>Napatb — Performance Dashboard</title>
<style>
  :root {{ color-scheme: dark; }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; background:{BG}; color:{FG};
    font-family: -apple-system, 'Segoe UI', 'Noto Sans Thai', Roboto, sans-serif; }}
  header {{ padding:22px 26px; border-bottom:1px solid {GRID}; }}
  header h1 {{ margin:0; font-size:20px; }}
  header .meta {{ color:{MUTED}; font-size:13px; margin-top:6px; }}
  main {{ padding:20px 26px 60px; max-width:1200px; margin:0 auto; }}
  h2 {{ font-size:14px; color:{MUTED}; margin:0 0 12px; font-weight:600;
    text-transform:uppercase; letter-spacing:.4px; }}
  .kpis {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
    gap:12px; margin-bottom:20px; }}
  .kpis.small {{ grid-template-columns:repeat(auto-fit,minmax(120px,1fr)); }}
  .kpi {{ background:{CARD}; border:1px solid {GRID}; border-radius:10px; padding:14px 16px; }}
  .kpi-label {{ color:{MUTED}; font-size:12px; }}
  .kpi-val {{ font-size:24px; font-weight:700; margin-top:4px; }}
  .kpi-sub {{ color:{MUTED}; font-size:11px; margin-top:2px; }}
  .card {{ background:{CARD}; border:1px solid {GRID}; border-radius:12px; padding:18px; margin-bottom:16px; }}
  .grid2 {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; }}
  @media (max-width:820px) {{ .grid2 {{ grid-template-columns:1fr; }} }}
  table {{ width:100%; border-collapse:collapse; font-size:13px; }}
  th, td {{ text-align:right; padding:7px 8px; border-bottom:1px solid {GRID}; }}
  th:first-child, td:first-child {{ text-align:left; }}
  th {{ color:{MUTED}; font-weight:600; }}
  .pos {{ color:{GREEN}; }} .neg {{ color:{RED}; }} .muted {{ color:{MUTED}; }}
  .note {{ background:rgba(210,153,34,0.08); border:1px solid {AMBER}; border-radius:10px;
    padding:12px 16px; font-size:13px; color:{FG}; line-height:1.6; margin:0 0 16px; }}
  .note b {{ color:{AMBER}; }}
  footer {{ color:{MUTED}; font-size:12px; padding:0 26px 40px; max-width:1200px; margin:0 auto; }}
</style></head><body>
<header>
  <h1>📊 Napatb — Performance Dashboard</h1>
  <div class='meta'>{label} · สร้างเมื่อ {gen}</div>
</header>
<main>{body}</main>
<footer>
  ⚠️ เพื่อการศึกษา/ช่วยตัดสินใจเท่านั้น ไม่รับประกันกำไร · ตัวเลขทั้งหมดเป็น walk-forward
  out-of-sample หักค่าธรรมเนียม/slippage แล้ว · Sharpe/Sortino เป็นค่าต่อไม้ (information ratio)
  ไม่ใช่รายปี · อดีตไม่การันตีอนาคต
</footer>
</body></html>"""


# ---------------------------------------------------------------- PNGs -------
def save_pngs(report: dict, outdir: str) -> list[str]:
    """Equity + R-distribution PNGs for Telegram. Returns [] if matplotlib absent."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:  # noqa: BLE001
        return []

    out = pathlib.Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []
    eq = report.get("equity", {})
    hist = report.get("r_histogram", {})

    if eq.get("equity_r"):
        fig, ax = plt.subplots(figsize=(8, 3.2), dpi=120)
        ax.plot(eq["equity_r"], color="#3fb950", lw=1.8)
        ax.axhline(0, color="#8b949e", lw=0.8, ls="--")
        ax.fill_between(range(len(eq["equity_r"])), eq["equity_r"], 0,
                        color="#3fb950", alpha=0.12)
        ax.set_title("Equity curve — cumulative R (OOS, net of fees)")
        ax.set_xlabel("trade #"); ax.set_ylabel("R")
        fig.tight_layout()
        p = str(out / "equity.png"); fig.savefig(p); plt.close(fig); paths.append(p)

    if hist.get("counts") and max(hist["counts"]) > 0:
        fig, ax = plt.subplots(figsize=(8, 3.2), dpi=120)
        cols = ["#f85149" if lbl.strip().startswith("-") else "#3fb950"
                for lbl in hist["labels"]]
        ax.bar(range(len(hist["counts"])), hist["counts"], color=cols, alpha=0.8)
        ax.set_xticks(range(len(hist["labels"])))
        ax.set_xticklabels(hist["labels"], rotation=45, ha="right", fontsize=7)
        ax.set_title("R-multiple distribution")
        ax.set_ylabel("trades")
        fig.tight_layout()
        p = str(out / "r_distribution.png"); fig.savefig(p); plt.close(fig); paths.append(p)

    return paths

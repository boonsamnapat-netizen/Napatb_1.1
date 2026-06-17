"""
Render a setup chart (candlesticks + EMAs + Entry/SL/TP levels) as a PNG to
attach to Telegram alerts. Pure matplotlib (Agg backend), no display needed.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from src.signal import indicators as ind  # noqa: E402

_GREEN = "#26a69a"
_RED = "#ef5350"


def make_chart(symbol: str, df, sig: dict, out_path: str, lookback: int = 140) -> str:
    """df = OHLCV entry-timeframe frame; sig = Signal.to_dict()."""
    full = ind.compute_all(df)
    d = full.tail(lookback).reset_index(drop=True)

    fig, ax = plt.subplots(figsize=(9.0, 5.0), dpi=110)

    # candlesticks
    for i, row in d.iterrows():
        up = row["close"] >= row["open"]
        color = _GREEN if up else _RED
        ax.plot([i, i], [row["low"], row["high"]], color=color, linewidth=0.8, zorder=1)
        height = abs(row["close"] - row["open"]) or (row["close"] * 1e-4)
        ax.add_patch(
            plt.Rectangle((i - 0.3, min(row["open"], row["close"])), 0.6, height,
                          color=color, zorder=2)
        )

    x = np.arange(len(d))
    for col, c, lbl in [("ema_fast", "#1e88e5", "EMA21"),
                        ("ema_mid", "#fb8c00", "EMA50"),
                        ("ema_slow", "#7e57c2", "EMA200")]:
        if col in d:
            ax.plot(x, d[col].values, color=c, linewidth=1.1, label=lbl, zorder=3)

    entry = sig.get("entry")
    sl = sig.get("stop_loss")
    if entry:
        ax.axhline(entry, color="#2962ff", ls="-", lw=1.3, label=f"Entry {entry:g}")
    if sl:
        ax.axhline(sl, color="#d50000", ls="--", lw=1.3, label=f"SL {sl:g}")
    for i, tp in enumerate(sig.get("position_plan", {}).get("take_profits", []), 1):
        ax.axhline(tp["price"], color="#00c853", ls=":", lw=1.2,
                   label=f"TP{i} {tp['price']:g}")

    direction = sig.get("direction", "")
    decision = sig.get("decision", "")
    conf = sig.get("confidence", "")
    ax.set_title(
        f"{symbol} · {sig.get('entry_timeframe','')} · {direction} {decision} "
        f"(conf {conf})", fontsize=11, fontweight="bold"
    )
    ax.legend(loc="upper left", fontsize=7, ncol=2, framealpha=0.85)
    ax.grid(alpha=0.2)
    ax.set_xticks([])
    ax.margins(x=0.01)
    fig.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)
    return out_path

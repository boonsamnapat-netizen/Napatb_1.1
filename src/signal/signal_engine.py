"""Turn a divergence into a risk-managed trade plan (Entry/SL/TP1-3/RR)."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from . import indicators
from .divergence import Divergence, detect


@dataclass
class Signal:
    symbol: str
    side: str            # "LONG" | "SHORT"
    kind: str            # "Bullish divergent" | "Bearish divergent"
    status: str          # e.g. "MACD Oversold"
    entry: float
    sl: float
    tp1: float
    tp2: float
    tp3: float
    rr: tuple[float, float, float]  # reward:risk at each TP
    risk_per_unit: float
    price_now: float

    @property
    def rr_text(self) -> str:
        a, b, c = self.rr
        return f"1:{a:.1f} / 1:{b:.1f} / 1:{c:.1f}"


def _round(x: float) -> float:
    """Adaptive rounding so cheap and expensive coins both read cleanly."""
    if x >= 1000:
        return round(x, 1)
    if x >= 1:
        return round(x, 2)
    return float(f"{x:.6g}")


def build_signal(
    symbol: str,
    df: pd.DataFrame,
    div: Divergence | None = None,
    indicator: str = "auto",
    atr_period: int = 14,
    atr_buffer: float = 0.5,
    tp_r_multiples: tuple[float, float, float] = (1.0, 2.0, 3.0),
    min_stop_pct: float = 0.3,
) -> Signal | None:
    """Build a Signal from a (detected or supplied) divergence.

    Entry  = last close.
    SL     = beyond the divergence swing, padded by `atr_buffer` * ATR
             (floored at `min_stop_pct` of price so tiny ranges can't blow up).
    TP1-3  = Entry +/- R * tp_r_multiples, where R = |Entry - SL|.
    """
    if div is None:
        div = detect(df, indicator=indicator)
    if div is None:
        return None

    entry = float(df["close"].iloc[-1])
    atr = float(indicators.atr(df, atr_period).iloc[-1])
    pad = atr * atr_buffer
    floor = entry * (min_stop_pct / 100.0)

    if div.kind == "bullish":
        side = "LONG"
        sl = div.swing_low - pad
        risk = max(entry - sl, floor)
        sl = entry - risk
        tps = [entry + risk * m for m in tp_r_multiples]
        kind = "Bullish divergent"
    else:
        side = "SHORT"
        sl = div.swing_high + pad
        risk = max(sl - entry, floor)
        sl = entry + risk
        tps = [entry - risk * m for m in tp_r_multiples]
        kind = "Bearish divergent"

    return Signal(
        symbol=symbol,
        side=side,
        kind=kind,
        status=div.status,
        entry=_round(entry),
        sl=_round(sl),
        tp1=_round(tps[0]),
        tp2=_round(tps[1]),
        tp3=_round(tps[2]),
        rr=tp_r_multiples,
        risk_per_unit=_round(risk),
        price_now=_round(entry),
    )

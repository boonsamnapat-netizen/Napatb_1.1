"""
Signal engine — the brain.

Turns raw OHLCV into an actionable plan by combining:
  - mainstream indicators (what the crowd sees),
  - multi-timeframe trend alignment (only trade with the higher timeframe),
  - key levels / liquidity (where to enter, stop, and target),
  - money management (how much to risk),
  - a news/sentiment risk gate.

Design intent: see exactly the picture the market sees, then make a more
disciplined decision around it — favour confluence, refuse low-quality setups,
and let risk management (not conviction) size the trade.

NOTE: This is decision-support tooling for analysis and education. No signal
system can guarantee profit; markets are uncertain and you can lose money.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

import pandas as pd

from src.signal import indicators as ind
from src.signal import levels as lv
from src.signal.money_management import (
    PositionPlan,
    TakeProfit,
    assumed_win_rate_from_confidence,
    build_position_plan,
)
from src.signal.news import NewsAssessment, NewsProvider

logger = logging.getLogger(__name__)

DEFAULTS = {
    "entry_timeframe": "1h",
    "htf_timeframe": "4h",
    "weights": {
        "trend": 0.35,
        "momentum": 0.30,
        "volatility": 0.15,
        "volume": 0.20,
    },
    "entry_threshold": 0.20,     # |composite| below this = no directional edge
    "min_confidence": 55.0,      # below this = WAIT (don't take the trade)
    "atr_stop_mult": 1.5,
    "min_stop_atr": 0.6,
    "max_stop_atr": 4.0,
    "tp_allocations": [50, 30, 20],
    "account_size": 1000.0,
    "risk_per_trade_pct": 1.0,
    "max_leverage_cap": 10.0,
}


@dataclass
class Signal:
    symbol: str
    entry_timeframe: str
    htf_timeframe: str
    generated_at: str

    direction: str = "NEUTRAL"          # LONG / SHORT / NEUTRAL
    decision: str = "WAIT"              # ENTER / WAIT / AVOID
    confidence: float = 0.0             # 0-100
    composite_score: float = 0.0        # -1..1 on the entry timeframe

    current_price: float = 0.0
    entry: float | None = None
    entry_zone: list[float] = field(default_factory=list)
    stop_loss: float | None = None

    position_plan: dict = field(default_factory=dict)
    scores: dict = field(default_factory=dict)
    indicators: dict = field(default_factory=dict)
    levels: list[dict] = field(default_factory=list)
    news: dict = field(default_factory=dict)

    rationale: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    thesis: str = ""

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "entry_timeframe": self.entry_timeframe,
            "htf_timeframe": self.htf_timeframe,
            "generated_at": self.generated_at,
            "direction": self.direction,
            "decision": self.decision,
            "confidence": round(self.confidence, 1),
            "composite_score": round(self.composite_score, 3),
            "current_price": round(self.current_price, 8),
            "entry": round(self.entry, 8) if self.entry else None,
            "entry_zone": [round(x, 8) for x in self.entry_zone],
            "stop_loss": round(self.stop_loss, 8) if self.stop_loss else None,
            "position_plan": self.position_plan,
            "scores": self.scores,
            "indicators": self.indicators,
            "levels": self.levels,
            "news": self.news,
            "rationale": self.rationale,
            "warnings": self.warnings,
            "thesis": self.thesis,
        }


def _latest(df: pd.DataFrame) -> pd.Series:
    return df.iloc[-1]


def _clamp(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def score_timeframe(df_ind: pd.DataFrame) -> dict:
    """Compute component scores (-1..1) and an indicator snapshot for one TF."""
    row = _latest(df_ind)
    price = float(row["close"])

    # --- Trend: EMA stacking + price location, scaled by ADX strength ---
    ema_f, ema_m, ema_s = row["ema_fast"], row["ema_mid"], row["ema_slow"]
    trend = 0.0
    if pd.notna(ema_s):
        if price > ema_f > ema_m > ema_s:
            trend = 1.0
        elif price < ema_f < ema_m < ema_s:
            trend = -1.0
        else:
            # partial credit from each relationship
            trend += 0.34 if price > ema_f else -0.34
            trend += 0.33 if ema_f > ema_m else -0.33
            trend += 0.33 if ema_m > ema_s else -0.33
    adx_val = float(row["adx"]) if pd.notna(row["adx"]) else 0.0
    adx_scale = min(1.0, max(0.3, adx_val / 25.0))  # weak trend (<25) dampened
    trend = _clamp(trend * adx_scale)

    # --- Momentum: RSI, MACD hist, Stochastic ---
    rsi_val = float(row["rsi"]) if pd.notna(row["rsi"]) else 50.0
    rsi_score = _clamp((rsi_val - 50.0) / 30.0)
    # fade extremes slightly (exhaustion risk)
    if rsi_val > 75:
        rsi_score *= 0.6
    elif rsi_val < 25:
        rsi_score *= 0.6

    macd_hist = float(row["macd_hist"]) if pd.notna(row["macd_hist"]) else 0.0
    macd_score = _clamp(macd_hist / (abs(price) * 0.004 + 1e-9))

    k = float(row["stoch_k"]) if pd.notna(row["stoch_k"]) else 50.0
    d = float(row["stoch_d"]) if pd.notna(row["stoch_d"]) else 50.0
    stoch_score = _clamp((k - 50.0) / 50.0)
    if k > 80:
        stoch_score *= 0.6
    elif k < 20:
        stoch_score *= 0.6
    stoch_score += 0.2 if k > d else -0.2
    stoch_score = _clamp(stoch_score)

    momentum = _clamp(0.45 * rsi_score + 0.35 * macd_score + 0.20 * stoch_score)

    # --- Volatility / mean-reversion via Bollinger %B (contrarian tilt) ---
    pct_b = float(row["bb_pct_b"]) if pd.notna(row["bb_pct_b"]) else 0.5
    # near lower band → bullish bounce bias; near upper → bearish
    volatility = _clamp((0.5 - pct_b) * 2.0)

    # --- Volume confirmation: rvol + OBV slope ---
    rvol = float(row["rvol"]) if pd.notna(row["rvol"]) else 1.0
    obv_slope = 0.0
    if len(df_ind) > 5 and pd.notna(df_ind["obv"].iloc[-5]):
        recent = df_ind["obv"].iloc[-5:]
        rng = recent.max() - recent.min()
        if rng > 0:
            obv_slope = _clamp((recent.iloc[-1] - recent.iloc[0]) / rng)
    # volume reinforces the prevailing momentum direction
    vol_dir = 1.0 if momentum >= 0 else -1.0
    volume = _clamp(vol_dir * min(1.0, (rvol - 1.0)) * 0.5 + obv_slope * 0.5)

    snapshot = {
        "price": round(price, 8),
        "ema_fast": round(float(ema_f), 8) if pd.notna(ema_f) else None,
        "ema_mid": round(float(ema_m), 8) if pd.notna(ema_m) else None,
        "ema_slow": round(float(ema_s), 8) if pd.notna(ema_s) else None,
        "rsi": round(rsi_val, 2),
        "macd_hist": round(macd_hist, 6),
        "stoch_k": round(k, 2),
        "stoch_d": round(d, 2),
        "adx": round(adx_val, 2),
        "bb_pct_b": round(pct_b, 3),
        "rvol": round(rvol, 2),
        "atr": round(float(row["atr"]), 8) if pd.notna(row["atr"]) else None,
    }

    return {
        "trend": round(trend, 3),
        "momentum": round(momentum, 3),
        "volatility": round(volatility, 3),
        "volume": round(volume, 3),
        "snapshot": snapshot,
    }


class SignalEngine:
    def __init__(self, config: dict):
        self.config = config
        cfg = config.get("signal", {})
        self.p = {**DEFAULTS, **{k: v for k, v in cfg.items() if k in DEFAULTS}}
        self.weights = {**DEFAULTS["weights"], **cfg.get("weights", {})}
        self.indicator_params = cfg.get("indicators", {})
        self.news_provider = NewsProvider(config)

    # ----------------------------------------------------------------- core
    def analyze(
        self,
        symbol: str,
        entry_df: pd.DataFrame,
        htf_df: pd.DataFrame | None = None,
        manual_headlines: list[str] | None = None,
        account_size: float | None = None,
        risk_per_trade_pct: float | None = None,
        use_news: bool = True,
    ) -> Signal:
        now = datetime.now(timezone.utc).isoformat()
        sig = Signal(
            symbol=symbol.upper(),
            entry_timeframe=self.p["entry_timeframe"],
            htf_timeframe=self.p["htf_timeframe"],
            generated_at=now,
        )

        if entry_df is None or len(entry_df) < 60:
            sig.decision = "AVOID"
            sig.warnings.append("Not enough data to analyze (need >= 60 candles).")
            return sig

        ent = ind.compute_all(entry_df, self.indicator_params)
        entry_scores = score_timeframe(ent)
        price = float(ent["close"].iloc[-1])
        atr_val = float(ent["atr"].iloc[-1])
        sig.current_price = price

        # Higher-timeframe trend gate
        htf_scores = None
        if htf_df is not None and len(htf_df) >= 60:
            htf_ind = ind.compute_all(htf_df, self.indicator_params)
            htf_scores = score_timeframe(htf_ind)
        sig.indicators = {
            self.p["entry_timeframe"]: entry_scores["snapshot"],
        }
        if htf_scores:
            sig.indicators[self.p["htf_timeframe"]] = htf_scores["snapshot"]

        # Composite on entry TF
        w = self.weights
        composite = (
            w["trend"] * entry_scores["trend"]
            + w["momentum"] * entry_scores["momentum"]
            + w["volatility"] * entry_scores["volatility"]
            + w["volume"] * entry_scores["volume"]
        )
        composite = _clamp(composite)
        sig.composite_score = composite
        sig.scores = {
            "entry_tf": {k: entry_scores[k] for k in ("trend", "momentum", "volatility", "volume")},
            "composite": round(composite, 3),
        }
        if htf_scores:
            sig.scores["htf_trend"] = htf_scores["trend"]

        # Direction
        threshold = self.p["entry_threshold"]
        if composite >= threshold:
            direction = "LONG"
        elif composite <= -threshold:
            direction = "SHORT"
        else:
            direction = "NEUTRAL"
        sig.direction = direction

        # ---- Confidence ----
        confidence = abs(composite) * 70.0  # base 0..70
        htf_aligned = True
        if htf_scores is not None and direction != "NEUTRAL":
            htf_trend = htf_scores["trend"]
            if direction == "LONG" and htf_trend > 0.2:
                confidence += 18
            elif direction == "SHORT" and htf_trend < -0.2:
                confidence += 18
            elif (direction == "LONG" and htf_trend < -0.2) or (
                direction == "SHORT" and htf_trend > 0.2
            ):
                htf_aligned = False
                confidence -= 25
                sig.warnings.append(
                    f"Higher timeframe ({self.p['htf_timeframe']}) trend opposes "
                    f"the {direction} signal — counter-trend, lower probability."
                )
        # volume confirmation bonus
        if entry_scores["snapshot"]["rvol"] >= 1.3:
            confidence += 6
        confidence = max(0.0, min(100.0, confidence))

        # ---- Levels ----
        all_levels = lv.find_levels(ent, price, atr_val)
        sig.levels = [
            l.to_dict()
            for l in sorted(all_levels, key=lambda x: abs(x.price - price))[:8]
        ]

        # ---- News overlay ----
        risk_multiplier = 1.0
        if use_news:
            news = self.news_provider.assess(symbol, manual_headlines)
            sig.news = news.to_dict()
            risk_multiplier, news_notes = self._apply_news_gate(
                news, direction, sig
            )
        else:
            sig.news = {"summary": "News overlay skipped."}

        # ---- Decision & plan ----
        if direction == "NEUTRAL":
            sig.decision = "WAIT"
            sig.confidence = confidence
            sig.rationale = self._build_rationale(
                direction, entry_scores, htf_scores, composite, None
            )
            sig.rationale.append(
                "No directional edge: indicators are mixed/neutral. Stay flat."
            )
            return sig

        if not htf_aligned and confidence < self.p["min_confidence"] + 10:
            sig.decision = "AVOID"
        elif confidence < self.p["min_confidence"]:
            sig.decision = "WAIT"
        else:
            sig.decision = "ENTER"

        sig.confidence = confidence

        # Build entry / stop / targets
        entry, entry_zone, stop = self._entry_and_stop(
            direction, price, atr_val, all_levels
        )
        sig.entry = entry
        sig.entry_zone = entry_zone
        sig.stop_loss = stop

        tps = self._take_profits(direction, entry, stop, all_levels)

        acct = account_size if account_size is not None else self.p["account_size"]
        risk_pct = (
            risk_per_trade_pct
            if risk_per_trade_pct is not None
            else self.p["risk_per_trade_pct"]
        )
        win_rate = assumed_win_rate_from_confidence(confidence)
        plan = build_position_plan(
            direction=direction,
            entry=entry,
            stop_loss=stop,
            take_profits=tps,
            account_size=acct,
            risk_per_trade_pct=risk_pct,
            confidence=confidence,
            assumed_win_rate=win_rate,
            max_leverage_cap=self.p["max_leverage_cap"],
            risk_multiplier=risk_multiplier,
        )
        sig.position_plan = plan.to_dict()
        sig.position_plan["assumed_win_rate"] = round(win_rate, 3)
        sig.position_plan["risk_multiplier"] = round(risk_multiplier, 2)

        if plan.expected_value_r <= 0 and sig.decision == "ENTER":
            sig.decision = "WAIT"
            sig.warnings.append(
                "Expected value is non-positive at the assumed win rate — "
                "reward/risk does not justify the trade."
            )

        sig.rationale = self._build_rationale(
            direction, entry_scores, htf_scores, composite, plan
        )
        return sig

    # ------------------------------------------------------------- helpers
    def _apply_news_gate(
        self, news: NewsAssessment, direction: str, sig: Signal
    ) -> tuple[float, list[str]]:
        notes: list[str] = []
        mult = 1.0
        if news.high_impact_event:
            mult *= 0.5
            sig.warnings.append(
                "High-impact macro/event detected in news — reduce size or wait "
                "until after the event (stop-hunt / volatility risk)."
            )
        if news.confidence >= 0.3 and direction != "NEUTRAL":
            dir_sign = 1.0 if direction == "LONG" else -1.0
            agree = dir_sign * news.sentiment_score
            if agree > 0.3:
                mult *= 1.15
                notes.append("News sentiment supports the trade direction.")
            elif agree < -0.3:
                mult *= 0.6
                sig.warnings.append(
                    "News sentiment opposes the trade direction — size down."
                )
        return mult, notes

    def _entry_and_stop(
        self, direction: str, price: float, atr_val: float, levels: list[lv.Level]
    ):
        atr_stop_dist = self.p["atr_stop_mult"] * atr_val
        min_dist = self.p["min_stop_atr"] * atr_val
        max_dist = self.p["max_stop_atr"] * atr_val

        if direction == "LONG":
            support = lv.nearest_support(levels, price)
            struct_stop = (support.price - 0.3 * atr_val) if support else None
            atr_stop = price - atr_stop_dist
            stop = min(struct_stop, atr_stop) if struct_stop else atr_stop
            dist = price - stop
            dist = max(min_dist, min(max_dist, dist))
            stop = price - dist
            # entry: market now, with a small pullback zone toward stop
            entry = price
            entry_zone = [round(price - 0.25 * dist, 8), round(price, 8)]
        else:  # SHORT
            resistance = lv.nearest_resistance(levels, price)
            struct_stop = (resistance.price + 0.3 * atr_val) if resistance else None
            atr_stop = price + atr_stop_dist
            stop = max(struct_stop, atr_stop) if struct_stop else atr_stop
            dist = stop - price
            dist = max(min_dist, min(max_dist, dist))
            stop = price + dist
            entry = price
            entry_zone = [round(price, 8), round(price + 0.25 * dist, 8)]

        return round(entry, 8), entry_zone, round(stop, 8)

    def _take_profits(
        self, direction: str, entry: float, stop: float, levels: list[lv.Level]
    ) -> list[TakeProfit]:
        risk = abs(entry - stop)
        allocs = self.p["tp_allocations"]
        tps: list[TakeProfit] = []

        if direction == "LONG":
            candidates = [l for l in lv.resistances_above(levels, entry)]
            level_prices = [l.price for l in candidates]
        else:
            candidates = [l for l in lv.supports_below(levels, entry)]
            level_prices = [l.price for l in candidates]

        # keep levels that give at least ~0.8R, ordered by distance
        chosen: list[float] = []
        for lp in level_prices:
            r = abs(lp - entry) / risk if risk > 0 else 0
            if r >= 0.8:
                chosen.append(lp)
            if len(chosen) >= len(allocs):
                break

        # fall back to fixed R multiples for any missing targets
        fallback_r = [1.5, 2.5, 4.0]
        while len(chosen) < len(allocs):
            r = fallback_r[len(chosen)] if len(chosen) < len(fallback_r) else (len(chosen) + 1) * 1.5
            tp_price = entry + r * risk if direction == "LONG" else entry - r * risk
            chosen.append(tp_price)

        labels = ["TP1 (de-risk)", "TP2", "TP3 (runner)"]
        for i, lp in enumerate(chosen[: len(allocs)]):
            r = abs(lp - entry) / risk if risk > 0 else 0
            tps.append(
                TakeProfit(
                    price=round(lp, 8),
                    r_multiple=r,
                    allocation_pct=allocs[i],
                    label=labels[i] if i < len(labels) else f"TP{i+1}",
                )
            )
        # ensure increasing R
        tps.sort(key=lambda t: t.r_multiple)
        return tps

    def _build_rationale(
        self, direction, entry_scores, htf_scores, composite, plan
    ) -> list[str]:
        s = entry_scores
        r: list[str] = []
        r.append(
            f"Entry-TF confluence: trend {s['trend']:+.2f}, momentum "
            f"{s['momentum']:+.2f}, volatility {s['volatility']:+.2f}, volume "
            f"{s['volume']:+.2f} → composite {composite:+.2f}."
        )
        snap = s["snapshot"]
        r.append(
            f"RSI {snap['rsi']}, MACD hist {snap['macd_hist']:+.4f}, "
            f"Stoch {snap['stoch_k']}/{snap['stoch_d']}, ADX {snap['adx']}, "
            f"%B {snap['bb_pct_b']}, rVol {snap['rvol']}x."
        )
        if htf_scores is not None:
            r.append(
                f"Higher timeframe trend score {htf_scores['trend']:+.2f} "
                f"({'aligned' if (htf_scores['trend'] > 0) == (direction == 'LONG') else 'not aligned'})."
            )
        if plan is not None:
            r.append(
                f"Plan: {direction} risking {plan.risk_per_trade_pct:.2f}% "
                f"(~{plan.risk_amount:.2f}) with stop {plan.stop_distance_pct:.2f}% away; "
                f"blended R:R {plan.blended_rr:.2f}, EV {plan.expected_value_r:+.2f}R."
            )
        return r

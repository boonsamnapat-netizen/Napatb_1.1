"""
Key price levels & liquidity zones.

The crowd places stops just beyond obvious swing highs/lows and round numbers.
Those clusters are liquidity — price is frequently drawn to them and reverses
there. We surface these so the signal engine can: (a) avoid entering right into
resistance, (b) place stops *beyond* obvious levels rather than on them, and
(c) target the next liquidity pool for take-profits.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class Level:
    price: float
    kind: str          # "support" / "resistance"
    source: str        # "swing" / "round" / "ema" / "bb"
    strength: int = 1  # how many touches / how significant

    def to_dict(self) -> dict:
        return {
            "price": round(self.price, 8),
            "kind": self.kind,
            "source": self.source,
            "strength": self.strength,
        }


def swing_points(df: pd.DataFrame, left: int = 3, right: int = 3) -> tuple[list, list]:
    """Fractal swing highs / lows (a high with `left`/`right` lower bars around it)."""
    highs, lows = [], []
    h, l = df["high"].values, df["low"].values
    n = len(df)
    for i in range(left, n - right):
        window_h = h[i - left : i + right + 1]
        window_l = l[i - left : i + right + 1]
        if h[i] == window_h.max() and (window_h.argmax() == left):
            highs.append((df.index[i], float(h[i])))
        if l[i] == window_l.min() and (window_l.argmin() == left):
            lows.append((df.index[i], float(l[i])))
    return highs, lows


def round_number_levels(price: float, count: int = 3) -> list[float]:
    """Psychologically important round numbers near `price`."""
    if price <= 0:
        return []
    magnitude = 10 ** (np.floor(np.log10(price)))
    step = magnitude / 2.0  # halves & wholes of the leading magnitude
    base = np.floor(price / step) * step
    levels = []
    for k in range(-count, count + 2):
        lvl = base + k * step
        if lvl > 0:
            levels.append(round(float(lvl), 8))
    return sorted(set(levels))


def _cluster(values: list[float], tol: float) -> list[tuple[float, int]]:
    """Group nearby levels; return (mean_price, count)."""
    if not values:
        return []
    values = sorted(values)
    clusters: list[list[float]] = [[values[0]]]
    for v in values[1:]:
        if abs(v - clusters[-1][-1]) <= tol:
            clusters[-1].append(v)
        else:
            clusters.append([v])
    return [(float(np.mean(c)), len(c)) for c in clusters]


def find_levels(df: pd.DataFrame, current_price: float, atr_value: float) -> list[Level]:
    """Build a consolidated list of support/resistance levels around price."""
    tol = max(atr_value * 0.5, current_price * 0.001)
    highs, lows = swing_points(df)

    levels: list[Level] = []

    for price, strength in _cluster([p for _, p in highs], tol):
        kind = "resistance" if price >= current_price else "support"
        levels.append(Level(price, kind, "swing", strength))
    for price, strength in _cluster([p for _, p in lows], tol):
        kind = "support" if price <= current_price else "resistance"
        levels.append(Level(price, kind, "swing", strength))

    for rn in round_number_levels(current_price):
        if abs(rn - current_price) > tol:  # skip the one we're sitting on
            kind = "resistance" if rn > current_price else "support"
            levels.append(Level(rn, kind, "round", 1))

    levels.sort(key=lambda x: x.price)
    return levels


def nearest_support(levels: list[Level], price: float) -> Level | None:
    below = [l for l in levels if l.price < price]
    return max(below, key=lambda x: x.price) if below else None


def nearest_resistance(levels: list[Level], price: float) -> Level | None:
    above = [l for l in levels if l.price > price]
    return min(above, key=lambda x: x.price) if above else None


def resistances_above(levels: list[Level], price: float) -> list[Level]:
    return sorted([l for l in levels if l.price > price], key=lambda x: x.price)


def supports_below(levels: list[Level], price: float) -> list[Level]:
    return sorted([l for l in levels if l.price < price], key=lambda x: x.price, reverse=True)

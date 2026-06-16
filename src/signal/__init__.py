"""
Live crypto signal system.

Combines mainstream technical indicators (the picture the crowd sees) with
multi-timeframe confluence, key-level / liquidity awareness, news sentiment and
strict money-management to produce actionable entry / exit / risk plans.

Public surface:
    from src.signal import SignalEngine, Signal
"""

from src.signal.signal_engine import SignalEngine, Signal  # noqa: F401

__all__ = ["SignalEngine", "Signal"]

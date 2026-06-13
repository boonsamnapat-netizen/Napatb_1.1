"""รัน freqtrade backtest แบบ offline (ใช้เฉพาะ environment ที่ต่อ exchange ไม่ได้)

ปกติ freqtrade จะดึงรายชื่อ market จาก exchange ก่อนเสมอ แม้ตอน backtest
สคริปต์นี้ patch ขั้นตอนนั้นให้ใช้ market แบบ static สำหรับเหรียญที่เราจะทดสอบ
เพื่อให้รัน backtest บนข้อมูลที่เตรียมไว้ในเครื่องได้โดยไม่ต้องต่อเน็ต

⚠️ บนเครื่องจริงของคุณ ไม่ต้องใช้ไฟล์นี้ — ใช้คำสั่งปกติได้เลย:
    freqtrade backtesting --config user_data/config.json --strategy SampleEmaRsiStrategy
"""
import sys

PAIRS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT"]


def _static_market(symbol: str) -> dict:
    base, quote = symbol.split("/")
    return {
        "id": base + quote,
        "lowercaseId": (base + quote).lower(),
        "symbol": symbol,
        "base": base,
        "quote": quote,
        "baseId": base,
        "quoteId": quote,
        "active": True,
        "type": "spot",
        "spot": True,
        "margin": False,
        "swap": False,
        "future": False,
        "option": False,
        "contract": False,
        "settle": None,
        "settleId": None,
        "contractSize": None,
        "linear": None,
        "inverse": None,
        "taker": 0.001,
        "maker": 0.001,
        "percentage": True,
        "tierBased": False,
        "feeSide": "get",
        # ค่า precision ต้องเป็น "tick size" (binance ใช้ TICK_SIZE mode)
        # ถ้าใส่เป็นจำนวนเต็มเช่น 8 จะถูกตีความว่า tick=8 -> จำนวนเหรียญปัดเป็น 0
        "precision": {"amount": 1e-05, "price": 0.01, "base": 1e-08, "quote": 1e-08},
        "limits": {
            "amount": {"min": 1e-05, "max": None},
            "price": {"min": None, "max": None},
            "cost": {"min": 5.0, "max": None},
            "leverage": {"min": None, "max": None},
        },
        "info": {},
    }


def _patch():
    from freqtrade.exchange.exchange import Exchange

    static_markets = {s: _static_market(s) for s in PAIRS}

    def _load_async_markets(self, reload: bool = False):
        # ป้อน market แบบ static เข้า ccxt แทนการเรียก network
        self._api_async.set_markets(static_markets)
        try:
            self._api.set_markets(static_markets)
        except Exception:
            pass
        return None

    Exchange._load_async_markets = _load_async_markets


if __name__ == "__main__":
    _patch()
    from freqtrade.main import main

    sys.argv = [
        "freqtrade",
        "backtesting",
        "--userdir", "freqtrade-bot/user_data",
        "--config", "freqtrade-bot/user_data/config.json",
        "--strategy", "SampleEmaRsiStrategy",
        "--timerange", "20250101-20250601",
        "--timeframe", "1h",
    ]
    main()

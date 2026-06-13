"""สร้างข้อมูลราคา OHLCV จำลอง (random walk) สำหรับทดสอบ backtest แบบ offline
รันบน environment ที่เข้า exchange ไม่ได้ — ใช้แทนคำสั่ง `freqtrade download-data` ชั่วคราว
บนเครื่องจริงให้ใช้ download-data เพื่อดึงข้อมูลจริงแทน
"""
import numpy as np
import pandas as pd
from pathlib import Path

OUT = Path(__file__).parent / "user_data" / "data" / "binance"
OUT.mkdir(parents=True, exist_ok=True)

PAIRS = {
    "BTC_USDT": 95000.0,
    "ETH_USDT": 3500.0,
    "SOL_USDT": 180.0,
    "BNB_USDT": 650.0,
}

# ช่วงเวลา: 1h แท่ง ตั้งแต่ 2025-01-01 ถึง 2025-06-01
idx = pd.date_range("2025-01-01", "2025-06-01", freq="1h", tz="UTC")
n = len(idx)
rng = np.random.default_rng(42)

for pair, start_price in PAIRS.items():
    # random walk + เทรนด์อ่อนๆ + รอบ (cycle) เพื่อให้มีทั้งขาขึ้น/ขาลง ให้สัญญาณยิงบ้าง
    rets = rng.normal(0.0, 0.012, n)
    trend = np.linspace(0, 0.4, n)
    cycle = 0.15 * np.sin(np.linspace(0, 12 * np.pi, n))
    log_price = np.log(start_price) + np.cumsum(rets) * 0.3 + trend + cycle
    close = np.exp(log_price)

    open_ = np.concatenate([[close[0]], close[:-1]])
    high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.004, n)))
    low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.004, n)))
    volume = rng.uniform(500, 5000, n)

    df = pd.DataFrame(
        {
            "date": idx,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        }
    )
    fpath = OUT / f"{pair}-1h.feather"
    df.reset_index(drop=True).to_feather(fpath)
    print(f"  wrote {fpath.name}  ({len(df)} candles, last close={close[-1]:.2f})")

print("done.")

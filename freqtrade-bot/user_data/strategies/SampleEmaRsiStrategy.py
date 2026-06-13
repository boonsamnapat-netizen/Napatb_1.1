# pragma pylint: disable=missing-docstring, invalid-name
"""
SampleEmaRsiStrategy — กลยุทธ์ตัวอย่างสำหรับมือใหม่
====================================================

แนวคิด (เข้าใจง่าย):
  - ใช้เส้นค่าเฉลี่ย EMA สองเส้น (เร็ว/ช้า) ดูเทรนด์
  - ใช้ RSI ดูว่าราคา "ถูก" (oversold) หรือ "แพง" (overbought)

เงื่อนไขเข้าซื้อ (long):
  - EMA เส้นเร็ว ตัดขึ้นเหนือ EMA เส้นช้า  (เทรนด์เริ่มเป็นขาขึ้น)
  - RSI ยังไม่สูงเกินไป (< 70)  เพื่อเลี่ยงไล่ราคาตอนแพง
  - มี volume จริง (กันเหรียญที่ไม่มีสภาพคล่อง)

เงื่อนไขออก (sell):
  - EMA เส้นเร็ว ตัดลงใต้ EMA เส้นช้า  (เทรนด์เริ่มกลับเป็นขาลง)
  - หรือ RSI สูงเกิน 70 (ราคาแพงเกิน — ขายทำกำไร)

นอกจากนี้ยังมี ROI table + stoploss + trailing stop เป็นตาข่ายนิรภัย

หมายเหตุ: นี่เป็นตัวอย่างเพื่อ "เรียนรู้และ backtest" เท่านั้น
ห้ามนำไปเทรดเงินจริงโดยไม่ทดสอบ (backtest + dry-run) ให้ดีก่อน
"""

from datetime import datetime
from typing import Optional

import talib.abstract as ta
from pandas import DataFrame

from freqtrade.strategy import IStrategy, IntParameter, DecimalParameter


class SampleEmaRsiStrategy(IStrategy):
    # เวอร์ชันของ interface ที่ใช้ (อย่าแก้ ถ้าไม่รู้ว่าทำอะไร)
    INTERFACE_VERSION = 3

    # ----------------------------------------------------------------
    # ตั้งค่าหลักของกลยุทธ์
    # ----------------------------------------------------------------

    # timeframe = กรอบเวลาแท่งเทียนที่ใช้ตัดสินใจ ("5m", "15m", "1h", "4h", "1d")
    timeframe = "1h"

    # can_short = อนุญาตให้ short ไหม (False = เล่นฝั่งขึ้นอย่างเดียว เหมาะกับมือใหม่/spot)
    can_short = False

    # ROI table: เป้ากำไรที่จะออกอัตโนมัติตามเวลาที่ถือ (หน่วยซ้าย = นาที, ขวา = สัดส่วนกำไร)
    #   0 นาที  -> +4% ออกเลย
    #   30 นาที -> +2% ก็พอ
    #   60 นาที -> +1% ก็พอ
    #   120 นาที -> เสมอตัวก็ออก
    minimal_roi = {
        "0": 0.04,
        "30": 0.02,
        "60": 0.01,
        "120": 0,
    }

    # stoploss = ตัดขาดทุนสูงสุดที่ยอมรับได้ (-10%)
    stoploss = -0.10

    # trailing stop = เลื่อน stoploss ตามกำไรเพื่อล็อกกำไร
    trailing_stop = True
    trailing_stop_positive = 0.02          # เริ่ม trail เมื่อกำไรถึงระดับนี้
    trailing_stop_positive_offset = 0.03   # ระยะ offset
    trailing_only_offset_is_reached = True

    # ใช้ราคา exit ตอนแท่งปิดเท่านั้น (ปลอดภัยและ backtest ตรงกับจริงมากขึ้น)
    process_only_new_candles = True
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    # จำนวนแท่งย้อนหลังที่ต้องมีก่อนเริ่มเทรด (ให้ indicator คำนวณครบ)
    startup_candle_count: int = 50

    # ----------------------------------------------------------------
    # พารามิเตอร์ที่ปรับ/optimize ได้ด้วย hyperopt
    # (ลองสั่ง: freqtrade hyperopt ... เพื่อหาค่าที่ดีที่สุดอัตโนมัติ)
    # ----------------------------------------------------------------
    buy_rsi = IntParameter(20, 40, default=30, space="buy", optimize=True)
    sell_rsi = IntParameter(60, 85, default=70, space="sell", optimize=True)
    ema_fast = IntParameter(5, 20, default=9, space="buy", optimize=True)
    ema_slow = IntParameter(20, 60, default=21, space="buy", optimize=True)

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """คำนวณ indicator ทั้งหมดที่กลยุทธ์ใช้ ลงในตารางข้อมูลราคา"""
        # RSI
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)

        # EMA เร็ว/ช้า
        dataframe["ema_fast"] = ta.EMA(dataframe, timeperiod=int(self.ema_fast.value))
        dataframe["ema_slow"] = ta.EMA(dataframe, timeperiod=int(self.ema_slow.value))

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """กำหนดเงื่อนไข 'เข้าซื้อ' -> ใส่ค่า 1 ในคอลัมน์ enter_long"""
        dataframe.loc[
            (
                # EMA เร็ว ตัดขึ้นเหนือ EMA ช้า (แท่งก่อนหน้าอยู่ใต้, แท่งนี้อยู่เหนือ)
                (dataframe["ema_fast"] > dataframe["ema_slow"])
                & (dataframe["ema_fast"].shift(1) <= dataframe["ema_slow"].shift(1))
                # RSI ยังไม่สูงเกินไป
                & (dataframe["rsi"] < self.sell_rsi.value)
                # มี volume จริง
                & (dataframe["volume"] > 0)
            ),
            "enter_long",
        ] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """กำหนดเงื่อนไข 'ออก' -> ใส่ค่า 1 ในคอลัมน์ exit_long"""
        dataframe.loc[
            (
                (
                    # EMA เร็ว ตัดลงใต้ EMA ช้า
                    (dataframe["ema_fast"] < dataframe["ema_slow"])
                    & (dataframe["ema_fast"].shift(1) >= dataframe["ema_slow"].shift(1))
                )
                # หรือ RSI แพงเกินไป
                | (dataframe["rsi"] > self.sell_rsi.value)
            )
            & (dataframe["volume"] > 0),
            "exit_long",
        ] = 1

        return dataframe

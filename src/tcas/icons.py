"""สร้างไอคอนแอปเป็น PNG โดยไม่พึ่งไลบรารีภายนอก.

Pillow ไม่ได้ติดตั้งในสภาพแวดล้อมนี้ และไอคอนที่ต้องการเป็นรูปทรงเรียบง่าย
(วงกลมบนพื้นสี่เหลี่ยม) จึงวาดเองด้วย zlib + struct ซึ่งมีอยู่ใน stdlib

ลาย: วงกลม OMR ที่กำลังถูกฝน — วงแหวนสีเหลืองอำพันบนพื้นกรมท่า
ซึ่งเป็นลายเดียวกับที่ใช้ในหน้าเว็บ อ่านออกตั้งแต่ 512px ลงไปถึง 48px

วาดที่ความละเอียด 4 เท่าแล้วย่อลง เพื่อให้ขอบวงกลมเรียบ (supersampling)
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path
from typing import Tuple

# สีเดียวกับ token ในหน้าเว็บ
NAVY = (0x2A, 0x1D, 0x2E)   # --ink: ม่วงเข้ม (เดิมเป็นกรมท่า)
MARIGOLD = (0xF0, 0xAB, 0x2C)

SS = 4  # supersample factor


def _blend(bg: Tuple[int, int, int], fg: Tuple[int, int, int], a: float):
    return tuple(int(round(b + (f - b) * a)) for b, f in zip(bg, fg))


def _render(size: int) -> bytes:
    """วาดไอคอนขนาด size×size คืน raw RGB bytes."""
    big = size * SS
    cx = cy = big / 2.0

    # รัศมีวงแหวน: นอก 33% ของด้าน, หนา 11%
    r_out = big * 0.33
    r_in = big * 0.22
    # จุดตรงกลาง (แสดงว่ากำลังฝน)
    r_dot = big * 0.115
    # มุมโค้งของพื้นหลัง
    corner = big * 0.22

    # accumulate ที่ความละเอียดสูง แล้วเฉลี่ยลงมา
    rows = []
    for y in range(size):
        row = bytearray()
        for x in range(size):
            rs = gs = bs = 0
            for sy in range(SS):
                py = y * SS + sy + 0.5
                for sx in range(SS):
                    px = x * SS + sx + 0.5

                    # นอกมุมโค้ง = โปร่ง -> ใช้สีหมึกเข้มกว่าเป็นขอบ
                    inside_card = True
                    for ox, oy in ((corner, corner), (big - corner, corner),
                                   (corner, big - corner), (big - corner, big - corner)):
                        if ((px < corner and py < corner) or
                            (px > big - corner and py < corner) or
                            (px < corner and py > big - corner) or
                            (px > big - corner and py > big - corner)):
                            if (px - ox) ** 2 + (py - oy) ** 2 > corner ** 2:
                                inside_card = False
                            break

                    if not inside_card:
                        c = NAVY  # นอกมุมโค้งก็ยังเป็นสีหมึก (ไอคอนทึบ ระบบจะครอบเอง)
                    else:
                        d = ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5
                        if d <= r_dot:
                            c = MARIGOLD
                        elif r_in <= d <= r_out:
                            c = MARIGOLD
                        else:
                            c = NAVY
                    rs += c[0]; gs += c[1]; bs += c[2]
            n = SS * SS
            row += bytes((rs // n, gs // n, bs // n))
        rows.append(bytes(row))
    return b"".join(b"\x00" + r for r in rows)


def _png(raw: bytes, size: int) -> bytes:
    """ประกอบ raw scanlines เป็นไฟล์ PNG (RGB 8-bit, ไม่มี alpha)."""
    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)  # bit depth 8, colour type 2 (RGB)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def write_icon(path: Path, size: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_png(_render(size), size))
    return path


def write_all(outdir: Path, force: bool = False) -> dict:
    """สร้างไอคอนทุกขนาดที่ PWA และ iOS ต้องการ.

    การวาดขนาด 512 ใช้เวลาหลายวินาที และไอคอนไม่เปลี่ยนถ้าโค้ดไม่เปลี่ยน
    จึงข้ามไฟล์ที่มีอยู่แล้ว — สั่งวาดใหม่ด้วย force=True
    """
    sizes = {"icon-192.png": 192, "icon-512.png": 512, "icon-180.png": 180}
    written = {}
    for name, size in sizes.items():
        path = outdir / name
        if force or not path.exists():
            write_icon(path, size)
        written[name] = path
    return written

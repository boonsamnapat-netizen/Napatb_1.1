#!/usr/bin/env python3
"""สร้างไฟล์ Artifact (tools/tdee/index.html) จากซอร์สของเว็บแอปใน docs/tdee/

เว็บแอปคือแหล่งความจริงเดียว — สคริปต์นี้แค่รวม CSS/JS เข้ามาไว้ในไฟล์เดียว
แล้วตัดส่วนที่เป็นของ PWA (manifest / service worker / ปุ่มติดตั้ง) ออก
เพราะหน้า Artifact เสิร์ฟเป็นไฟล์เดียวและ host เป็นคนใส่ <head> ให้เอง

ใช้:  python3 tools/tdee/build_artifact.py
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "docs" / "tdee"
OUT = ROOT / "tools" / "tdee" / "index.html"

FONTS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
    '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
    "family=Anuphan:wght@400;500;600;700&family=IBM+Plex+Sans+Thai:wght@400;500;600"
    '&family=IBM+Plex+Mono:wght@500;600&display=swap">'
)


def main() -> None:
    html = (SRC / "index.html").read_text(encoding="utf-8")
    body = html.split("<body>", 1)[1].split('<div class="toast"', 1)[0].strip()

    fragment = "\n".join([
        "<title>งบแคลอรี่รายวัน</title>",
        FONTS,
        "<style>",
        (SRC / "app.css").read_text(encoding="utf-8").strip(),
        "</style>",
        "",
        body,
        "",
        "<script>",
        (SRC / "app.js").read_text(encoding="utf-8").strip(),
        "</script>",
        "",
    ])
    OUT.write_text(fragment, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} ({len(fragment):,} chars)")


if __name__ == "__main__":
    main()

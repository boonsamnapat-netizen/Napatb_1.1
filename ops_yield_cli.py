#!/usr/bin/env python3
"""Batch-convert a day's LINE production reports into the Excel yield workbook.

Usage:
    python ops_yield_cli.py --in messages.txt --out yield.xlsx
    python ops_yield_cli.py --in messages.txt --out yield.xlsx --no-append
    python ops_yield_cli.py --demo --out yield.xlsx

``messages.txt`` is the raw text dump of the day's LINE messages (one report
per block, separated by a blank line or a new ``@`` mention). The end-of-day
collector writes this file; this CLI parses it and updates the workbook.
"""

from __future__ import annotations

import argparse
import sys

from ops_yield import parse_messages, write_workbook

DEMO = """\
@NapatB. Manual # (1) Underfill  Runได้ปกติค่ะ Jun 17 2026  Day  ✅️Run  95 Unit  ✅ไม่มี Fail L1  ✅ไม่มี Fail L2  ✅ไม่มี splash

@NapatB. Manual # (2) Underfill  Runปกติ Jun 17 2026  Day  ✅️Run  120 Unit  ❌ 3 Fail L1  ✅ไม่มี Fail L2  ❌ 2 splash

@NapatB. Auto # (3) Crack  มีปัญหานิดหน่อย Jun 17 2026  Night  ✅️Run  80 Unit  ✅ไม่มี Fail L1  ❌ 5 Fail L2  ✅ไม่มี splash

@NapatB. Manual # (1) Underfill  Runได้ปกติค่ะ Jun 18 2026  Day  ✅️Run  100 Unit  ❌ 1 Fail L1  ✅ไม่มี Fail L2  ✅ไม่มี splash

@NapatB. Manual # (2) Underfill  ปกติ Jun 18 2026  Night  ✅️Run  110 Unit  ✅ไม่มี Fail L1  ✅ไม่มี Fail L2  ❌ 4 splash
"""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--in", dest="infile", help="text file of LINE messages")
    ap.add_argument("--line-export", dest="export",
                    help="raw LINE 'Save chat history' .txt export to learn from")
    ap.add_argument("--year", type=int, help="with --line-export: keep only this year")
    ap.add_argument("--url", help="URL returning the day's messages (e.g. a "
                    "published Google Sheet CSV / Apps Script endpoint)")
    ap.add_argument("--out", default="yield.xlsx", help="workbook path")
    ap.add_argument("--demo", action="store_true", help="use built-in sample data")
    ap.add_argument("--no-append", action="store_true",
                    help="overwrite instead of appending to existing workbook")
    args = ap.parse_args(argv)

    if args.export:
        from ops_yield.lineexport import parse_export
        with open(args.export, encoding="utf-8") as fh:
            records = parse_export(fh.read())
        if args.year:
            records = [r for r in records
                       if r.work_date and r.work_date.year == args.year]
        if not records:
            print("ไม่พบรายงานใน export", file=sys.stderr)
            return 1
        flagged = [r for r in records if r.warnings]
        summary = write_workbook(records, args.out, append=not args.no_append)
        print(f"อ่าน export ได้ {len(records)} รายงาน | เครื่อง: {summary['machines']}")
        print(f"เขียนลง {summary['path']} (รวม {summary['records_total']} แถว) "
              f"| ต้อง review {len(flagged)} รายงาน")
        return 0

    if args.demo:
        text = DEMO
    elif args.infile:
        with open(args.infile, encoding="utf-8") as fh:
            text = fh.read()
    elif args.url:
        from urllib.request import urlopen
        with urlopen(args.url, timeout=30) as resp:
            text = resp.read().decode("utf-8")
    else:
        ap.error("ต้องระบุ --in <file>, --url <url> หรือ --demo")
        return 2

    records = parse_messages(text)
    if not records:
        print("ไม่พบข้อความที่ parse ได้", file=sys.stderr)
        return 1

    flagged = [r for r in records if r.warnings]
    summary = write_workbook(records, args.out, append=not args.no_append)

    print(f"parse ได้ {len(records)} รายการ | เครื่อง: {summary['machines']}")
    print(f"เขียนลง {summary['path']} (รวมทั้งหมด {summary['records_total']} แถว)")
    for r in flagged:
        print(f"  ⚠️  เครื่อง {r.machine} {r.work_date}: {'; '.join(r.warnings)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

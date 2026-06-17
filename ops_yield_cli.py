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
    ap.add_argument("--gsheet-url", help="also publish to this Google Sheet URL")
    ap.add_argument("--gsheet-creds", default="service_account.json",
                    help="service-account JSON for --gsheet-url")
    ap.add_argument("--gsheet-source", action="store_true",
                    help="read the day's messages from the 'Messages' tab of "
                    "--gsheet-url (fed by collector.gs) instead of a file/url")
    args = ap.parse_args(argv)

    # --- connect to Google Sheets (master) first, if requested -------------
    sh = None
    if args.gsheet_url:
        from ops_yield import to_gsheet
        sh = to_gsheet.connect(args.gsheet_creds, args.gsheet_url)

    # --- obtain records ----------------------------------------------------
    if args.export:
        from ops_yield.lineexport import parse_export
        with open(args.export, encoding="utf-8") as fh:
            records = parse_export(fh.read())
        if args.year:
            records = [r for r in records
                       if r.work_date and r.work_date.year == args.year]
    else:
        if args.gsheet_source:
            if sh is None:
                ap.error("--gsheet-source ต้องใช้คู่กับ --gsheet-url")
                return 2
            from ops_yield import to_gsheet
            text = to_gsheet.read_messages(sh)
        elif args.demo:
            text = DEMO
        elif args.infile:
            with open(args.infile, encoding="utf-8") as fh:
                text = fh.read()
        elif args.url:
            from urllib.request import urlopen
            with urlopen(args.url, timeout=30) as resp:
                text = resp.read().decode("utf-8")
        else:
            ap.error("ต้องระบุ --in <file>, --url <url>, --line-export, "
                     "--gsheet-source หรือ --demo")
            return 2
        records = parse_messages(text)

    if not records:
        print("ไม่พบรายงานที่ parse ได้", file=sys.stderr)
        return 1

    # --- pull back Action/Status from Google Sheets (master) ---------------
    prior = {}
    if sh is not None:
        from ops_yield import to_gsheet
        prior = to_gsheet.read_actions(sh)

    # --- build workbook ----------------------------------------------------
    flagged = [r for r in records if r.warnings]
    summary = write_workbook(records, args.out, append=not args.no_append,
                             prior_actions=prior)
    print(f"parse ได้ {len(records)} รายงาน | เครื่อง: {summary['machines']}")
    print(f"เขียนลง {summary['path']} (รวม {summary['records_total']} แถว, "
          f"{summary['issues']} เหตุการณ์ใน Issue Log) | ต้อง review {len(flagged)}")

    # --- publish to Google Sheets ------------------------------------------
    if sh is not None:
        from ops_yield import to_gsheet
        pushed = to_gsheet.push_workbook(sh, args.out)
        print(f"publish ขึ้น Google Sheets แล้ว: {', '.join(pushed)} "
              f"(คง Action เดิม {len(prior)} รายการ)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

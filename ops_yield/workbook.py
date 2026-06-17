"""Write parsed production records into an Excel workbook.

Three sheets:
  * ``Records``      — one row per LINE message (the audit trail).
  * ``Daily Yield``  — matrix: rows = date, columns = each machine + รวม (All).
  * ``Weekly Yield`` — matrix: rows = ISO week, columns = each machine + รวม.

Yield cells aggregate by **summing pass and total** across every report for
that machine/day (or week), then dividing — this is the correct way to combine
yields, not by averaging percentages. A green→red colour scale makes low
yield pop.

We read existing ``Records`` rows back in before rewriting, so re-running on a
new batch appends rather than clobbers (idempotent on the ``raw`` text).
"""

from __future__ import annotations

import os
from collections import defaultdict
from datetime import date, datetime

from openpyxl import Workbook, load_workbook
from openpyxl.formatting.rule import ColorScaleRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .parser import Record

RECORD_HEADERS = [
    "Date", "Week", "Machine", "Mode", "Issue Type", "Shift",
    "Total", "Fail L1", "Fail L2", "Splash", "Pass", "Yield",
    "Status Note", "Warnings", "Raw",
]

_HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
_HEADER_FONT = Font(color="FFFFFF", bold=True)
_PCT = "0.0%"


def _iso_week(d: date) -> str:
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def _machine_key(m):
    """Natural sort: numeric machines first (1,2,..10), text after."""
    s = str(m)
    return (0, int(s)) if s.isdigit() else (1, s)


def _style_header(ws, ncols: int) -> None:
    for c in range(1, ncols + 1):
        cell = ws.cell(row=1, column=c)
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.freeze_panes = "A2"


def _read_existing_records(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    wb = load_workbook(path)
    if "Records" not in wb.sheetnames:
        return []
    ws = wb["Records"]
    rows = []
    headers = [c.value for c in ws[1]]
    for r in ws.iter_rows(min_row=2, values_only=True):
        if all(v is None for v in r):
            continue
        rows.append(dict(zip(headers, r)))
    return rows


def _record_to_row(rec: Record) -> list:
    d = rec.work_date
    return [
        d.isoformat() if d else "",
        _iso_week(d) if d else "",
        rec.machine,
        rec.mode,
        rec.issue_type,
        rec.shift,
        rec.total,
        rec.fail_l1,
        rec.fail_l2,
        rec.splash,
        rec.passed,
        rec.yield_ratio,
        rec.status_note,
        "; ".join(rec.warnings),
        rec.raw,
    ]


def _row_key(row: list) -> tuple:
    """Dedup key: same date+machine+raw text => same report."""
    return (row[0], row[2], row[14])


def write_workbook(records: list[Record], path: str, *, append: bool = True) -> dict:
    """Build/refresh the workbook at ``path`` from ``records``.

    Returns a small summary dict (counts) for logging.
    """
    new_rows = [_record_to_row(r) for r in records]

    existing = []
    if append:
        for er in _read_existing_records(path):
            existing.append([er.get(h) for h in RECORD_HEADERS])

    seen = set()
    all_rows = []
    for row in existing + new_rows:
        k = _row_key(row)
        if k in seen:
            continue
        seen.add(k)
        all_rows.append(row)

    # sort by date then machine for a tidy sheet
    all_rows.sort(key=lambda r: (str(r[0]), _machine_key(r[2])))

    wb = Workbook()
    _build_records_sheet(wb, all_rows)
    machines = _build_matrix_sheet(wb, all_rows, "Daily Yield", key_index=0, key_title="Date")
    _build_matrix_sheet(wb, all_rows, "Weekly Yield", key_index=1, key_title="Week")

    wb.save(path)
    return {
        "records_total": len(all_rows),
        "records_added": len(new_rows),
        "machines": sorted(machines),
        "path": path,
    }


def _build_records_sheet(wb: Workbook, rows: list[list]) -> None:
    ws = wb.active
    ws.title = "Records"
    ws.append(RECORD_HEADERS)
    yield_col = RECORD_HEADERS.index("Yield") + 1
    for row in rows:
        ws.append(row)
        ws.cell(row=ws.max_row, column=yield_col).number_format = _PCT
    _style_header(ws, len(RECORD_HEADERS))
    widths = [12, 9, 8, 8, 12, 7, 7, 8, 8, 8, 7, 8, 24, 22, 40]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    if ws.max_row > 1:
        ws.conditional_formatting.add(
            f"L2:L{ws.max_row}",
            ColorScaleRule(
                start_type="num", start_value=0.8, start_color="F8696B",
                mid_type="num", mid_value=0.95, mid_color="FFEB84",
                end_type="num", end_value=1.0, end_color="63BE7B",
            ),
        )


def _build_matrix_sheet(
    wb: Workbook, rows: list[list], title: str, *, key_index: int, key_title: str
) -> set:
    """Aggregate pass/total into a period x machine yield matrix."""
    # agg[period][machine] = [pass_sum, total_sum]
    agg: dict[str, dict] = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    machines: set = set()
    for row in rows:
        period = row[key_index]
        machine = row[2]
        total = row[6] or 0
        passed = row[10] or 0
        if not period or not machine:
            continue
        machines.add(machine)
        agg[period][machine][0] += passed
        agg[period][machine][1] += total
        agg[period]["ALL"][0] += passed
        agg[period]["ALL"][1] += total

    machine_cols = sorted(machines, key=_machine_key)
    ws = wb.create_sheet(title)
    header = [key_title] + [f"เครื่อง {m}" for m in machine_cols] + ["รวม (All)"]
    ws.append(header)

    for period in sorted(agg):
        line = [period]
        for m in machine_cols:
            p, t = agg[period].get(m, [0, 0])
            line.append(p / t if t else None)
        p, t = agg[period]["ALL"]
        line.append(p / t if t else None)
        ws.append(line)
        for c in range(2, len(header) + 1):
            ws.cell(row=ws.max_row, column=c).number_format = _PCT

    _style_header(ws, len(header))
    ws.column_dimensions["A"].width = 12
    for i in range(2, len(header) + 1):
        ws.column_dimensions[get_column_letter(i)].width = 11
    if ws.max_row > 1 and len(header) > 1:
        last_col = get_column_letter(len(header))
        ws.conditional_formatting.add(
            f"B2:{last_col}{ws.max_row}",
            ColorScaleRule(
                start_type="num", start_value=0.8, start_color="F8696B",
                mid_type="num", mid_value=0.95, mid_color="FFEB84",
                end_type="num", end_value=1.0, end_color="63BE7B",
            ),
        )
    return machines

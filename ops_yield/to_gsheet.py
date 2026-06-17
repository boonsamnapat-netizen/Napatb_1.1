"""Publish the yield workbook to Google Sheets (gspread).

Google Sheets is the live dashboard: the team views it over the company network
and types into the Issue Log ``Action`` / ``Status`` columns. This module pushes
the freshly-computed sheets up there **without clobbering those edits** — it
reads the existing Action/Status back first (keyed by the hidden ``_key``
column) so the caller can fold them into the rebuild.

Not exercised in the sandbox (no network to Google). Needs ``gspread`` and a
Google service-account JSON key shared with the target spreadsheet. See
README for setup.

Typical flow (see ops_yield_cli.py --gsheet-url)::

    sh    = connect(creds_path, sheet_url)
    prior = read_actions(sh)                       # pull back user edits
    write_workbook(records, local_xlsx, prior_actions=prior)
    push_workbook(sh, local_xlsx)                  # publish every tab
"""

from __future__ import annotations

from openpyxl import load_workbook


def connect(creds_path: str, sheet_url: str):
    """Open the target spreadsheet via a service-account key."""
    import gspread  # imported lazily so the package works without it

    gc = gspread.service_account(filename=creds_path)
    return gc.open_by_url(sheet_url)


def read_actions(spreadsheet) -> dict:
    """Return {issue_key: (action, status)} from the live Issue Log tab."""
    try:
        ws = spreadsheet.worksheet("Issue Log")
    except Exception:
        return {}
    values = ws.get_all_values()
    if not values:
        return {}
    headers = values[0]
    try:
        ik, ia, ist = (headers.index("_key"),
                       headers.index("Action"), headers.index("Status"))
    except ValueError:
        return {}
    out = {}
    for row in values[1:]:
        if len(row) <= max(ik, ia, ist):
            continue
        key, action, status = row[ik], row[ia], row[ist]
        if key and (action or status):
            out[key] = (action, status)
    return out


def _sheet_values(ws) -> list[list]:
    """openpyxl worksheet -> 2D list of JSON-safe values for gspread."""
    out = []
    for row in ws.iter_rows(values_only=True):
        out.append(["" if v is None else v for v in row])
    return out


def push_workbook(spreadsheet, xlsx_path: str) -> list[str]:
    """Overwrite each tab of ``spreadsheet`` with the xlsx's sheets."""
    wb = load_workbook(xlsx_path)
    pushed = []
    for name in wb.sheetnames:
        values = _sheet_values(wb[name])
        rows = max(len(values), 1)
        cols = max((len(r) for r in values), default=1)
        try:
            ws = spreadsheet.worksheet(name)
            ws.clear()
        except Exception:
            ws = spreadsheet.add_worksheet(title=name, rows=rows + 10, cols=cols + 2)
        if values:
            ws.update(values, value_input_option="USER_ENTERED")
        pushed.append(name)
    return pushed

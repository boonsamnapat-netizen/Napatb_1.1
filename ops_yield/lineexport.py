"""Read a raw LINE chat export (.txt) into individual messages.

LINE's "Save chat history" format is::

    Wed, 17/06/2569 BE
    18:14<TAB>Sender<TAB>message text
    ...continuation lines for multi-line messages...

This module tokenizes that into ``(date_header, time, sender, text)`` messages,
joining multi-line bodies, and can keep only production-report messages.
"""

from __future__ import annotations

import re

from .parser import Record, looks_like_report, parse_message

_MSG = re.compile(r"^(\d\d:\d\d)\t([^\t]*)\t(.*)$", re.S)
_DATE_HEADER = re.compile(r"^[A-Z][a-z]{2}, \d\d/\d\d/\d{4} BE$")


def iter_messages(text: str):
    """Yield ``(date_header, time, sender, body)`` for each message."""
    cur_date = None
    buf: list | None = None

    def done(b):
        return tuple(b)

    for line in text.split("\n"):
        if _DATE_HEADER.match(line.strip()):
            if buf is not None:
                yield done(buf)
                buf = None
            cur_date = line.strip()
            continue
        m = _MSG.match(line)
        if m:
            if buf is not None:
                yield done(buf)
            t, s, body = m.groups()
            buf = [cur_date, t, s, body]
        elif buf is not None:
            buf[3] += "\n" + line
    if buf is not None:
        yield done(buf)


def parse_export(text: str, *, reports_only: bool = True) -> list[Record]:
    """Parse a whole LINE export into :class:`Record` objects.

    With ``reports_only`` (default) non-report chatter is skipped.
    """
    records: list[Record] = []
    for _date_header, _time, sender, body in iter_messages(text):
        body = body.strip().strip('"')
        if reports_only and not looks_like_report(body):
            continue
        records.append(parse_message(body, sender=sender))
    return records

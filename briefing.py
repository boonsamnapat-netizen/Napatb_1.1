#!/usr/bin/env python3
"""
Daily US stock pre-market briefing.

Usage:
  python briefing.py                 # full run (Claude digest + Discord post)
  python briefing.py --no-ai         # rules-based digest only (no API call)
  python briefing.py --no-post       # don't post to Discord

Reads the watchlist from config (briefing.watchlist) or data/universe.txt,
fetches recent daily data, and writes reports/briefings/briefing_<date>.md.
"""

import sys

from src.briefing.daily_briefing import main

if __name__ == "__main__":
    sys.exit(main())

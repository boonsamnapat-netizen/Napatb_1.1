#!/usr/bin/env python3
"""Telegram bot that turns a product photo into an approved 8-second clip.

    python affiliate_bot.py --once            # drain pending updates (GitHub Actions)
    python affiliate_bot.py --serve           # long-poll forever (VPS / local)
    python affiliate_bot.py --selftest        # render a demo clip, no Telegram

Without TELEGRAM_BOT_TOKEN the client runs dry: every send is logged instead.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time

import yaml

from src.affiliate import products as prod
from src.affiliate import script as scriptlib
from src.affiliate import store as st
from src.affiliate import video as videolib
from src.affiliate.pipeline import Pipeline, drain
from src.affiliate.telegram import TelegramClient, TelegramError

DEFAULT_CONFIG = "config/affiliate.yaml"


def load_config(path: str) -> dict:
    if not os.path.exists(path):
        logging.warning("config %s not found — using defaults", path)
        return {}
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def build(args: argparse.Namespace) -> tuple[TelegramClient, st.JobStore, Pipeline]:
    config = load_config(args.config)
    affiliate = config.get("affiliate", {}) or {}
    client = TelegramClient(timeout=int(affiliate.get("http_timeout_s", 60)))
    store = st.JobStore(args.state or affiliate.get("state_path",
                                                    "data/affiliate_state.json"))
    return client, store, Pipeline(client, store, config)


def cmd_once(args: argparse.Namespace) -> int:
    client, store, pipeline = build(args)
    if not client.configured:
        print("TELEGRAM_BOT_TOKEN not set — nothing to poll.")
        return 0
    results = drain(client, store, pipeline, poll_timeout=args.poll_timeout)
    removed = store.prune()
    store.save()
    for line in results:
        print(" ", line)
    print(f"processed {len(results)} update(s); pruned {removed} old job(s)")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    client, store, pipeline = build(args)
    if not client.configured:
        print("TELEGRAM_BOT_TOKEN not set — cannot serve.", file=sys.stderr)
        return 1
    print("polling… (ctrl-c to stop)")
    while True:
        try:
            for line in drain(client, store, pipeline, poll_timeout=args.poll_timeout):
                print(" ", line)
        except TelegramError as exc:
            logging.warning("telegram error: %s — retrying in 10s", exc)
            time.sleep(10)
        except KeyboardInterrupt:
            print("\nstopped.")
            return 0


def cmd_selftest(args: argparse.Namespace) -> int:
    """Render a clip from a local image without touching the network."""
    config = load_config(args.config)
    demo = prod.Product(title="ตัวอย่างสินค้า", url="https://example.com/p/1",
                        platform="lazada", price=199, sold=1200, commission_pct=8)
    clip = scriptlib.build(demo)
    print(scriptlib.storyboard(clip))
    print("\ncaption:\n" + clip.caption)
    print("hashtags: " + " ".join(clip.hashtags))
    if not args.image:
        print("\n(pass --image PATH to also render the mp4)")
        return 0
    maker = videolib.make((config.get("affiliate", {}) or {}).get("video", {}))
    out = args.out or "data/affiliate/selftest.mp4"
    try:
        print("\nrendering with " + maker.name + " …")
        print("wrote " + maker.render(args.image, clip, out))
    except videolib.VideoError as exc:
        print(f"render failed: {exc}", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument("--state", help="override the job state file path")
    parser.add_argument("--poll-timeout", type=int, default=0,
                        help="seconds to long-poll getUpdates (0 = return at once)")
    parser.add_argument("--log-level", default="INFO")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--once", action="store_true", help="drain pending updates and exit")
    mode.add_argument("--serve", action="store_true", help="poll continuously")
    mode.add_argument("--selftest", action="store_true", help="build a demo clip offline")
    parser.add_argument("--image", help="selftest: source photo")
    parser.add_argument("--out", help="selftest: output mp4 path")
    args = parser.parse_args(argv)

    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO),
                        format="%(levelname)s %(name)s: %(message)s")
    if args.serve:
        return cmd_serve(args)
    if args.selftest:
        return cmd_selftest(args)
    return cmd_once(args)


if __name__ == "__main__":
    raise SystemExit(main())

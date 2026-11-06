#!/usr/bin/env python3
"""Metrics for the Short-form Marketing OS (stdlib only).

  python tools/metrics.py research    --data data   # D3 / D4 / D5 inputs
  python tools/metrics.py performance --data data   # D9 inputs

Blank cells are treated as "no data" (never as 0). Definitions: CONTEXT_STRUCTURE.md.
"""
import argparse
import csv
import os
from collections import defaultdict
from datetime import datetime, timedelta
from statistics import median


def num(v):
    try:
        return float(v) if str(v).strip() != "" else None
    except ValueError:
        return None


def parse_dt(v):
    v = (v or "").strip().replace("Z", "")
    for n in (19, 16, 10):
        try:
            return datetime.fromisoformat(v[:n])
        except ValueError:
            continue
    return None


def read_csv(path):
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def write_csv(path, rows, fields):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {path} ({len(rows)} rows)")


def fmt(x, nd=2):
    if x is None:
        return ""
    return int(round(x)) if nd == 0 else round(x, nd)


def engagement(r, views):
    """Return (er_per_1k, fields_used, ss_per_1k) using only cells that have data."""
    if not views:
        return None, "", None
    parts = {k: num(r.get(k)) for k in ("likes", "comments", "shares", "saves")}
    used = {k: v for k, v in parts.items() if v is not None}
    er = sum(used.values()) / views * 1000 if used else None
    ss = None
    if parts["shares"] is not None and parts["saves"] is not None:
        ss = (parts["shares"] + parts["saves"]) / views * 1000
    return er, "+".join(used), ss


def pct_ranks(values):
    """Percentile rank (0..1) for each non-None value; ties share the average rank."""
    idx = sorted((v, i) for i, v in enumerate(values) if v is not None)
    out = [None] * len(values)
    n = len(idx)
    j = 0
    while j < n:
        k = j
        while k + 1 < n and idx[k + 1][0] == idx[j][0]:
            k += 1
        r = ((j + k) / 2) / (n - 1) if n > 1 else 1.0
        for t in range(j, k + 1):
            out[idx[t][1]] = r
        j = k + 1
    return out


def assign_rank(rows, key, col):
    ranked = sorted((r for r in rows if r[key] != ""), key=lambda r: -float(r[key]))
    for i, r in enumerate(ranked, 1):
        r[col] = i
    for r in rows:
        r.setdefault(col, "")


def research(a):
    videos = read_csv(os.path.join(a.data, "videos.csv"))
    if not videos:
        print("videos.csv ว่าง — ยังไม่มีข้อมูลให้คำนวณ")
        return

    by_creator = defaultdict(list)
    for r in videos:
        v = num(r.get("views"))
        if v is not None:
            by_creator[(r.get("creator_handle"), r.get("platform"))].append(v)

    for r in videos:
        views = num(r.get("views"))
        med = num(r.get("creator_median_views"))
        med_src = "given"
        if med is None:
            pool = by_creator[(r.get("creator_handle"), r.get("platform"))]
            if len(pool) >= a.min_creator_videos:
                med, med_src = median(pool), "computed"
            else:
                med_src = "insufficient"
        score = views / med if (views is not None and med) else None
        er, used, ss = engagement(r, views)
        r.update(median_used=fmt(med, 0), median_source=med_src, outlier_score=fmt(score),
                 is_outlier=int(score is not None and score >= a.outlier_min),
                 er_per_1k=fmt(er), er_fields=used, ss_per_1k=fmt(ss))

    ers = [num(r["er_per_1k"]) for r in videos if num(r["er_per_1k"]) is not None]
    niche_er = median(ers) if ers else None
    for r in videos:
        er = num(r["er_per_1k"])
        r["dead_views"] = int(bool(r["is_outlier"]) and niche_er is not None
                              and er is not None and er < a.dead_factor * niche_er)

    pr_s = pct_ranks([num(r["outlier_score"]) for r in videos])
    pr_e = pct_ranks([num(r["er_per_1k"]) for r in videos])
    for r, s, e in zip(videos, pr_s, pr_e):
        r["_combo"] = fmt((s + e) / 2, 4) if s is not None and e is not None else ""
    assign_rank(videos, "_combo", "rank_views_er")
    assign_rank(videos, "ss_per_1k", "rank_ss")

    out = a.out
    fields = list(videos[0].keys())
    fields = [f for f in fields if f != "_combo"]
    write_csv(os.path.join(out, "D03", "videos_scored.csv"), videos, fields)
    print(f"niche median ER/1K = {fmt(niche_er)} · outliers = {sum(r['is_outlier'] for r in videos)}"
          f" · no median = {sum(r['median_source'] == 'insufficient' for r in videos)}")

    # ---- creators (D4)
    dates = [parse_dt(r.get("posted_at")) for r in videos]
    asof = parse_dt(a.asof) if a.asof else max((d for d in dates if d), default=None)
    groups = defaultdict(list)
    for r in videos:
        groups[(r.get("creator_handle"), r.get("platform"))].append(r)
    crows = []
    for (h, p), rs in groups.items():
        views = [num(r["views"]) for r in rs if num(r["views"]) is not None]
        ers_c = [num(r["er_per_1k"]) for r in rs if num(r["er_per_1k"]) is not None]
        outs = [r for r in rs if r["is_outlier"]]
        odates = [d for d in (parse_dt(r.get("posted_at")) for r in outs) if d]
        last = max(odates) if odates else None
        crows.append(dict(
            creator_handle=h, platform=p, n_videos=len(rs),
            median_views=fmt(median(views), 0) if views else "",
            median_er_per_1k=fmt(median(ers_c)) if ers_c else "",
            n_outliers=len(outs), repeatable=int(len(outs) >= a.min_outliers),
            last_outlier_date=last.date().isoformat() if last else "",
            active_recent=("" if not (last and asof)
                           else int(last >= asof - timedelta(days=a.active_days))),
        ))
    crows.sort(key=lambda c: (-c["n_outliers"], -(num(c["median_er_per_1k"]) or 0)))
    write_csv(os.path.join(out, "D03", "creators_scored.csv"), crows, list(crows[0].keys()))

    # ---- hook structures (D5)
    hooks = [h for h in read_csv(os.path.join(a.data, "hook_bank.csv")) if h.get("structure")]
    if not hooks:
        print("hook_bank.csv ยังไม่มีคอลัมน์ structure — ข้ามสถิติ hook")
        return
    vid = {r["video_id"]: r for r in videos if not r["dead_views"]}
    st = defaultdict(lambda: {"views": [], "score": []})
    for h in hooks:
        v = vid.get(h["video_id"])
        if not v:
            continue
        s = st[h["structure"]]
        if num(v["views"]) is not None:
            s["views"].append(num(v["views"]))
        if num(v["outlier_score"]) is not None:
            s["score"].append(num(v["outlier_score"]))
    srows = [dict(structure=k, n=len(s["views"]),
                  median_views=fmt(median(s["views"]), 0) if s["views"] else "",
                  median_outlier_score=fmt(median(s["score"])) if s["score"] else "",
                  low_sample=int(len(s["views"]) < a.min_samples))
             for k, s in st.items()]
    srows.sort(key=lambda x: (x["low_sample"], -(num(x["median_outlier_score"]) or 0)))
    write_csv(os.path.join(out, "D05", "hook_structure_stats.csv"), srows, list(srows[0].keys()))


def performance(a):
    rows = [r for r in read_csv(os.path.join(a.data, "performance_log.csv"))
            if num(r.get("snapshot_hours")) == a.hours]
    if not rows:
        print(f"ไม่มีแถวที่ snapshot_hours = {a.hours:g}")
        return
    rows.sort(key=lambda r: parse_dt(r.get("posted_at")) or datetime.min)
    history = defaultdict(list)  # platform -> prior views
    for r in rows:
        v = num(r.get("views"))
        prior = history[r.get("platform")]
        base = median(prior) if len(prior) >= a.min_samples else None
        ratio = v / base if (v is not None and base) else None
        if v is None:
            label = "no_data"
        elif base is None:
            label = "baseline_insufficient"
        elif ratio >= a.winner:
            label = "winner"
        elif ratio <= a.loser:
            label = "loser"
        else:
            label = "neutral"
        er, used, ss = engagement(r, v)
        r.update(baseline_median=fmt(base, 0), views_ratio=fmt(ratio), label=label,
                 er_per_1k=fmt(er), er_fields=used, ss_per_1k=fmt(ss))
        if v is not None:
            prior.append(v)
    write_csv(os.path.join(a.out, "D09", "performance_scored.csv"), rows, list(rows[0].keys()))
    counts = defaultdict(int)
    for r in rows:
        counts[r["label"]] += 1
    print(" · ".join(f"{k}={v}" for k, v in sorted(counts.items())))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("mode", choices=["research", "performance"])
    p.add_argument("--data", default="data")
    p.add_argument("--out", default=None, help="default: <data>/../outputs")
    p.add_argument("--outlier-min", type=float, default=3.0)
    p.add_argument("--dead-factor", type=float, default=0.5)
    p.add_argument("--min-outliers", type=int, default=2)
    p.add_argument("--active-days", type=int, default=30)
    p.add_argument("--min-samples", type=int, default=5)
    p.add_argument("--min-creator-videos", type=int, default=5,
                   help="videos needed to compute a creator median when none is given")
    p.add_argument("--asof", default=None, help="reference date for 'active' (default: newest posted_at)")
    p.add_argument("--hours", type=float, default=48)
    p.add_argument("--winner", type=float, default=1.5)
    p.add_argument("--loser", type=float, default=0.5)
    a = p.parse_args()
    a.out = a.out or os.path.join(os.path.dirname(os.path.abspath(a.data)), "outputs")
    research(a) if a.mode == "research" else performance(a)


if __name__ == "__main__":
    main()

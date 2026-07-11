#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
claude_monitor - Claude Code usage monitor (Windows / Linux / macOS)

Parses Claude Code transcript files (~/.claude/projects/**/*.jsonl) and reports
token usage, estimated API-equivalent cost, per-model / per-project breakdowns,
5-hour rate-limit blocks, and a live auto-refreshing dashboard.

No third-party dependencies. Python 3.8+.

Usage:
  python claude_monitor.py               # summary: today + current block + last 7 days
  python claude_monitor.py daily         # daily table (--days N, default 14)
  python claude_monitor.py monthly       # monthly table
  python claude_monitor.py models        # per-model breakdown
  python claude_monitor.py projects      # per-project breakdown
  python claude_monitor.py blocks        # 5-hour rate-limit blocks (--limit N)
  python claude_monitor.py live          # live dashboard (--interval N seconds)

Note: if you are on a Pro/Max subscription you don't pay per token; the cost
shown is the API-equivalent value of your usage.
"""

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ---------------------------------------------------------------- pricing ---
# (input $/MTok, output $/MTok). Cache write 5m = 1.25x input, 1h = 2x input,
# cache read = 0.1x input. Matched by longest prefix.
PRICING = {
    "claude-fable-5":     (10.0, 50.0),
    "claude-mythos-5":    (10.0, 50.0),
    "claude-opus-4-8":    (5.0, 25.0),
    "claude-opus-4-7":    (5.0, 25.0),
    "claude-opus-4-6":    (5.0, 25.0),
    "claude-opus-4-5":    (5.0, 25.0),
    "claude-opus-4-1":    (15.0, 75.0),
    "claude-opus-4-2":    (15.0, 75.0),
    "claude-opus-4":      (15.0, 75.0),
    "claude-sonnet-5":    None,  # intro pricing, resolved per-date below
    "claude-sonnet-4":    (3.0, 15.0),
    "claude-haiku-4-5":   (1.0, 5.0),
    "claude-3-5-haiku":   (0.8, 4.0),
    "claude-3-haiku":     (0.25, 1.25),
}
SONNET5_INTRO_END = datetime(2026, 8, 31, tzinfo=timezone.utc)


def model_price(model, ts):
    if not model or model == "<synthetic>":
        return None
    if model.startswith("claude-sonnet-5"):
        return (2.0, 10.0) if ts <= SONNET5_INTRO_END else (3.0, 15.0)
    best = None
    for prefix, price in PRICING.items():
        if price and model.startswith(prefix):
            if best is None or len(prefix) > len(best[0]):
                best = (prefix, price)
    return best[1] if best else None


def entry_cost(e):
    price = model_price(e["model"], e["ts"])
    if not price:
        return 0.0
    p_in, p_out = price
    return (
        e["input"] * p_in
        + e["output"] * p_out
        + e["cache_5m"] * p_in * 1.25
        + e["cache_1h"] * p_in * 2.0
        + e["cache_read"] * p_in * 0.10
    ) / 1_000_000


# ------------------------------------------------------------------ loader ---
EXTRA_DATA_DIRS = []  # user-configured roots (GUI settings); tried first


def data_dirs():
    dirs = []
    candidates = []
    for d in EXTRA_DATA_DIRS:
        p = Path(d)
        # accept either the Claude config dir (~/.claude) or its projects/ dir
        candidates.append(p / "projects" if (p / "projects").is_dir() else p)
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    if env:
        candidates.append(Path(env) / "projects")
    candidates.append(Path.home() / ".claude" / "projects")
    candidates.append(Path.home() / ".config" / "claude" / "projects")
    for c in candidates:
        if c.is_dir() and c not in dirs:
            dirs.append(c)
    return dirs


def load_entries(since=None):
    """Parse all transcripts; return a list of usage entries sorted by time."""
    entries = []
    seen = set()
    for base in data_dirs():
        for path in base.rglob("*.jsonl"):
            project = path.parent.name
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    for line in f:
                        if '"usage"' not in line:
                            continue
                        try:
                            obj = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if obj.get("type") != "assistant":
                            continue
                        msg = obj.get("message") or {}
                        usage = msg.get("usage")
                        if not usage:
                            continue
                        # dedupe retried/streamed duplicates
                        key = (msg.get("id"), obj.get("requestId"))
                        if key != (None, None):
                            if key in seen:
                                continue
                            seen.add(key)
                        ts_raw = obj.get("timestamp")
                        if not ts_raw:
                            continue
                        try:
                            ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
                        except ValueError:
                            continue
                        if since and ts < since:
                            continue
                        cc = usage.get("cache_creation") or {}
                        c5m = cc.get("ephemeral_5m_input_tokens")
                        c1h = cc.get("ephemeral_1h_input_tokens")
                        if c5m is None and c1h is None:
                            # older records: no split, assume 5m
                            c5m = usage.get("cache_creation_input_tokens", 0) or 0
                            c1h = 0
                        entries.append({
                            "ts": ts,
                            "model": msg.get("model") or "",
                            "project": project,
                            "input": usage.get("input_tokens", 0) or 0,
                            "output": usage.get("output_tokens", 0) or 0,
                            "cache_5m": c5m or 0,
                            "cache_1h": c1h or 0,
                            "cache_read": usage.get("cache_read_input_tokens", 0) or 0,
                        })
            except OSError:
                continue
    entries.sort(key=lambda e: e["ts"])
    return entries


# -------------------------------------------------------------- aggregation ---
class Agg:
    __slots__ = ("input", "output", "cache_w", "cache_r", "cost", "count", "models")

    def __init__(self):
        self.input = self.output = self.cache_w = self.cache_r = 0
        self.cost = 0.0
        self.count = 0
        self.models = set()

    def add(self, e):
        self.input += e["input"]
        self.output += e["output"]
        self.cache_w += e["cache_5m"] + e["cache_1h"]
        self.cache_r += e["cache_read"]
        self.cost += entry_cost(e)
        self.count += 1
        if e["model"] and e["model"] != "<synthetic>":
            self.models.add(e["model"])

    @property
    def total(self):
        return self.input + self.output + self.cache_w + self.cache_r


def blocks_of(entries, hours=5):
    """Group entries into rate-limit blocks: start = first activity floored to
    the hour (UTC); a block spans `hours`; a gap > `hours` starts a new one."""
    span = timedelta(hours=hours)
    blocks = []
    cur = None
    last_ts = None
    for e in entries:
        if cur is None or e["ts"] >= cur["start"] + span or (last_ts and e["ts"] - last_ts > span):
            start = e["ts"].replace(minute=0, second=0, microsecond=0)
            cur = {"start": start, "end": start + span, "agg": Agg(),
                   "first": e["ts"], "last": e["ts"]}
            blocks.append(cur)
        cur["agg"].add(e)
        cur["last"] = e["ts"]
        last_ts = e["ts"]
    return blocks


# -------------------------------------------------------------- formatting ---
def supports_color():
    # under pythonw (GUI, no console) sys.stdout is None — never touch it
    out = sys.stdout
    return out is not None and hasattr(out, "isatty") and out.isatty()


if os.name == "nt" and supports_color():
    os.system("")  # enable ANSI escape sequences in the Windows console

USE_COLOR = supports_color()


def c(text, code):
    return f"\x1b[{code}m{text}\x1b[0m" if USE_COLOR else str(text)


def bold(t):    return c(t, "1")
def dim(t):     return c(t, "2")
def green(t):   return c(t, "32")
def yellow(t):  return c(t, "33")
def red(t):     return c(t, "31")
def cyan(t):    return c(t, "36")


def fmt(n):
    if n >= 1_000_000_000:
        return f"{n / 1e9:.2f}B"
    if n >= 1_000_000:
        return f"{n / 1e6:.2f}M"
    if n >= 1_000:
        return f"{n / 1e3:.1f}K"
    return str(int(n))


def money(v):
    return f"${v:,.2f}"


def short_model(m):
    return (m.replace("claude-", "")) if m else "?"


def table(headers, rows, aligns=None):
    widths = [len(h) for h in headers]
    srows = [[str(x) for x in r] for r in rows]
    for r in srows:
        for i, cell in enumerate(r):
            widths[i] = max(widths[i], len(cell))
    aligns = aligns or ["<"] + [">"] * (len(headers) - 1)
    def line(cells, style=None):
        parts = []
        for i, cell in enumerate(cells):
            parts.append(f"{cell:{aligns[i]}{widths[i]}}")
        s = "  ".join(parts)
        return style(s) if style else s
    out = [line(headers, bold), dim("-" * (sum(widths) + 2 * (len(widths) - 1)))]
    out.extend(line(r) for r in srows)
    return "\n".join(out)


def local(ts):
    return ts.astimezone()


# ---------------------------------------------------------------- commands ---
def group_by(entries, keyfn):
    groups = defaultdict(Agg)
    for e in entries:
        groups[keyfn(e)].add(e)
    return groups


def totals_row(aggs):
    t = Agg()
    for a in aggs:
        t.input += a.input; t.output += a.output
        t.cache_w += a.cache_w; t.cache_r += a.cache_r
        t.cost += a.cost; t.count += a.count
    return t


def cmd_daily(entries, days):
    since = datetime.now(timezone.utc) - timedelta(days=days)
    entries = [e for e in entries if e["ts"] >= since]
    groups = group_by(entries, lambda e: local(e["ts"]).strftime("%Y-%m-%d"))
    rows = []
    for day in sorted(groups):
        a = groups[day]
        rows.append([day, fmt(a.input), fmt(a.output), fmt(a.cache_w),
                     fmt(a.cache_r), fmt(a.total), money(a.cost),
                     ",".join(sorted(short_model(m) for m in a.models))])
    t = totals_row(groups.values())
    rows.append([bold("TOTAL"), fmt(t.input), fmt(t.output), fmt(t.cache_w),
                 fmt(t.cache_r), fmt(t.total), bold(money(t.cost)), ""])
    print(bold(f"\nDaily usage (last {days} days, local time)\n"))
    print(table(["Date", "Input", "Output", "CacheW", "CacheR", "Total", "Cost", "Models"], rows,
                aligns=["<", ">", ">", ">", ">", ">", ">", "<"]))


def cmd_monthly(entries):
    groups = group_by(entries, lambda e: local(e["ts"]).strftime("%Y-%m"))
    rows = []
    for month in sorted(groups):
        a = groups[month]
        rows.append([month, fmt(a.input), fmt(a.output), fmt(a.cache_w),
                     fmt(a.cache_r), fmt(a.total), money(a.cost)])
    t = totals_row(groups.values())
    rows.append([bold("TOTAL"), fmt(t.input), fmt(t.output), fmt(t.cache_w),
                 fmt(t.cache_r), fmt(t.total), bold(money(t.cost))])
    print(bold("\nMonthly usage (local time)\n"))
    print(table(["Month", "Input", "Output", "CacheW", "CacheR", "Total", "Cost"], rows))


def cmd_models(entries):
    groups = group_by(entries, lambda e: e["model"] or "?")
    rows = []
    for model, a in sorted(groups.items(), key=lambda kv: -kv[1].cost):
        rows.append([short_model(model), a.count, fmt(a.input), fmt(a.output),
                     fmt(a.cache_w), fmt(a.cache_r), money(a.cost)])
    t = totals_row(groups.values())
    rows.append([bold("TOTAL"), t.count, fmt(t.input), fmt(t.output),
                 fmt(t.cache_w), fmt(t.cache_r), bold(money(t.cost))])
    print(bold("\nUsage by model (all time)\n"))
    print(table(["Model", "Msgs", "Input", "Output", "CacheW", "CacheR", "Cost"], rows))


def cmd_projects(entries):
    groups = group_by(entries, lambda e: e["project"])
    rows = []
    for proj, a in sorted(groups.items(), key=lambda kv: -kv[1].cost):
        name = proj[:48] + ("..." if len(proj) > 48 else "")
        rows.append([name, a.count, fmt(a.total), money(a.cost)])
    t = totals_row(groups.values())
    rows.append([bold("TOTAL"), t.count, fmt(t.total), bold(money(t.cost))])
    print(bold("\nUsage by project (all time)\n"))
    print(table(["Project", "Msgs", "Tokens", "Cost"], rows))


def cmd_blocks(entries, limit):
    blocks = blocks_of(entries)[-limit:]
    now = datetime.now(timezone.utc)
    rows = []
    for b in blocks:
        a = b["agg"]
        active = b["start"] <= now < b["end"]
        start_s = local(b["start"]).strftime("%m-%d %H:%M")
        end_s = local(b["end"]).strftime("%H:%M")
        status = green("ACTIVE") if active else dim("ended")
        rows.append([f"{start_s} - {end_s}", status, a.count,
                     fmt(a.input), fmt(a.output), fmt(a.total), money(a.cost)])
    print(bold(f"\n5-hour blocks (last {limit}, local time)\n"))
    print(table(["Block", "Status", "Msgs", "Input", "Output", "Total", "Cost"], rows,
                aligns=["<", "<", ">", ">", ">", ">", ">"]))


def bar(ratio, width=30):
    ratio = max(0.0, min(1.0, ratio))
    filled = int(ratio * width)
    color = green if ratio < 0.6 else (yellow if ratio < 0.85 else red)
    return color("#" * filled) + dim("-" * (width - filled))


def render_live(entries):
    now = datetime.now(timezone.utc)
    blocks = blocks_of(entries)
    cur = blocks[-1] if blocks and blocks[-1]["start"] <= now < blocks[-1]["end"] else None
    today_key = local(now).strftime("%Y-%m-%d")
    today = group_by(entries, lambda e: local(e["ts"]).strftime("%Y-%m-%d")).get(today_key, Agg())

    lines = []
    lines.append(bold(cyan("  CLAUDE USAGE MONITOR")) + dim(f"   refreshed {local(now).strftime('%H:%M:%S')}   (Ctrl+C to quit)"))
    lines.append("")
    if cur:
        a = cur["agg"]
        elapsed = (now - cur["start"]).total_seconds() / 60
        span = (cur["end"] - cur["start"]).total_seconds() / 60
        remain = span - elapsed
        rate = a.total / elapsed if elapsed > 0 else 0
        proj = a.total + rate * remain
        lines.append(bold("  Current 5h block  ")
                     + dim(f"{local(cur['start']).strftime('%H:%M')} - {local(cur['end']).strftime('%H:%M')}"))
        lines.append(f"    time     [{bar(elapsed / span)}] {elapsed:.0f}m / {span:.0f}m  ({remain:.0f}m left)")
        lines.append(f"    tokens   {bold(fmt(a.total))}   in {fmt(a.input)}  out {fmt(a.output)}  cacheW {fmt(a.cache_w)}  cacheR {fmt(a.cache_r)}")
        lines.append(f"    cost     {bold(money(a.cost))}   msgs {a.count}   burn {fmt(rate)} tok/min   proj. {fmt(proj)} by block end")
    else:
        lines.append(dim("  No active 5h block (no recent messages)."))
    lines.append("")
    lines.append(bold("  Today") + dim(f"  ({today_key})"))
    lines.append(f"    tokens   {bold(fmt(today.total))}   in {fmt(today.input)}  out {fmt(today.output)}  cacheW {fmt(today.cache_w)}  cacheR {fmt(today.cache_r)}")
    lines.append(f"    cost     {bold(money(today.cost))}   msgs {today.count}   models: {', '.join(sorted(short_model(m) for m in today.models)) or '-'}")
    lines.append("")
    lines.append(dim("  Cost = API-equivalent value (subscription users don't pay per token)."))
    return "\n".join(lines)


def cmd_live(interval):
    try:
        while True:
            since = datetime.now(timezone.utc) - timedelta(days=2)
            entries = load_entries(since=since)
            sys.stdout.write("\x1b[2J\x1b[H" if USE_COLOR else "\n" * 2)
            print(render_live(entries))
            time.sleep(interval)
    except KeyboardInterrupt:
        print()


def cmd_summary(entries):
    now = datetime.now(timezone.utc)
    print(render_live(entries))
    since = now - timedelta(days=7)
    recent = [e for e in entries if e["ts"] >= since]
    if recent:
        cmd_daily(entries, 7)
    print()


# -------------------------------------------------------------------- main ---
def main():
    ap = argparse.ArgumentParser(description="Claude Code usage monitor")
    ap.add_argument("command", nargs="?", default="summary",
                    choices=["summary", "daily", "monthly", "models", "projects", "blocks", "live"])
    ap.add_argument("--days", type=int, default=14, help="days for daily report")
    ap.add_argument("--limit", type=int, default=10, help="number of blocks to show")
    ap.add_argument("--interval", type=int, default=10, help="live refresh seconds")
    args = ap.parse_args()

    if not data_dirs():
        print(red("No Claude Code data found (~/.claude/projects)."))
        sys.exit(1)

    if args.command == "live":
        cmd_live(args.interval)
        return

    entries = load_entries()
    if not entries:
        print(yellow("No usage records found."))
        return

    if args.command == "summary":
        cmd_summary(entries)
    elif args.command == "daily":
        cmd_daily(entries, args.days)
    elif args.command == "monthly":
        cmd_monthly(entries)
    elif args.command == "models":
        cmd_models(entries)
    elif args.command == "projects":
        cmd_projects(entries)
    elif args.command == "blocks":
        cmd_blocks(entries, args.limit)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
JFR Lock Contention Analysis -- monitor enter, wait, inflate.

Shows contended locks ranked by total blocked time, with stack traces
and per-thread breakdowns. Detects ReadWriteLock patterns.

Usage:
    python -m rtx_tools.profiler.jfr_locks profile.jfr
    python -m rtx_tools.profiler.jfr_locks profile.jfr --min-duration 1
    python -m rtx_tools.profiler.jfr_locks profile.jfr -t "^main$"
    python -m rtx_tools.profiler.jfr_locks profile.jfr --stacks
"""

import argparse
import sys
from collections import defaultdict

from .jfr_parse import (
    apply_common_filters,
    event_duration_ms,
    fmt_count,
    fmt_ms,
    fmt_pct,
    jfr_events,
    jfr_summary_text,
    json_output,
    parse_summary_events,
    print_header,
    stack_frames,
    thread_name,
)


def _monitor_class(ev):
    mc = ev.get("values", {}).get("monitorClass")
    if isinstance(mc, dict):
        return mc.get("name", "?").replace("/", ".")
    return str(mc) if mc else "?"


def _render_json(sorted_monitors, top):
    """Return the JSON-serialisable dict for --json output.

    *sorted_monitors* is a list of (monitor_class, total_ms, count, max_ms, thread_count)
    tuples sorted by total_ms descending.

    Keys match what generate_profile_data.py's build_jfr() reads:
      locks[].{monitor, site, waitMs, count}
    """
    locks = []
    for item in sorted_monitors[:top]:
        cls, total_ms, count = item[0], item[1], item[2]
        locks.append(
            {
                "monitor": cls,
                "site": None,  # site is not tracked at monitor aggregation level
                "waitMs": total_ms,
                "count": count,
            }
        )
    return {"locks": locks}


def run(args):
    jfr = args.jfr_file
    summary = jfr_summary_text(jfr)
    available = {n for n, _, _ in parse_summary_events(summary)}

    lock_types = [
        t for t in ("jdk.JavaMonitorEnter", "jdk.JavaMonitorWait", "jdk.JavaMonitorInflate") if t in available
    ]

    if not lock_types:
        if args.json:
            json_output(_render_json([], top=args.top))
            return
        print("No lock contention events found in this recording.", file=sys.stderr)
        sys.exit(1)

    events = jfr_events(jfr, lock_types)
    events = apply_common_filters(events, args)

    if args.min_duration > 0:
        events = [ev for ev in events if event_duration_ms(ev) >= args.min_duration]

    if not events:
        if args.json:
            json_output(_render_json([], top=args.top))
            return
        print("No lock events match the filters.", file=sys.stderr)
        sys.exit(1)

    # -- By monitor class --
    monitor_time = defaultdict(float)
    monitor_count = defaultdict(int)
    monitor_max = defaultdict(float)
    monitor_threads = defaultdict(set)
    for ev in events:
        cls = _monitor_class(ev)
        dur = event_duration_ms(ev)
        monitor_time[cls] += dur
        monitor_count[cls] += 1
        monitor_max[cls] = max(monitor_max[cls], dur)
        monitor_threads[cls].add(thread_name(ev))

    sorted_monitors = sorted(monitor_time.items(), key=lambda x: x[1], reverse=True)
    total_blocked = sum(monitor_time.values())

    if args.json:
        rows = [(c, t, monitor_count[c], monitor_max[c], len(monitor_threads[c])) for c, t in sorted_monitors]
        json_output(_render_json(rows, top=args.top))
        return

    print_header(f"Lock Contention ({fmt_count(len(events))} events, {fmt_ms(total_blocked)} total blocked)")

    cw = max((len(c) for c, _ in sorted_monitors[: args.top]), default=30)
    print(f"\n  {'#':>4}  {'Monitor Class':<{cw}}  {'Total':>10}  {'Count':>8}  {'Max':>10}  {'Threads':>8}  {'%':>7}")
    print(f"  {'':>4}  {'':-<{cw}}  {'':->10}  {'':->8}  {'':->10}  {'':->8}  {'':->7}")

    for i, (cls, total) in enumerate(sorted_monitors[: args.top], 1):
        # Detect RWL pattern
        rwl_marker = ""
        if "ReadWriteLock" in cls or "ReentrantReadWriteLock" in cls:
            rwl_marker = " [RWL]"

        print(
            f"  {i:>4}  {cls:<{cw}}  {fmt_ms(total):>10}  {monitor_count[cls]:>8}  "
            f"{fmt_ms(monitor_max[cls]):>10}  {len(monitor_threads[cls]):>8}  "
            f"{fmt_pct(total, total_blocked)}{rwl_marker}"
        )

    # -- RWL detection from stack frames --
    rwl_events = [
        ev
        for ev in events
        if any("ReadWriteLock" in f or "ReentrantReadWriteLock" in f for f in stack_frames(ev, simple=False)[:5])
    ]
    if rwl_events:
        print(f"\n  ReadWriteLock contention detected: {len(rwl_events)} events")
        rwl_dur = sum(event_duration_ms(ev) for ev in rwl_events)
        print(f"  Total RWL blocked time: {fmt_ms(rwl_dur)}")

    # -- Stack details --
    if args.stacks:
        print(f"\n{'--- Stack Details (top 5 contended monitors) ---':^80}")
        for cls, _ in sorted_monitors[:5]:
            cls_events = [ev for ev in events if _monitor_class(ev) == cls]
            if not cls_events:
                continue
            print(f"\n  {cls}  [{monitor_count[cls]} events, {fmt_ms(monitor_time[cls])}]")
            site_count = defaultdict(int)
            site_example = {}
            for ev in cls_events:
                frames = stack_frames(ev, simple=True)
                key = frames[0] if frames else "<no stack>"
                site_count[key] += 1
                if key not in site_example:
                    site_example[key] = frames[:8]
            for site, cnt in sorted(site_count.items(), key=lambda x: x[1], reverse=True)[:3]:
                print(f"    [{cnt} events] {site}")
                for f in site_example[site][:5]:
                    print(f"      {f}")

    # -- Per-thread breakdown --
    if not args.thread and len(events) > 20:
        thread_blocked = defaultdict(float)
        thread_cnt = defaultdict(int)
        for ev in events:
            tn = thread_name(ev)
            thread_blocked[tn] += event_duration_ms(ev)
            thread_cnt[tn] += 1

        sorted_thr = sorted(thread_blocked.items(), key=lambda x: x[1], reverse=True)
        print("\n  Per-Thread Lock Wait:")
        tw = max((len(n) for n, _ in sorted_thr[:10]), default=20)
        for tn, dur in sorted_thr[:10]:
            print(f"    {tn:<{tw}}  {fmt_ms(dur):>10}  ({thread_cnt[tn]} events)")

    print()


def main():
    parser = argparse.ArgumentParser(
        description="Lock contention analysis from JFR recordings.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  python -m rtx_tools.profiler.jfr_locks profile.jfr                      # all contention
  python -m rtx_tools.profiler.jfr_locks profile.jfr --min-duration 1     # only blocks > 1ms
  python -m rtx_tools.profiler.jfr_locks profile.jfr --stacks             # with stack traces
  python -m rtx_tools.profiler.jfr_locks profile.jfr -t "^main$"          # main thread only""",
    )
    parser.add_argument("jfr_file", help="Path to the .jfr recording file")
    parser.add_argument("--thread", "-t", default=None, help="Filter threads by regex")
    parser.add_argument(
        "--min-duration", type=float, default=0, help="Minimum blocked duration in ms to include (default: 0)"
    )
    parser.add_argument("--stacks", action="store_true", help="Show stack traces for top monitors")
    parser.add_argument("--top", "-n", type=int, default=20, help="Top N entries (default: 20)")
    parser.add_argument("--fqn", action="store_true", help="Fully qualified class names")
    parser.add_argument("--after", default=None, help="Only events after this time")
    parser.add_argument("--before", default=None, help="Only events before this time")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    run(parser.parse_args())


if __name__ == "__main__":
    main()

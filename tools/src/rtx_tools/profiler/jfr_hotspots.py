#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
JFR Hot Method Analysis -- find where CPU/wall time is spent.

Supports self-time (method at top of stack = actually executing) and
total-time (method anywhere in stack = participating in call chain).
Thread filtering, package grouping, and time estimation included.

Usage:
    python -m rtx_tools.profiler.jfr_hotspots profile.jfr
    python -m rtx_tools.profiler.jfr_hotspots profile.jfr -t "^main$" --mode self -n 20
    python -m rtx_tools.profiler.jfr_hotspots profile.jfr -t "Worker" --mode total --group package
    python -m rtx_tools.profiler.jfr_hotspots profile.jfr --wall -t "^main$"
    python -m rtx_tools.profiler.jfr_hotspots profile.jfr --after 15:30 --before 15:35
"""

import argparse
import sys
from collections import defaultdict

from .jfr_parse import (
    _resolve_type_name,
    apply_common_filters,
    event_duration_ms,
    fmt_count,
    fmt_ms,
    fmt_pct,
    get_sampling_period_ms,
    jfr_events,
    json_output,
    print_header,
    stack_frames,
    stack_frames_raw,
)


def collect_self_time(events, simple):
    counts = defaultdict(int)
    for ev in events:
        frames = stack_frames(ev, simple=simple)
        if frames:
            counts[frames[0]] += 1
    return counts


def collect_total_time(events, simple):
    counts = defaultdict(int)
    for ev in events:
        frames = stack_frames(ev, simple=simple)
        seen = set()
        for f in frames:
            if f not in seen:
                counts[f] += 1
                seen.add(f)
    return counts


def collect_package_time(events, mode):
    counts = defaultdict(int)
    for ev in events:
        raw_frames = stack_frames_raw(ev)
        if not raw_frames:
            continue
        targets = [raw_frames[0]] if mode == "self" else raw_frames
        seen = set()
        for f in targets:
            fqn = _resolve_type_name(f.get("method", {}).get("type", "?")).replace("/", ".")
            parts = fqn.split(".")
            pkg = ".".join(parts[: min(3, len(parts) - 1)]) if len(parts) > 1 else fqn
            if pkg not in seen:
                counts[pkg] += 1
                seen.add(pkg)
    return counts


def collect_wall_time(events, simple):
    durations = defaultdict(float)
    counts = defaultdict(int)
    for ev in events:
        dur = event_duration_ms(ev)
        frames = stack_frames(ev, simple=simple)
        if frames:
            leaf = frames[0]
            durations[leaf] += dur
            counts[leaf] += 1
    return durations, counts


def _render_json(rows, period_ms, total):
    """Return the JSON-serialisable dict for --json output.

    *rows* is a list of (method_name, sample_count) pairs, already sorted
    and sliced to top-N.  *period_ms* is the sampling interval.  *total* is
    the total sample count (used to derive totalMs as a proxy).

    Keys match what generate_profile_data.py's build_jfr() reads:
      hotspots[].method, selfMs, totalMs, thread, package
    """
    hotspots = []
    for method, count in rows:
        self_ms = count * period_ms
        # totalMs is not tracked separately in sampling mode; use selfMs as
        # a conservative lower-bound proxy (callers may override when they
        # have richer data).
        hotspots.append(
            {
                "method": method,
                "selfMs": self_ms,
                "totalMs": self_ms,
                "thread": None,
                "package": None,
            }
        )
    return {"hotspots": hotspots}


def run(args):
    jfr = args.jfr_file
    simple = not args.fqn

    if args.wall:
        event_types = ["jdk.ThreadPark", "jdk.JavaMonitorWait", "jdk.ThreadSleep"]
        label = "Wall-Clock (blocked/waiting time)"
    else:
        event_types = ["jdk.ExecutionSample", "jdk.NativeMethodSample"]
        label = "CPU"

    events = jfr_events(jfr, event_types)
    events = apply_common_filters(events, args)

    thread_label = args.thread or "all threads"
    total = len(events)

    if total == 0:
        print(f"No {label} events found for thread filter '{thread_label}'.", file=sys.stderr)
        sys.exit(1)

    title_parts = [label]
    if args.group == "package":
        title_parts.append("by package")
    else:
        title_parts.append(f"{args.mode}-time")
    title_parts.append(f"[{thread_label}]")
    title_parts.append(f"({fmt_count(total)} samples)")
    title = " | ".join(title_parts)

    if args.wall:
        durations, counts = collect_wall_time(events, simple)
        total_ms = sum(durations.values())
        sorted_items = sorted(durations.items(), key=lambda x: x[1], reverse=True)
        top = sorted_items[: args.top]

        if args.json:
            json_output(
                [
                    {"method": m, "total_ms": d, "count": counts[m], "avg_ms": d / counts[m] if counts[m] else 0}
                    for m, d in top
                ]
            )
            return

        print_header(title)
        mw = max((len(m) for m, _ in top), default=40)
        print(f"\n{'#':>4}  {'Method':<{mw}}  {'Total':>10}  {'Count':>8}  {'Avg':>10}  {'%':>6}")
        print(f"{'':>4}  {'':-<{mw}}  {'':->10}  {'':->8}  {'':->10}  {'':->6}")
        for i, (method, dur_ms) in enumerate(top, 1):
            cnt = counts[method]
            avg = dur_ms / cnt if cnt else 0
            print(
                f"{i:>4}  {method:<{mw}}  {fmt_ms(dur_ms):>10}  "
                f"{fmt_count(cnt):>8}  {fmt_ms(avg):>10}  {fmt_pct(dur_ms, total_ms)}"
            )
        print(f"\n  Total blocked/waiting time: {fmt_ms(total_ms)}")
        return

    if args.group == "package":
        counts = collect_package_time(events, args.mode)
    elif args.mode == "self":
        counts = collect_self_time(events, simple)
    else:
        counts = collect_total_time(events, simple)

    period = get_sampling_period_ms(jfr)
    sorted_items = sorted(counts.items(), key=lambda x: x[1], reverse=True)
    top = sorted_items[: args.top]

    if args.json:
        json_output(_render_json(top, period_ms=period, total=total))
        return

    print_header(title)
    mw = max((len(m) for m, _ in top), default=40)
    col_label = "Method" if args.group != "package" else "Package"
    print(f"\n  Sampling period: ~{fmt_ms(period)}")
    print(f"\n{'#':>4}  {col_label:<{mw}}  {'Samples':>10}  {'%':>6}  {'~Time':>10}")
    print(f"{'':>4}  {'':-<{mw}}  {'':->10}  {'':->6}  {'':->10}")

    for i, (method, count) in enumerate(top, 1):
        est_time = count * period
        print(f"{i:>4}  {method:<{mw}}  {fmt_count(count):>10}  {fmt_pct(count, total)}  {fmt_ms(est_time):>10}")

    if len(sorted_items) > args.top:
        remaining = sum(c for _, c in sorted_items[args.top :])
        print(f"\n  ... {len(sorted_items) - args.top} more entries ({fmt_count(remaining)} samples)")

    total_est = total * period
    print(f"\n  Total estimated {label} time: ~{fmt_ms(total_est)}")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Hot method analysis from JFR recordings.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  python -m rtx_tools.profiler.jfr_hotspots profile.jfr                          # CPU self-time, all threads
  python -m rtx_tools.profiler.jfr_hotspots profile.jfr -t "^main$" --mode self  # main thread only
  python -m rtx_tools.profiler.jfr_hotspots profile.jfr --wall -t "^main$"       # wall-clock blocked time
  python -m rtx_tools.profiler.jfr_hotspots profile.jfr --group package           # group by package""",
    )
    parser.add_argument("jfr_file", help="Path to the .jfr recording file")
    parser.add_argument("--thread", "-t", default=None, help="Filter threads by regex")
    parser.add_argument(
        "--mode",
        choices=["self", "total"],
        default="self",
        help="self = top of stack; total = anywhere in stack (default: self)",
    )
    parser.add_argument("--wall", action="store_true", help="Analyze wall-clock blocked/waiting time")
    parser.add_argument(
        "--group", choices=["method", "package"], default="method", help="Group by method (default) or package"
    )
    parser.add_argument("--fqn", action="store_true", help="Fully qualified class names")
    parser.add_argument("--top", "-n", type=int, default=30, help="Top N entries (default: 30)")
    parser.add_argument("--after", default=None, help="Only events after this time")
    parser.add_argument("--before", default=None, help="Only events before this time")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    run(parser.parse_args())


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
JFR I/O Analysis -- file and socket I/O with duration ranking.

Shows the slowest and largest I/O operations, grouped by path or
remote address. Useful for spotting blocking reads, large writes,
or unexpected network traffic.

Usage:
    python -m rtx_tools.profiler.jfr_io profile.jfr
    python -m rtx_tools.profiler.jfr_io profile.jfr --type file
    python -m rtx_tools.profiler.jfr_io profile.jfr --type socket --min-duration 10
    python -m rtx_tools.profiler.jfr_io profile.jfr --by duration -n 50
"""

import argparse
import sys
from collections import defaultdict

from .jfr_parse import (
    apply_common_filters,
    event_duration_ms,
    fmt_bytes,
    fmt_count,
    fmt_ms,
    fmt_pct,
    jfr_events,
    jfr_summary_text,
    json_output,
    parse_summary_events,
    print_header,
    thread_name,
)

FILE_TYPES = ["jdk.FileRead", "jdk.FileWrite", "jdk.FileForce"]
SOCKET_TYPES = ["jdk.SocketRead", "jdk.SocketWrite"]


def _io_target(ev):
    vals = ev.get("values", {})
    path = vals.get("path")
    if path:
        return str(path)
    host = vals.get("host", "")
    port = vals.get("port", "")
    addr = vals.get("address", "")
    if host or addr:
        return f"{host or addr}:{port}"
    return "<unknown>"


def _io_bytes(ev):
    vals = ev.get("values", {})
    return vals.get("bytesRead", vals.get("bytesWritten", vals.get("bytesTransferred", 0)))


def run(args):
    jfr = args.jfr_file
    summary = jfr_summary_text(jfr)
    available = {n for n, _, _ in parse_summary_events(summary)}

    if args.type == "file":
        fetch_types = [t for t in FILE_TYPES if t in available]
    elif args.type == "socket":
        fetch_types = [t for t in SOCKET_TYPES if t in available]
    else:
        fetch_types = [t for t in FILE_TYPES + SOCKET_TYPES if t in available]

    if not fetch_types:
        print(f"No I/O events of type '{args.type}' found.", file=sys.stderr)
        sys.exit(1)

    events = jfr_events(jfr, fetch_types)
    events = apply_common_filters(events, args)

    if args.min_duration > 0:
        events = [ev for ev in events if event_duration_ms(ev) >= args.min_duration]

    if not events:
        print("No I/O events match the filters.", file=sys.stderr)
        sys.exit(1)

    # -- Group by target --
    target_dur = defaultdict(float)
    target_bytes = defaultdict(int)
    target_count = defaultdict(int)
    target_max = defaultdict(float)

    for ev in events:
        tgt = _io_target(ev)
        dur = event_duration_ms(ev)
        b = _io_bytes(ev)
        target_dur[tgt] += dur
        target_bytes[tgt] += b
        target_count[tgt] += 1
        target_max[tgt] = max(target_max[tgt], dur)

    sort_key = target_dur if args.by == "duration" else target_bytes
    sorted_targets = sorted(sort_key.items(), key=lambda x: x[1], reverse=True)
    total_dur = sum(target_dur.values())
    total_b = sum(target_bytes.values())

    if args.json:
        json_output(
            [
                {
                    "target": t,
                    "total_ms": target_dur[t],
                    "bytes": target_bytes[t],
                    "count": target_count[t],
                    "max_ms": target_max[t],
                }
                for t, _ in sorted_targets[: args.top]
            ]
        )
        return

    print_header(f"I/O Analysis ({fmt_count(len(events))} events, {fmt_ms(total_dur)} total, {fmt_bytes(total_b)})")

    tw = max((len(t) for t, _ in sorted_targets[: args.top]), default=30)
    tw = min(tw, 60)
    print(f"\n  {'#':>4}  {'Target':<{tw}}  {'Total':>10}  {'Bytes':>12}  {'Count':>8}  {'Max':>10}  {'%Time':>7}")
    print(f"  {'':>4}  {'':-<{tw}}  {'':->10}  {'':->12}  {'':->8}  {'':->10}  {'':->7}")

    for i, (tgt, _) in enumerate(sorted_targets[: args.top], 1):
        label = tgt if len(tgt) <= tw else "..." + tgt[-(tw - 3) :]
        print(
            f"  {i:>4}  {label:<{tw}}  {fmt_ms(target_dur[tgt]):>10}  "
            f"{fmt_bytes(target_bytes[tgt]):>12}  {target_count[tgt]:>8}  "
            f"{fmt_ms(target_max[tgt]):>10}  {fmt_pct(target_dur[tgt], total_dur)}"
        )

    # -- Top slow individual operations --
    if args.slow:
        sorted_by_dur = sorted(events, key=lambda ev: event_duration_ms(ev), reverse=True)
        print(f"\n  Top {min(10, len(sorted_by_dur))} Slowest Individual I/O Operations:")
        for ev in sorted_by_dur[:10]:
            dur = event_duration_ms(ev)
            tgt = _io_target(ev)
            b = _io_bytes(ev)
            tn = thread_name(ev)
            etype = ev.get("type", "?").rsplit(".", 1)[-1]
            print(f"    {fmt_ms(dur):>10}  {fmt_bytes(b):>10}  {etype:<12}  {tn}  {tgt}")

    print()


def main():
    parser = argparse.ArgumentParser(
        description="I/O analysis from JFR recordings.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  python -m rtx_tools.profiler.jfr_io profile.jfr                        # all I/O
  python -m rtx_tools.profiler.jfr_io profile.jfr --type file             # file I/O only
  python -m rtx_tools.profiler.jfr_io profile.jfr --type socket           # network only
  python -m rtx_tools.profiler.jfr_io profile.jfr --min-duration 10 --slow  # slow operations""",
    )
    parser.add_argument("jfr_file", help="Path to the .jfr recording file")
    parser.add_argument("--thread", "-t", default=None, help="Filter threads by regex")
    parser.add_argument(
        "--type", choices=["file", "socket", "all"], default="all", help="I/O type to analyze (default: all)"
    )
    parser.add_argument(
        "--by",
        choices=["duration", "bytes"],
        default="duration",
        help="Sort targets by total duration or bytes (default: duration)",
    )
    parser.add_argument("--min-duration", type=float, default=0, help="Minimum I/O duration in ms (default: 0)")
    parser.add_argument("--slow", action="store_true", help="Show top slowest individual operations")
    parser.add_argument("--top", "-n", type=int, default=30, help="Top N entries (default: 30)")
    parser.add_argument("--fqn", action="store_true", help="Fully qualified class names")
    parser.add_argument("--after", default=None, help="Only events after this time")
    parser.add_argument("--before", default=None, help="Only events before this time")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    run(parser.parse_args())


if __name__ == "__main__":
    main()

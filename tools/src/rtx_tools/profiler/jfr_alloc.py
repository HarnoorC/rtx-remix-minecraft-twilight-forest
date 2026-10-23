#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
JFR Allocation Analysis -- find what's creating GC pressure.

Shows top allocation sites by total size or count, with stack traces
to pinpoint exactly where objects are created. Thread-filterable.

Usage:
    python -m rtx_tools.profiler.jfr_alloc profile.jfr
    python -m rtx_tools.profiler.jfr_alloc profile.jfr -t "Worker" --by size -n 20
    python -m rtx_tools.profiler.jfr_alloc profile.jfr --class "byte\\[\\]" --stacks
    python -m rtx_tools.profiler.jfr_alloc profile.jfr --top-classes
    python -m rtx_tools.profiler.jfr_alloc profile.jfr --after 15:30 --before 15:35
"""

import argparse
import re
import sys
from collections import defaultdict
from typing import Literal, TypedDict

from .jfr_parse import (
    apply_common_filters,
    fmt_bytes,
    fmt_count,
    fmt_pct,
    jfr_events,
    json_output,
    print_header,
    stack_frames,
    thread_name,
)


class _AllocationSiteStats(TypedDict):
    count: int
    bytes: int
    classes: defaultdict[str, int]


def alloc_class(event):
    """Extract the allocated object class name."""
    oc = event.get("values", {}).get("objectClass")
    if isinstance(oc, dict):
        return oc.get("name", "?").replace("/", ".")
    if isinstance(oc, str):
        return oc
    return "?"


def alloc_weight(event):
    """Extract the allocation weight (bytes)."""
    return event.get("values", {}).get("weight", 0)


def _render_json(sorted_sites, top):
    """Return the JSON-serialisable dict for --json output (allocation sites mode).

    *sorted_sites* is a list of (site, stats_dict) pairs where stats_dict has
    keys 'count', 'bytes', and 'classes' (a dict of {class_name: count}).
    *top* is the maximum number of entries to include.

    Keys match what generate_profile_data.py's build_jfr() reads:
      allocations[].class, site, count, bytes
    """
    allocations = []
    for site, stats in sorted_sites[:top]:
        top_class = max(stats["classes"].items(), key=lambda x: x[1])[0] if stats["classes"] else ""
        allocations.append(
            {
                "class": top_class,
                "site": site,
                "count": stats["count"],
                "bytes": stats["bytes"],
            }
        )
    return {"allocations": allocations}


def run(args):
    jfr = args.jfr_file
    simple = not args.fqn

    events = jfr_events(jfr, ["jdk.ObjectAllocationSample"])
    events = apply_common_filters(events, args)

    if args.alloc_class:
        cls_re = re.compile(args.alloc_class, re.IGNORECASE)
        events = [ev for ev in events if cls_re.search(alloc_class(ev))]

    thread_label = args.thread or "all threads"
    total = len(events)

    if total == 0:
        print(
            f"No allocation samples found for thread '{thread_label}'"
            + (f" matching class '{args.alloc_class}'" if args.alloc_class else ""),
            file=sys.stderr,
        )
        sys.exit(1)

    total_bytes = sum(alloc_weight(ev) for ev in events)

    # -- Top classes mode --
    if args.top_classes:
        class_stats = defaultdict(lambda: {"count": 0, "bytes": 0})
        for ev in events:
            cls = alloc_class(ev)
            w = alloc_weight(ev)
            class_stats[cls]["count"] += 1
            class_stats[cls]["bytes"] += w

        sort_key: Literal["bytes", "count"] = "bytes" if args.by == "size" else "count"
        sorted_classes = sorted(class_stats.items(), key=lambda x: x[1][sort_key], reverse=True)

        if args.json:
            json_output([{"class": c, **s} for c, s in sorted_classes[: args.top]])
            return

        header = f"Allocation by Class | {thread_label} | {fmt_count(total)} samples | {fmt_bytes(total_bytes)} total"
        print_header(header)

        cw = max((len(c) for c, _ in sorted_classes[: args.top]), default=20)
        print(f"\n{'#':>4}  {'Class':<{cw}}  {'Count':>10}  {'Total Size':>12}  {'Avg Size':>10}  {'% Size':>7}")
        print(f"{'':>4}  {'':-<{cw}}  {'':->10}  {'':->12}  {'':->10}  {'':->7}")

        for i, (cls, stats) in enumerate(sorted_classes[: args.top], 1):
            avg = stats["bytes"] / stats["count"] if stats["count"] else 0
            print(
                f"{i:>4}  {cls:<{cw}}  {fmt_count(stats['count']):>10}  "
                f"{fmt_bytes(stats['bytes']):>12}  {fmt_bytes(avg):>10}  "
                f"{fmt_pct(stats['bytes'], total_bytes)}"
            )
        print()
        return

    # -- Top allocation sites --
    site_stats: defaultdict[str, _AllocationSiteStats] = defaultdict(
        lambda: {"count": 0, "bytes": 0, "classes": defaultdict(int)}
    )
    for ev in events:
        frames = stack_frames(ev, simple=simple)
        cls = alloc_class(ev)
        w = alloc_weight(ev)
        site = frames[0] if frames else "<no stack>"
        site_stats[site]["count"] += 1
        site_stats[site]["bytes"] += w
        site_stats[site]["classes"][cls] += 1

    sort_key = "bytes" if args.by == "size" else "count"
    sorted_sites = sorted(site_stats.items(), key=lambda x: x[1][sort_key], reverse=True)

    if args.json:
        json_output(_render_json(sorted_sites, top=args.top))
        return

    header = (
        f"Allocation Sites (by {args.by}) | {thread_label} | "
        f"{fmt_count(total)} samples | {fmt_bytes(total_bytes)} total"
    )
    print_header(header)

    sw = max((len(s) for s, _ in sorted_sites[: args.top]), default=30)
    print(f"\n{'#':>4}  {'Allocation Site':<{sw}}  {'Count':>10}  {'Total Size':>12}  {'Top Class':<25}")
    print(f"{'':>4}  {'':-<{sw}}  {'':->10}  {'':->12}  {'':-<25}")

    for i, (site, stats) in enumerate(sorted_sites[: args.top], 1):
        top_cls = max(stats["classes"].items(), key=lambda x: x[1])
        cls_label = f"{top_cls[0]} ({top_cls[1]})"
        if len(cls_label) > 25:
            cls_label = cls_label[:22] + "..."
        print(
            f"{i:>4}  {site:<{sw}}  {fmt_count(stats['count']):>10}  {fmt_bytes(stats['bytes']):>12}  {cls_label:<25}"
        )

    # -- Stack detail for top sites --
    if args.stacks:
        detail_count = min(args.stack_depth, len(sorted_sites))
        print(f"\n{'--- Stack Details (top ' + str(detail_count) + ' sites) ---':^80}")
        for i, (site, stats) in enumerate(sorted_sites[: args.stack_depth], 1):
            print(f"\n  #{i} {site}  [{fmt_count(stats['count'])} allocs, {fmt_bytes(stats['bytes'])}]")
            for cls, cnt in sorted(stats["classes"].items(), key=lambda x: x[1], reverse=True)[:5]:
                print(f"    Class: {cls} ({fmt_count(cnt)} times)")

            for ev in events:
                frames = stack_frames(ev, simple=simple)
                if frames and frames[0] == site:
                    print("    Example stack (top 10):")
                    for j, f in enumerate(frames[:10]):
                        print(f"      {'>' if j == 0 else ' '} {f}")
                    break

    # -- Per-thread breakdown --
    if args.thread is None and total > 100:
        thread_bytes = defaultdict(int)
        thread_counts = defaultdict(int)
        for ev in events:
            tn = thread_name(ev)
            thread_bytes[tn] += alloc_weight(ev)
            thread_counts[tn] += 1

        sorted_threads = sorted(thread_bytes.items(), key=lambda x: x[1], reverse=True)
        print("\n  Per-Thread Allocation Breakdown:")
        tw = max((len(n) for n, _ in sorted_threads[:10]), default=20)
        for tn, tb in sorted_threads[:10]:
            tc = thread_counts[tn]
            print(f"    {tn:<{tw}}  {fmt_count(tc):>8} allocs  {fmt_bytes(tb):>12}  {fmt_pct(tb, total_bytes)}")
        if len(sorted_threads) > 10:
            print(f"    ... {len(sorted_threads) - 10} more threads")

    print()


def main():
    parser = argparse.ArgumentParser(
        description="Allocation profiling from JFR recordings.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  python -m rtx_tools.profiler.jfr_alloc profile.jfr                           # top allocation sites by count
  python -m rtx_tools.profiler.jfr_alloc profile.jfr --by size -n 20           # by total size
  python -m rtx_tools.profiler.jfr_alloc profile.jfr --top-classes              # group by allocated class
  python -m rtx_tools.profiler.jfr_alloc profile.jfr -t "Worker" --stacks      # workers with stack detail
  python -m rtx_tools.profiler.jfr_alloc profile.jfr --after 15:30 --json       # JSON output for a time window""",
    )
    parser.add_argument("jfr_file", help="Path to the .jfr recording file")
    parser.add_argument("--thread", "-t", default=None, help="Filter threads by regex")
    parser.add_argument(
        "--by",
        choices=["count", "size"],
        default="count",
        help="Sort by sample count or total allocation size (default: count)",
    )
    parser.add_argument(
        "--top-classes", action="store_true", help="Group by allocated class instead of allocation site"
    )
    parser.add_argument("--class", dest="alloc_class", default=None, help="Filter by allocated class (regex)")
    parser.add_argument("--stacks", action="store_true", help="Show example stack traces for top sites")
    parser.add_argument("--stack-depth", type=int, default=5, help="Number of sites to show stacks for (default: 5)")
    parser.add_argument("--fqn", action="store_true", help="Fully qualified class names")
    parser.add_argument("--top", "-n", type=int, default=30, help="Top N entries (default: 30)")
    parser.add_argument("--after", default=None, help="Only events after this time (HH:MM or ISO)")
    parser.add_argument("--before", default=None, help="Only events before this time (HH:MM or ISO)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    run(parser.parse_args())


if __name__ == "__main__":
    main()

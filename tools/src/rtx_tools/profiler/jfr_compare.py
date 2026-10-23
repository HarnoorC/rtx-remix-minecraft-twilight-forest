#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
JFR Compare -- diff two recordings side-by-side.

The killer feature VisualVM can't do. Compare before/after optimization:
allocation deltas, CPU hotspot changes, GC pressure differences, and
per-thread allocation shifts.

Usage:
    python -m rtx_tools.profiler.jfr_compare before.jfr after.jfr
    python -m rtx_tools.profiler.jfr_compare before.jfr after.jfr --mode alloc
    python -m rtx_tools.profiler.jfr_compare before.jfr after.jfr --mode cpu
    python -m rtx_tools.profiler.jfr_compare before.jfr after.jfr --mode gc
    python -m rtx_tools.profiler.jfr_compare before.jfr after.jfr -t "^main$"
"""

import argparse
from collections import defaultdict

from .jfr_parse import (
    compile_thread_filter,
    event_duration_ms,
    fmt_bytes,
    fmt_count,
    fmt_delta,
    fmt_ms,
    jfr_events,
    jfr_summary_text,
    json_output,
    matches_thread,
    parse_summary_events,
    parse_summary_meta,
    print_header,
    stack_frames,
)


def _alloc_weight(ev):
    return ev.get("values", {}).get("weight", 0)


def compare_alloc(before_jfr, after_jfr, thread_re, simple, top_n, as_json):
    """Compare allocation hotspots between two recordings."""

    def gather(jfr):
        events = jfr_events(jfr, ["jdk.ObjectAllocationSample"])
        if thread_re:
            events = [ev for ev in events if matches_thread(ev, thread_re)]
        site_count = defaultdict(int)
        site_bytes = defaultdict(int)
        for ev in events:
            frames = stack_frames(ev, simple=simple)
            site = frames[0] if frames else "<no stack>"
            site_count[site] += 1
            site_bytes[site] += _alloc_weight(ev)
        return site_count, site_bytes, len(events), sum(site_bytes.values())

    b_cnt, b_bytes, b_total, b_total_bytes = gather(before_jfr)
    a_cnt, a_bytes, a_total, a_total_bytes = gather(after_jfr)

    all_sites = sorted(
        set(b_bytes) | set(a_bytes),
        key=lambda s: max(b_bytes.get(s, 0), a_bytes.get(s, 0)),
        reverse=True,
    )

    if as_json:
        rows = []
        for site in all_sites[:top_n]:
            rows.append(
                {
                    "site": site,
                    "before_count": b_cnt.get(site, 0),
                    "after_count": a_cnt.get(site, 0),
                    "before_bytes": b_bytes.get(site, 0),
                    "after_bytes": a_bytes.get(site, 0),
                }
            )
        json_output({"total_before": b_total_bytes, "total_after": a_total_bytes, "sites": rows})
        return

    print_header(
        f"Allocation Delta ({fmt_count(b_total)} -> {fmt_count(a_total)} samples, "
        f"{fmt_bytes(b_total_bytes)} -> {fmt_bytes(a_total_bytes)})"
    )
    print(f"  Total: {fmt_delta(b_total_bytes, a_total_bytes)}")

    sw = max((len(s) for s in all_sites[:top_n]), default=30)
    print(f"\n  {'Site':<{sw}}  {'Before':>12}  {'After':>12}  {'Delta':>12}")
    print(f"  {'':-<{sw}}  {'':->12}  {'':->12}  {'':->12}")

    for site in all_sites[:top_n]:
        bb = b_bytes.get(site, 0)
        ab = a_bytes.get(site, 0)
        if bb == 0 and ab == 0:
            continue
        print(f"  {site:<{sw}}  {fmt_bytes(bb):>12}  {fmt_bytes(ab):>12}  {fmt_delta(bb, ab):>12}")


def compare_cpu(before_jfr, after_jfr, thread_re, simple, top_n, as_json):
    """Compare CPU hotspots between two recordings."""

    def gather(jfr):
        events = jfr_events(jfr, ["jdk.ExecutionSample", "jdk.NativeMethodSample"])
        if thread_re:
            events = [ev for ev in events if matches_thread(ev, thread_re)]
        counts = defaultdict(int)
        for ev in events:
            frames = stack_frames(ev, simple=simple)
            if frames:
                counts[frames[0]] += 1
        return counts, len(events)

    b_counts, b_total = gather(before_jfr)
    a_counts, a_total = gather(after_jfr)

    all_methods = sorted(
        set(b_counts) | set(a_counts),
        key=lambda m: max(b_counts.get(m, 0), a_counts.get(m, 0)),
        reverse=True,
    )

    if as_json:
        rows = [{"method": m, "before": b_counts.get(m, 0), "after": a_counts.get(m, 0)} for m in all_methods[:top_n]]
        json_output({"total_before": b_total, "total_after": a_total, "methods": rows})
        return

    print_header(f"CPU Hotspot Delta ({fmt_count(b_total)} -> {fmt_count(a_total)} samples)")

    mw = max((len(m) for m in all_methods[:top_n]), default=30)
    print(f"\n  {'Method':<{mw}}  {'Before':>10}  {'After':>10}  {'Delta':>12}")
    print(f"  {'':-<{mw}}  {'':->10}  {'':->10}  {'':->12}")

    for m in all_methods[:top_n]:
        bc = b_counts.get(m, 0)
        ac = a_counts.get(m, 0)
        if bc == 0 and ac == 0:
            continue
        print(f"  {m:<{mw}}  {bc:>10}  {ac:>10}  {fmt_delta(bc, ac):>12}")


def compare_gc(before_jfr, after_jfr, as_json):
    """Compare GC stats between two recordings."""

    def gather(jfr):
        summary = jfr_summary_text(jfr)
        meta = parse_summary_meta(summary)
        available = {n for n, _, _ in parse_summary_events(summary)}
        gc_types = [t for t in ("jdk.GCPhasePause", "jdk.GarbageCollection") if t in available]
        gc_events = jfr_events(jfr, gc_types) if gc_types else []
        durs = [event_duration_ms(ev) for ev in gc_events]

        heap_events = jfr_events(jfr, ["jdk.GCHeapSummary"]) if "jdk.GCHeapSummary" in available else []
        heap_used = heap_events[-1].get("values", {}).get("heapUsed", 0) if heap_events else 0

        return {
            "gc_count": len(durs),
            "gc_total_ms": sum(durs) if durs else 0,
            "gc_max_ms": max(durs) if durs else 0,
            "heap_used": heap_used,
            "duration": meta.get("duration", "?"),
        }

    b = gather(before_jfr)
    a = gather(after_jfr)

    if as_json:
        json_output({"before": b, "after": a})
        return

    print_header("GC Delta")
    print(f"\n  {'Metric':<25}  {'Before':>15}  {'After':>15}  {'Delta':>12}")
    print(f"  {'':-<25}  {'':->15}  {'':->15}  {'':->12}")

    rows = [
        ("Duration", b["duration"], a["duration"], ""),
        ("GC events", str(b["gc_count"]), str(a["gc_count"]), fmt_delta(b["gc_count"], a["gc_count"])),
        (
            "Total GC pause",
            fmt_ms(b["gc_total_ms"]),
            fmt_ms(a["gc_total_ms"]),
            fmt_delta(b["gc_total_ms"], a["gc_total_ms"]),
        ),
        ("Max GC pause", fmt_ms(b["gc_max_ms"]), fmt_ms(a["gc_max_ms"]), fmt_delta(b["gc_max_ms"], a["gc_max_ms"])),
        (
            "Last heap used",
            fmt_bytes(b["heap_used"]),
            fmt_bytes(a["heap_used"]),
            fmt_delta(b["heap_used"], a["heap_used"]),
        ),
    ]
    for label, bv, av, delta in rows:
        print(f"  {label:<25}  {bv:>15}  {av:>15}  {delta:>12}")


def run(args):
    simple = not args.fqn
    thread_re = compile_thread_filter(args.thread)
    top_n = args.top
    show_all = args.mode == "all"

    if show_all or args.mode == "alloc":
        compare_alloc(args.before_jfr, args.after_jfr, thread_re, simple, top_n, args.json)
    if show_all or args.mode == "cpu":
        compare_cpu(args.before_jfr, args.after_jfr, thread_re, simple, top_n, args.json)
    if show_all or args.mode == "gc":
        compare_gc(args.before_jfr, args.after_jfr, args.json)
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Compare two JFR recordings side-by-side.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  python -m rtx_tools.profiler.jfr_compare before.jfr after.jfr               # everything
  python -m rtx_tools.profiler.jfr_compare before.jfr after.jfr --mode alloc  # allocations only
  python -m rtx_tools.profiler.jfr_compare before.jfr after.jfr --mode cpu    # CPU hotspots only
  python -m rtx_tools.profiler.jfr_compare before.jfr after.jfr -t "^main$"   # main thread only""",
    )
    parser.add_argument("before_jfr", help="Path to the BEFORE .jfr recording")
    parser.add_argument("after_jfr", help="Path to the AFTER .jfr recording")
    parser.add_argument(
        "--mode", choices=["all", "alloc", "cpu", "gc"], default="all", help="Comparison mode (default: all)"
    )
    parser.add_argument("--thread", "-t", default=None, help="Filter threads by regex")
    parser.add_argument("--fqn", action="store_true", help="Fully qualified class names")
    parser.add_argument("--top", "-n", type=int, default=30, help="Top N entries (default: 30)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    run(parser.parse_args())


if __name__ == "__main__":
    main()

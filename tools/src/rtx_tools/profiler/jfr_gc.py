#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
JFR GC and Memory Analysis -- heap, RSS, GC pauses, retained objects.

Consolidates heap, RSS, GC pause, retained object, and per-thread
allocation analysis into a single tool. VisualVM shows you a graph;
this tells you the numbers behind it.

Usage:
    python -m rtx_tools.profiler.jfr_gc profile.jfr                    # everything
    python -m rtx_tools.profiler.jfr_gc profile.jfr --heap              # heap timeline only
    python -m rtx_tools.profiler.jfr_gc profile.jfr --rss               # RSS tracking
    python -m rtx_tools.profiler.jfr_gc profile.jfr --gc                # GC pause breakdown
    python -m rtx_tools.profiler.jfr_gc profile.jfr --retained          # old object samples
    python -m rtx_tools.profiler.jfr_gc profile.jfr --thread-alloc      # per-thread allocation ranking
"""

import argparse
import sys
from collections import defaultdict
from datetime import datetime
from typing import TypedDict

from .jfr_parse import (
    event_duration_ms,
    event_timestamp_ms,
    filter_by_time,
    fmt_bytes,
    fmt_count,
    fmt_ms,
    fmt_pct,
    jfr_events,
    jfr_summary_text,
    json_output,
    parse_iso_duration,
    parse_summary_events,
    parse_time_arg,
    print_header,
    stack_frames,
    thread_name,
)


class _RetainedObjectStats(TypedDict):
    count: int
    total_size: int
    stacks: list[list[str]]


def _ts_label(ms):
    if ms <= 0:
        return "?"
    return datetime.fromtimestamp(ms / 1000.0).strftime("%H:%M:%S")


def _apply_time_window(events, args):
    after_ms = parse_time_arg(getattr(args, "after", None), reference_events=events)
    before_ms = parse_time_arg(getattr(args, "before", None), reference_events=events)
    return filter_by_time(events, after_ms, before_ms)


def _gc_pause_event_types(available):
    if "jdk.GCPhasePause" in available:
        return ["jdk.GCPhasePause"]
    if "jdk.GarbageCollection" in available:
        return ["jdk.GarbageCollection"]
    return []


def _gc_pause_duration_ms(event):
    vals = event.get("values", {})
    if event.get("type") == "jdk.GarbageCollection":
        pause = vals.get("sumOfPauses") or vals.get("longestPause")
        if pause is not None:
            return parse_iso_duration(pause)
    return event_duration_ms(event)


def show_heap(jfr, args):
    events = jfr_events(jfr, ["jdk.GCHeapSummary"])
    events = _apply_time_window(events, args)
    if not events:
        print("  No GCHeapSummary events found.", file=sys.stderr)
        return

    print_header("Heap Timeline (GCHeapSummary)")
    print(f"\n  {'Time':>10}  {'When':>8}  {'Used':>10}  {'Committed':>12}  {'Reserved':>12}")
    print(f"  {'':->10}  {'':->8}  {'':->10}  {'':->12}  {'':->12}")

    first_used = last_used = 0
    for ev in events:
        vals = ev.get("values", {})
        ts = event_timestamp_ms(ev)
        when = vals.get("when", "?")
        used = vals.get("heapUsed", 0)
        hs = vals.get("heapSpace", {})
        committed = hs.get("committedSize", 0) if isinstance(hs, dict) else 0
        reserved = hs.get("reservedSize", 0) if isinstance(hs, dict) else 0

        if not first_used:
            first_used = used
        last_used = used

        print(
            f"  {_ts_label(ts):>10}  {when:>8}  {fmt_bytes(used):>10}  "
            f"{fmt_bytes(committed):>12}  {fmt_bytes(reserved):>12}"
        )

    if first_used and last_used:
        delta = last_used - first_used
        direction = "grew" if delta > 0 else "shrunk"
        print(f"\n  Heap {direction} by {fmt_bytes(abs(delta))} over recording")


def show_rss(jfr, args):
    events = jfr_events(jfr, ["jdk.PhysicalMemory"])
    events = _apply_time_window(events, args)
    if not events:
        print("  No PhysicalMemory events found.", file=sys.stderr)
        return

    print_header("RSS / Physical Memory Timeline")
    print(f"\n  {'Time':>10}  {'Used':>12}  {'Total':>12}")
    print(f"  {'':->10}  {'':->12}  {'':->12}")

    first_used = last_used = 0
    for ev in events:
        vals = ev.get("values", {})
        ts = event_timestamp_ms(ev)
        used = vals.get("usedSize", 0)
        total = vals.get("totalSize", 0)
        if not first_used and used:
            first_used = used
        if used:
            last_used = used
        print(f"  {_ts_label(ts):>10}  {fmt_bytes(used):>12}  {fmt_bytes(total):>12}")

    if first_used and last_used:
        print(
            f"\n  RSS start: {fmt_bytes(first_used)}, end: {fmt_bytes(last_used)}, "
            f"delta: {fmt_bytes(last_used - first_used)}"
        )


def show_gc(jfr, args):
    summary = jfr_summary_text(jfr)
    available = {n for n, _, _ in parse_summary_events(summary)}

    pause_types = _gc_pause_event_types(available)
    if not pause_types:
        print("  No GC pause events found.", file=sys.stderr)
        return

    events = jfr_events(jfr, pause_types)
    events = _apply_time_window(events, args)
    if not events:
        return

    print_header("GC Pause Analysis")

    by_cause = defaultdict(list)
    for ev in events:
        vals = ev.get("values", {})
        cause = vals.get("cause", vals.get("name", ev.get("type", "unknown")))
        dur = _gc_pause_duration_ms(ev)
        by_cause[cause].append(dur)

    total_pause = sum(d for durs in by_cause.values() for d in durs)
    total_count = sum(len(durs) for durs in by_cause.values())

    print(f"\n  Total GC events: {fmt_count(total_count)}")
    print(f"  Total pause time: {fmt_ms(total_pause)}")
    print()

    cw = max((len(c) for c in by_cause), default=20)
    print(f"  {'Cause':<{cw}}  {'Count':>8}  {'Total':>10}  {'Max':>10}  {'Avg':>10}")
    print(f"  {'':-<{cw}}  {'':->8}  {'':->10}  {'':->10}  {'':->10}")

    for cause, durs in sorted(by_cause.items(), key=lambda x: sum(x[1]), reverse=True):
        total = sum(durs)
        print(
            f"  {cause:<{cw}}  {len(durs):>8}  {fmt_ms(total):>10}  "
            f"{fmt_ms(max(durs)):>10}  {fmt_ms(total / len(durs)):>10}"
        )


def show_retained(jfr, args):
    events = jfr_events(jfr, ["jdk.OldObjectSample"])
    events = _apply_time_window(events, args)
    if not events:
        print("  No OldObjectSample events found.", file=sys.stderr)
        return

    print_header(f"Retained Objects ({len(events)} samples)")

    by_type: defaultdict[str, _RetainedObjectStats] = defaultdict(lambda: {"count": 0, "total_size": 0, "stacks": []})
    for ev in events:
        vals = ev.get("values", {})
        obj_type = vals.get("objectClass")
        if isinstance(obj_type, dict):
            name = obj_type.get("name", "?").replace("/", ".")
        else:
            name = str(obj_type)
        size = vals.get("objectSize", vals.get("allocationSize", 0))
        by_type[name]["count"] += 1
        by_type[name]["total_size"] += size
        frames = stack_frames(ev, simple=True)
        if frames and len(by_type[name]["stacks"]) < 3:
            by_type[name]["stacks"].append(frames[:5])

    sorted_types = sorted(by_type.items(), key=lambda x: x[1]["total_size"], reverse=True)

    tw = max((len(t) for t, _ in sorted_types[:20]), default=30)
    print(f"\n  {'#':>4}  {'Type':<{tw}}  {'Count':>8}  {'Total Size':>12}")
    print(f"  {'':>4}  {'':-<{tw}}  {'':->8}  {'':->12}")

    for i, (type_name, info) in enumerate(sorted_types[:20], 1):
        print(f"  {i:>4}  {type_name:<{tw}}  {info['count']:>8}  {fmt_bytes(info['total_size']):>12}")
        for stack in info["stacks"][:1]:
            print(f"         Alloc: {' <- '.join(stack[:3])}")


def show_thread_alloc(jfr, args):
    events = jfr_events(jfr, ["jdk.ObjectAllocationSample"])
    events = _apply_time_window(events, args)
    if not events:
        print("  No allocation samples found.", file=sys.stderr)
        return

    print_header("Per-Thread Allocation Ranking")

    thread_bytes = defaultdict(int)
    thread_counts = defaultdict(int)
    for ev in events:
        tn = thread_name(ev)
        w = ev.get("values", {}).get("weight", 0)
        thread_bytes[tn] += w
        thread_counts[tn] += 1

    total_bytes = sum(thread_bytes.values())
    sorted_threads = sorted(thread_bytes.items(), key=lambda x: x[1], reverse=True)

    tw = max((len(n) for n, _ in sorted_threads[:30]), default=20)
    print(f"\n  {'#':>4}  {'Thread':<{tw}}  {'Samples':>10}  {'Total Size':>12}  {'%':>7}")
    print(f"  {'':>4}  {'':-<{tw}}  {'':->10}  {'':->12}  {'':->7}")

    for i, (tn, tb) in enumerate(sorted_threads[:30], 1):
        print(
            f"  {i:>4}  {tn:<{tw}}  {fmt_count(thread_counts[tn]):>10}  {fmt_bytes(tb):>12}  {fmt_pct(tb, total_bytes)}"
        )

    if len(sorted_threads) > 30:
        print(f"\n  ... {len(sorted_threads) - 30} more threads")
    print()


def _render_json(gc_events, duration_sec):
    """Return the JSON-serialisable dict for --json output.

    *gc_events* is a list of (cause, duration_ms, timestamp_ms) tuples derived
    from jdk.GCPhasePause / jdk.GarbageCollection events.
    *duration_sec* is the total recording duration used to compute rate.

    Keys match what generate_profile_data.py's build_jfr() reads:
      pauseCountPerSec, p99PauseMs, totalPauseMs, events[].{cause, durationMs}
    """
    if not gc_events:
        return {"pauseCountPerSec": 0.0, "p99PauseMs": 0.0, "totalPauseMs": 0.0, "events": []}

    durations = [dur for _, dur, _ in gc_events]
    total_pause = sum(durations)
    count = len(durations)
    rate = count / duration_sec if duration_sec > 0 else 0.0

    sorted_durs = sorted(durations)
    p99_idx = max(0, int(len(sorted_durs) * 0.99) - 1) if len(sorted_durs) > 1 else 0
    p99 = sorted_durs[p99_idx] if sorted_durs else 0.0
    # For small N, p99 of a handful of samples is just the max
    if len(sorted_durs) <= 10:
        p99 = sorted_durs[-1]

    events_out = [{"cause": cause, "durationMs": dur} for cause, dur, _ in gc_events]
    return {
        "pauseCountPerSec": round(rate, 4),
        "p99PauseMs": p99,
        "totalPauseMs": total_pause,
        "events": events_out,
    }


def run(args):
    jfr = args.jfr_file
    show_all = not any([args.heap, args.rss, args.gc, args.retained, args.thread_alloc])

    if args.json:
        summary = jfr_summary_text(jfr)
        available = {n for n, _, _ in parse_summary_events(summary)}
        pause_types = _gc_pause_event_types(available)
        gc_evts = jfr_events(jfr, pause_types) if pause_types else []
        gc_evts = _apply_time_window(gc_evts, args)

        # Derive recording duration from first/last timestamp across all GC events
        from .jfr_parse import event_timestamp_ms as _ts_ms

        timestamps = [_ts_ms(ev) for ev in gc_evts if _ts_ms(ev) > 0]
        if len(timestamps) >= 2:
            duration_sec = (max(timestamps) - min(timestamps)) / 1000.0
        else:
            duration_sec = 0.0

        rows = [
            (
                ev.get("values", {}).get("cause", ev.get("values", {}).get("name", ev.get("type", "unknown"))),
                _gc_pause_duration_ms(ev),
                _ts_ms(ev),
            )
            for ev in gc_evts
        ]
        json_output(_render_json(rows, duration_sec=duration_sec))
        return

    if show_all or args.heap:
        show_heap(jfr, args)
    if show_all or args.rss:
        show_rss(jfr, args)
    if show_all or args.gc:
        show_gc(jfr, args)
    if show_all or args.retained:
        show_retained(jfr, args)
    if show_all or args.thread_alloc:
        show_thread_alloc(jfr, args)
    print()


def main():
    parser = argparse.ArgumentParser(
        description="GC and memory analysis from JFR recordings.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  python -m rtx_tools.profiler.jfr_gc profile.jfr                # full report
  python -m rtx_tools.profiler.jfr_gc profile.jfr --heap         # heap timeline
  python -m rtx_tools.profiler.jfr_gc profile.jfr --rss          # RSS / native memory
  python -m rtx_tools.profiler.jfr_gc profile.jfr --gc           # GC pause breakdown
  python -m rtx_tools.profiler.jfr_gc profile.jfr --retained     # retained (leaked?) objects
  python -m rtx_tools.profiler.jfr_gc profile.jfr --thread-alloc # who allocates most""",
    )
    parser.add_argument("jfr_file", help="Path to the .jfr recording file")
    parser.add_argument("--heap", action="store_true", help="Heap timeline")
    parser.add_argument("--rss", action="store_true", help="RSS / physical memory tracking")
    parser.add_argument("--gc", action="store_true", help="GC pause analysis")
    parser.add_argument("--retained", action="store_true", help="Retained object analysis")
    parser.add_argument("--thread-alloc", action="store_true", help="Per-thread allocation ranking")
    parser.add_argument("--after", default=None, help="Only events after this time")
    parser.add_argument("--before", default=None, help="Only events before this time")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    run(parser.parse_args())


if __name__ == "__main__":
    main()

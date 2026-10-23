#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
JFR Recording Summary -- the "start here" dashboard for any recording.

Gives an LLM (or human) enough context in one call to decide where to
drill down next: metadata, event counts, CPU thread breakdown, top
allocation sites, heap/RSS snapshots, GC stats, and contended locks.

Usage:
    python -m rtx_tools.profiler.jfr_summary profile.jfr
    python -m rtx_tools.profiler.jfr_summary profile.jfr --threads
    python -m rtx_tools.profiler.jfr_summary profile.jfr --json
"""

import argparse
from collections import defaultdict
from pathlib import Path

from .jfr_parse import (
    event_duration_ms,
    fmt_bytes,
    fmt_count,
    fmt_ms,
    fmt_pct,
    get_sampling_period_ms,
    jfr_events,
    jfr_summary_text,
    json_output,
    parse_iso_duration,
    parse_summary_events,
    parse_summary_meta,
    print_header,
    stack_frames,
    thread_name,
)


def _alloc_weight(event):
    return event.get("values", {}).get("weight", 0)


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


def run(args):
    jfr = args.jfr_file
    out = {}

    # -- Recording metadata --
    summary = jfr_summary_text(jfr)
    meta = parse_summary_meta(summary)
    events_list = parse_summary_events(summary)
    available = {name for name, _, _ in events_list}

    if args.json:
        out["file"] = Path(jfr).name
        out["meta"] = meta
    else:
        print_header("JFR Recording Summary")
        print(f"  File     : {Path(jfr).name}")
        print(f"  Duration : {meta.get('duration', '?')}")
        print(f"  Start    : {meta.get('start', '?')}")
        print(f"  Chunks   : {meta.get('chunks', '?')}")

    # -- Event counts --
    total_events = sum(c for _, c, _ in events_list)
    if args.json:
        out["events"] = {n: {"count": c, "size": s} for n, c, s in events_list}
    else:
        print_header("Event Counts")
        nw = max((len(n) for n, _, _ in events_list), default=30)
        for name, count, size in events_list:
            print(f"  {name:<{nw}}  {fmt_count(count):>10}  {fmt_pct(count, total_events)}  ({fmt_bytes(size)})")
        print(f"  {'TOTAL':<{nw}}  {fmt_count(total_events):>10}")

    # -- CPU thread breakdown --
    sample_types = [t for t in ("jdk.ExecutionSample", "jdk.NativeMethodSample") if t in available]
    if sample_types:
        samples = jfr_events(jfr, sample_types)
        period = get_sampling_period_ms(jfr)

        thread_counts = defaultdict(int)
        for ev in samples:
            thread_counts[thread_name(ev)] += 1

        total_samples = sum(thread_counts.values())
        sorted_threads = sorted(thread_counts.items(), key=lambda x: x[1], reverse=True)

        if args.json:
            out["cpu_threads"] = {n: c for n, c in sorted_threads}
            out["sampling_period_ms"] = period
        else:
            print_header(f"Threads by CPU Samples (period ~{fmt_ms(period)}, {fmt_count(total_samples)} total)")
            tw = max((len(n) for n, _ in sorted_threads), default=20)
            shown = sorted_threads if args.threads else sorted_threads[:15]
            for name, count in shown:
                est = count * period
                print(f"  {name:<{tw}}  {fmt_count(count):>8} samples  {fmt_pct(count, total_samples)}  ~{fmt_ms(est)}")
            if not args.threads and len(sorted_threads) > 15:
                remaining = sum(c for _, c in sorted_threads[15:])
                print(
                    f"  ... {len(sorted_threads) - 15} more threads ({fmt_count(remaining)} samples). "
                    "Use --threads to show all."
                )

    # -- Top 5 allocation sites (quick peek) --
    if "jdk.ObjectAllocationSample" in available:
        alloc_events = jfr_events(jfr, ["jdk.ObjectAllocationSample"])
        if alloc_events:
            site_bytes = defaultdict(int)
            for ev in alloc_events:
                frames = stack_frames(ev, simple=True)
                site = frames[0] if frames else "<no stack>"
                site_bytes[site] += _alloc_weight(ev)
            top5 = sorted(site_bytes.items(), key=lambda x: x[1], reverse=True)[:5]
            total_alloc = sum(site_bytes.values())

            if args.json:
                out["top_alloc_sites"] = [{"site": s, "bytes": b} for s, b in top5]
            else:
                print_header("Top 5 Allocation Sites (quick peek)")
                sw = max((len(s) for s, _ in top5), default=30)
                for i, (site, b) in enumerate(top5, 1):
                    print(f"  {i}. {site:<{sw}}  {fmt_bytes(b):>10}  {fmt_pct(b, total_alloc)}")

    # -- Heap / RSS snapshot --
    if "jdk.GCHeapSummary" in available:
        heap_evts = jfr_events(jfr, ["jdk.GCHeapSummary"])
        if heap_evts:
            last = heap_evts[-1]
            vals = last.get("values", {})
            used = vals.get("heapUsed", 0)
            committed = 0
            hs = vals.get("heapSpace")
            if isinstance(hs, dict):
                committed = hs.get("committedSize", 0)
            if args.json:
                out["heap_last"] = {"used": used, "committed": committed}
            else:
                print_header("Heap (last GC event)")
                print(f"  Used      : {fmt_bytes(used)}")
                print(f"  Committed : {fmt_bytes(committed)}")

    if "jdk.PhysicalMemory" in available:
        rss_evts = jfr_events(jfr, ["jdk.PhysicalMemory"])
        if rss_evts:
            first_total = rss_evts[0].get("values", {}).get("totalSize", 0)
            last_used = rss_evts[-1].get("values", {}).get("usedSize", 0)
            if args.json:
                out["rss"] = {"total": first_total, "used_last": last_used}
            elif last_used:
                print(f"  RSS (last): {fmt_bytes(last_used)}")

    # -- GC stats --
    gc_types = _gc_pause_event_types(available)
    if gc_types:
        gc_events = jfr_events(jfr, gc_types)
        if gc_events:
            durations = [_gc_pause_duration_ms(ev) for ev in gc_events]
            total_gc = sum(durations)
            if args.json:
                out["gc"] = {
                    "count": len(durations),
                    "total_ms": total_gc,
                    "max_ms": max(durations),
                    "avg_ms": total_gc / len(durations),
                }
            else:
                print_header(f"GC Pauses ({len(durations)} events)")
                print(f"  Total pause : {fmt_ms(total_gc)}")
                print(f"  Max pause   : {fmt_ms(max(durations))}")
                print(f"  Avg pause   : {fmt_ms(total_gc / len(durations))}")

    # -- Top 3 contended locks (quick peek) --
    if "jdk.JavaMonitorEnter" in available:
        lock_events = jfr_events(jfr, ["jdk.JavaMonitorEnter"])
        if lock_events:
            monitor_time = defaultdict(float)
            monitor_count = defaultdict(int)
            for ev in lock_events:
                mc = ev.get("values", {}).get("monitorClass")
                name = mc.get("name", "?").replace("/", ".") if isinstance(mc, dict) else str(mc)
                dur = event_duration_ms(ev)
                monitor_time[name] += dur
                monitor_count[name] += 1
            top3 = sorted(monitor_time.items(), key=lambda x: x[1], reverse=True)[:3]
            if top3 and top3[0][1] > 0:
                if args.json:
                    out["top_locks"] = [{"class": c, "total_ms": t, "count": monitor_count[c]} for c, t in top3]
                else:
                    print_header("Top 3 Contended Locks (quick peek)")
                    for i, (cls, total) in enumerate(top3, 1):
                        print(f"  {i}. {cls}  {fmt_ms(total)} total  ({monitor_count[cls]} events)")

    # -- CPU load --
    if "jdk.CPULoad" in available and not args.json:
        cpu_events = jfr_events(jfr, ["jdk.CPULoad"])
        if cpu_events:
            jvm_user = [ev["values"]["jvmUser"] for ev in cpu_events if "jvmUser" in ev.get("values", {})]
            jvm_sys = [ev["values"]["jvmSystem"] for ev in cpu_events if "jvmSystem" in ev.get("values", {})]
            machine = [ev["values"]["machineTotal"] for ev in cpu_events if "machineTotal" in ev.get("values", {})]
            print_header("CPU Load (averages over recording)")
            if jvm_user:
                print(f"  JVM User   : {sum(jvm_user) / len(jvm_user) * 100:.1f}%")
            if jvm_sys:
                print(f"  JVM System : {sum(jvm_sys) / len(jvm_sys) * 100:.1f}%")
            if machine:
                print(f"  Machine    : {sum(machine) / len(machine) * 100:.1f}%")

    if args.json:
        json_output(out)
    else:
        print()


def main():
    parser = argparse.ArgumentParser(
        description="Quick dashboard overview of a JFR recording.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Example: python -m rtx_tools.profiler.jfr_summary profile.jfr --threads",
    )
    parser.add_argument("jfr_file", help="Path to the .jfr recording file")
    parser.add_argument("--threads", action="store_true", help="Show all threads (default: top 15)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    run(parser.parse_args())


if __name__ == "__main__":
    main()

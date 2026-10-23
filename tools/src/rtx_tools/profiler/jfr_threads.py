#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
JFR Thread State Analysis -- inventory, CPU load, stuck detection.

Goes beyond VisualVM's thread timeline by detecting "dark" threads
(running in native code, invisible to JFR sampling) and providing
quantitative park/wait analysis.

Usage:
    python -m rtx_tools.profiler.jfr_threads profile.jfr
    python -m rtx_tools.profiler.jfr_threads profile.jfr -t "Worker"
    python -m rtx_tools.profiler.jfr_threads profile.jfr --detect-stuck
    python -m rtx_tools.profiler.jfr_threads profile.jfr --cpu-load
    python -m rtx_tools.profiler.jfr_threads profile.jfr --after 22:04 --before 22:06
"""

import argparse
import sys
from collections import defaultdict
from datetime import datetime

from .jfr_parse import (
    compile_thread_filter,
    event_duration_ms,
    event_timestamp_ms,
    filter_by_time,
    fmt_ms,
    jfr_events,
    jfr_summary_text,
    json_output,
    matches_thread,
    parse_summary_events,
    parse_time_arg,
    print_header,
    stack_frames,
    thread_name,
)


def _ts_label(ms):
    if ms <= 0:
        return "?"
    return datetime.fromtimestamp(ms / 1000.0).strftime("%H:%M:%S.%f")[:-3]


def show_inventory(events, thread_re, top_n):
    """Thread inventory: all threads with first/last event times."""
    thread_info = defaultdict(lambda: {"first": float("inf"), "last": 0, "count": 0})
    for ev in events:
        if not matches_thread(ev, thread_re):
            continue
        tn = thread_name(ev)
        ts = event_timestamp_ms(ev)
        info = thread_info[tn]
        info["count"] += 1
        if ts > 0:
            info["first"] = min(info["first"], ts)
            info["last"] = max(info["last"], ts)

    print_header(f"Thread Inventory ({len(thread_info)} threads)")
    sorted_threads = sorted(thread_info.items(), key=lambda x: x[1]["count"], reverse=True)
    tw = max((len(n) for n, _ in sorted_threads[:top_n]), default=20)
    print(f"\n  {'Thread':<{tw}}  {'Events':>8}  {'First':>12}  {'Last':>12}  {'Span':>10}")
    print(f"  {'':-<{tw}}  {'':->8}  {'':->12}  {'':->12}  {'':->10}")

    for tn, info in sorted_threads[:top_n]:
        span = info["last"] - info["first"] if info["last"] > info["first"] else 0
        print(
            f"  {tn:<{tw}}  {info['count']:>8}  "
            f"{_ts_label(info['first']):>12}  {_ts_label(info['last']):>12}  "
            f"{fmt_ms(span):>10}"
        )

    if len(sorted_threads) > top_n:
        print(f"\n  ... {len(sorted_threads) - top_n} more threads")


def show_cpu_load(jfr, thread_re):
    """Per-thread CPU load from jdk.ThreadCPULoad."""
    events = jfr_events(jfr, ["jdk.ThreadCPULoad"])
    if not events:
        print("  No ThreadCPULoad events found.", file=sys.stderr)
        return

    thread_user = defaultdict(list)
    thread_sys = defaultdict(list)
    for ev in events:
        if not matches_thread(ev, thread_re):
            continue
        tn = thread_name(ev)
        vals = ev.get("values", {})
        if "user" in vals:
            thread_user[tn].append(vals["user"])
        if "system" in vals:
            thread_sys[tn].append(vals["system"])

    print_header("Per-Thread CPU Load (ThreadCPULoad)")
    sorted_threads = sorted(thread_user.items(), key=lambda x: sum(x[1]) / len(x[1]), reverse=True)
    tw = max((len(n) for n, _ in sorted_threads[:30]), default=20)
    print(f"\n  {'Thread':<{tw}}  {'Avg User':>10}  {'Max User':>10}  {'Avg Sys':>10}")
    print(f"  {'':-<{tw}}  {'':->10}  {'':->10}  {'':->10}")

    for tn, user_vals in sorted_threads[:30]:
        avg_u = sum(user_vals) / len(user_vals) * 100
        max_u = max(user_vals) * 100
        sys_vals = thread_sys.get(tn, [0])
        avg_s = sum(sys_vals) / len(sys_vals) * 100
        print(f"  {tn:<{tw}}  {avg_u:>9.1f}%  {max_u:>9.1f}%  {avg_s:>9.1f}%")


def detect_stuck(jfr, thread_re, cutoff_s=5.0):
    """Detect threads that stop producing JFR events while possibly still running.

    A thread is "dark" if it has events in the first half of the recording
    but none in the last *cutoff_s* seconds, while other threads are active.
    """
    all_types = [
        "jdk.ExecutionSample",
        "jdk.NativeMethodSample",
        "jdk.ObjectAllocationSample",
        "jdk.ThreadPark",
    ]
    summary = jfr_summary_text(jfr)
    available = {n for n, _, _ in parse_summary_events(summary)}
    fetch = [t for t in all_types if t in available]
    if not fetch:
        print("  Not enough event types to detect stuck threads.", file=sys.stderr)
        return

    events = jfr_events(jfr, fetch)
    thread_last = defaultdict(float)
    thread_first = defaultdict(lambda: float("inf"))
    thread_counts = defaultdict(int)
    global_last = 0

    for ev in events:
        ts = event_timestamp_ms(ev)
        if ts <= 0:
            continue
        tn = thread_name(ev)
        if thread_re and not thread_re.search(tn):
            continue
        thread_last[tn] = max(thread_last[tn], ts)
        thread_first[tn] = min(thread_first[tn], ts)
        thread_counts[tn] += 1
        global_last = max(global_last, ts)

    if not global_last:
        return

    cutoff_ms = cutoff_s * 1000
    dark_threads = []
    for tn in thread_last:
        gap = global_last - thread_last[tn]
        if gap > cutoff_ms and thread_counts[tn] > 10:
            dark_threads.append((tn, thread_last[tn], gap, thread_counts[tn]))

    dark_threads.sort(key=lambda x: x[2], reverse=True)

    print_header(f"Dark Thread Detection (gap > {cutoff_s}s from recording end)")
    if not dark_threads:
        print("  No dark threads detected -- all threads active until recording end.")
        return

    tw = max((len(t[0]) for t in dark_threads), default=20)
    print(f"\n  {'Thread':<{tw}}  {'Last Event':>12}  {'Gap':>10}  {'Events':>8}")
    print(f"  {'':-<{tw}}  {'':->12}  {'':->10}  {'':->8}")
    for tn, last_ts, gap, count in dark_threads:
        print(f"  {tn:<{tw}}  {_ts_label(last_ts):>12}  {fmt_ms(gap):>10}  {count:>8}")

    print(f"\n  Recording end: {_ts_label(global_last)}")
    print("  These threads stopped producing JFR events while the recording continued.")
    print("  Likely stuck in native code (malloc, JNA, JNI) or an infinite loop.")


def show_park_analysis(jfr, thread_re, top_n):
    """Top park/wait sites with durations."""
    events = jfr_events(jfr, ["jdk.ThreadPark", "jdk.JavaMonitorWait", "jdk.ThreadSleep"])
    if not events:
        print("  No park/wait/sleep events found.", file=sys.stderr)
        return

    site_dur = defaultdict(float)
    site_count = defaultdict(int)
    for ev in events:
        if not matches_thread(ev, thread_re):
            continue
        dur = event_duration_ms(ev)
        frames = stack_frames(ev, simple=True)
        site = frames[0] if frames else "<no stack>"
        site_dur[site] += dur
        site_count[site] += 1

    print_header("Park/Wait/Sleep Analysis")
    sorted_sites = sorted(site_dur.items(), key=lambda x: x[1], reverse=True)
    sw = max((len(s) for s, _ in sorted_sites[:top_n]), default=30)
    print(f"\n  {'#':>4}  {'Site':<{sw}}  {'Total':>10}  {'Count':>8}  {'Avg':>10}")
    print(f"  {'':>4}  {'':-<{sw}}  {'':->10}  {'':->8}  {'':->10}")

    for i, (site, dur) in enumerate(sorted_sites[:top_n], 1):
        cnt = site_count[site]
        avg = dur / cnt if cnt else 0
        print(f"  {i:>4}  {site:<{sw}}  {fmt_ms(dur):>10}  {cnt:>8}  {fmt_ms(avg):>10}")
    print()


def _render_json(thread_counts, total_samples):
    """Return the JSON-serialisable dict for --json output.

    *thread_counts* is a dict of {thread_name: sample_count}.
    *total_samples* is the total number of samples (used to compute cpuPct).

    Keys match what generate_profile_data.py's build_jfr() reads:
      threads[].{name, cpuPct, sampleCount}
    """
    threads = []
    for name, count in sorted(thread_counts.items(), key=lambda x: x[1], reverse=True):
        cpu_pct = (count / total_samples * 100.0) if total_samples > 0 else 0.0
        threads.append({"name": name, "cpuPct": round(cpu_pct, 2), "sampleCount": count})
    return {"threads": threads}


def run(args):
    jfr = args.jfr_file
    thread_re = compile_thread_filter(args.thread)
    top_n = args.top

    show_all = not any([args.cpu_load, args.detect_stuck, args.parks])

    if args.json:
        sample_events = jfr_events(jfr, ["jdk.ExecutionSample", "jdk.NativeMethodSample"])
        after_ms = parse_time_arg(args.after, reference_events=sample_events)
        before_ms = parse_time_arg(args.before, reference_events=sample_events)
        sample_events = filter_by_time(sample_events, after_ms, before_ms)
        thread_counts: dict = defaultdict(int)
        for ev in sample_events:
            if not matches_thread(ev, thread_re):
                continue
            thread_counts[thread_name(ev)] += 1
        total = sum(thread_counts.values())
        json_output(_render_json(dict(thread_counts), total_samples=total))
        return

    all_types = [
        "jdk.ExecutionSample",
        "jdk.NativeMethodSample",
        "jdk.ObjectAllocationSample",
        "jdk.ThreadPark",
        "jdk.JavaMonitorWait",
        "jdk.ThreadSleep",
    ]
    summary = jfr_summary_text(jfr)
    available = {n for n, _, _ in parse_summary_events(summary)}
    fetch = [t for t in all_types if t in available]
    all_events = jfr_events(jfr, fetch)

    after_ms = parse_time_arg(args.after, reference_events=all_events)
    before_ms = parse_time_arg(args.before, reference_events=all_events)
    all_events = filter_by_time(all_events, after_ms, before_ms)

    if show_all:
        show_inventory(all_events, thread_re, top_n)

    if show_all or args.cpu_load:
        show_cpu_load(jfr, thread_re)

    if show_all or args.detect_stuck:
        detect_stuck(jfr, thread_re)

    if show_all or args.parks:
        show_park_analysis(jfr, thread_re, top_n)

    print()


def main():
    parser = argparse.ArgumentParser(
        description="Thread state analysis from JFR recordings.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  python -m rtx_tools.profiler.jfr_threads profile.jfr                     # full report
  python -m rtx_tools.profiler.jfr_threads profile.jfr -t "Worker"         # only worker threads
  python -m rtx_tools.profiler.jfr_threads profile.jfr --detect-stuck      # find dark threads
  python -m rtx_tools.profiler.jfr_threads profile.jfr --cpu-load          # per-thread CPU
  python -m rtx_tools.profiler.jfr_threads profile.jfr --parks             # park/wait analysis""",
    )
    parser.add_argument("jfr_file", help="Path to the .jfr recording file")
    parser.add_argument("--thread", "-t", default=None, help="Filter threads by regex")
    parser.add_argument("--top", "-n", type=int, default=30, help="Top N entries (default: 30)")
    parser.add_argument("--cpu-load", action="store_true", help="Per-thread CPU load")
    parser.add_argument("--detect-stuck", action="store_true", help="Detect dark/stuck threads")
    parser.add_argument("--parks", action="store_true", help="Park/wait/sleep analysis")
    parser.add_argument("--after", default=None, help="Only events after this time")
    parser.add_argument("--before", default=None, help="Only events before this time")
    parser.add_argument("--json", action="store_true", help="Output as JSON (limited)")
    run(parser.parse_args())


if __name__ == "__main__":
    main()

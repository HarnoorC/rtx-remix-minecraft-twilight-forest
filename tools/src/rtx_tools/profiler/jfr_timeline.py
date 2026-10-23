#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
JFR Timeline Analysis -- time-bucketed view of where samples land.

Divides the recording into intervals and shows CPU sample distribution,
top methods, and thread activity per bucket. Spots spikes, phase changes,
and periodic hitches.

Usage:
    python -m rtx_tools.profiler.jfr_timeline profile.jfr
    python -m rtx_tools.profiler.jfr_timeline profile.jfr -t "^main$" --interval 500
    python -m rtx_tools.profiler.jfr_timeline profile.jfr --interval 16 -t "^main$"
    python -m rtx_tools.profiler.jfr_timeline profile.jfr --gc
"""

import argparse
import sys
from collections import defaultdict

from .jfr_parse import (
    apply_common_filters,
    event_duration_ms,
    event_timestamp_ms,
    fmt_count,
    fmt_ms,
    get_sampling_period_ms,
    jfr_events,
    json_output,
    print_header,
    stack_frames,
)


def bucket_key(ts_ms, origin_ms, interval_ms):
    if ts_ms < origin_ms:
        return 0
    return int((ts_ms - origin_ms) / interval_ms)


def run(args):
    jfr = args.jfr_file
    simple = not args.fqn
    interval = args.interval

    event_types = ["jdk.ExecutionSample", "jdk.NativeMethodSample"]
    events = jfr_events(jfr, event_types)
    events = apply_common_filters(events, args)

    if not events:
        print(f"No CPU samples found for thread '{args.thread or 'all'}'.", file=sys.stderr)
        sys.exit(1)

    timestamps = [event_timestamp_ms(ev) for ev in events]
    origin = min(ts for ts in timestamps if ts > 0) if any(ts > 0 for ts in timestamps) else 0
    end = max(timestamps)
    duration = end - origin

    buckets = defaultdict(list)
    for ev, ts in zip(events, timestamps, strict=False):
        bk = bucket_key(ts, origin, interval)
        buckets[bk].append(ev)

    num_buckets = max(buckets.keys()) + 1 if buckets else 0

    gc_buckets = defaultdict(float)
    if args.gc:
        gc_events = jfr_events(jfr, ["jdk.GCPhasePause"])
        for ev in gc_events:
            ts = event_timestamp_ms(ev)
            dur = event_duration_ms(ev)
            bk = bucket_key(ts, origin, interval)
            gc_buckets[bk] += dur

    period = get_sampling_period_ms(jfr)
    thread_label = args.thread or "all threads"

    if args.json:
        rows = []
        for bk in range(num_buckets):
            evs = buckets.get(bk, [])
            row = {"time_ms": bk * interval, "samples": len(evs), "est_cpu_ms": len(evs) * period}
            if args.gc:
                row["gc_ms"] = gc_buckets.get(bk, 0)
            rows.append(row)
        json_output(rows)
        return

    header = (
        f"Timeline | {thread_label} | {fmt_count(len(events))} samples | "
        f"{fmt_ms(interval)}ms buckets | ~{fmt_ms(duration)} recording"
    )
    print_header(header)

    max_samples = max((len(evs) for evs in buckets.values()), default=1)
    bar_max = 40
    gc_col = "  GC" if args.gc else ""

    print(f"\n{'Time':>10}  {'Samples':>8}  {'~CPU':>8}  {'':>{bar_max}}  {'Top Method (self)':<40}{gc_col}")
    print(f"{'':>10}  {'':->8}  {'':->8}  {'':->{bar_max}}  {'':-<40}{'  ----' if args.gc else ''}")

    for bk in range(num_buckets):
        evs = buckets.get(bk, [])
        count = len(evs)
        bar_len = int(count / max_samples * bar_max) if max_samples else 0
        bar = "#" * bar_len
        est_cpu = fmt_ms(count * period)

        top_method = ""
        if evs:
            method_counts = defaultdict(int)
            for ev in evs:
                frames = stack_frames(ev, simple=simple)
                if frames:
                    method_counts[frames[0]] += 1
            if method_counts:
                best = max(method_counts.items(), key=lambda x: x[1])
                top_method = f"{best[0]} ({best[1]})"
                if len(top_method) > 40:
                    top_method = top_method[:37] + "..."

        gc_info = ""
        if args.gc and bk in gc_buckets:
            gc_info = f"  {fmt_ms(gc_buckets[bk])}"

        print(f"{fmt_ms(bk * interval):>10}  {count:>8}  {est_cpu:>8}  {bar:<{bar_max}}  {top_method:<40}{gc_info}")

    # Summary stats
    counts_per_bucket = [len(buckets.get(bk, [])) for bk in range(num_buckets)]
    if counts_per_bucket:
        avg = sum(counts_per_bucket) / len(counts_per_bucket)
        mx = max(counts_per_bucket)
        mn = min(counts_per_bucket)
        variance = sum((c - avg) ** 2 for c in counts_per_bucket) / len(counts_per_bucket)
        stddev = variance**0.5

        print("\n  Bucket stats:")
        print(f"    Avg samples/bucket : {avg:.1f}  (~{fmt_ms(avg * period)} CPU)")
        print(f"    Max samples/bucket : {mx}  (~{fmt_ms(mx * period)} CPU)")
        print(f"    Min samples/bucket : {mn}")
        print(f"    Stddev             : {stddev:.1f}")
        if avg > 0:
            print(f"    Jitter (max-min)/avg : {(mx - mn) / avg * 100:.0f}%")

        if stddev > 0:
            threshold = avg + 2 * stddev
            spikes = [(bk, c) for bk, c in enumerate(counts_per_bucket) if c > threshold]
            if spikes:
                print(f"\n  Spikes (>{threshold:.0f} samples, 2-sigma):")
                for bk, c in spikes[:10]:
                    print(f"    {fmt_ms(bk * interval):>10}  {c} samples (~{fmt_ms(c * period)} CPU)")

    print()


def main():
    parser = argparse.ArgumentParser(
        description="Time-bucketed analysis of JFR CPU samples.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  python -m rtx_tools.profiler.jfr_timeline profile.jfr                             # 1s buckets
  python -m rtx_tools.profiler.jfr_timeline profile.jfr -t "^main$" --interval 500  # 500ms buckets
  python -m rtx_tools.profiler.jfr_timeline profile.jfr --interval 16 --gc           # per-frame + GC""",
    )
    parser.add_argument("jfr_file", help="Path to the .jfr recording file")
    parser.add_argument("--thread", "-t", default=None, help="Filter threads by regex")
    parser.add_argument("--interval", "-i", type=float, default=1000, help="Bucket interval in ms (default: 1000)")
    parser.add_argument("--gc", action="store_true", help="Overlay GC pause durations")
    parser.add_argument("--fqn", action="store_true", help="Fully qualified class names")
    parser.add_argument("--after", default=None, help="Only events after this time")
    parser.add_argument("--before", default=None, help="Only events before this time")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    run(parser.parse_args())


if __name__ == "__main__":
    main()

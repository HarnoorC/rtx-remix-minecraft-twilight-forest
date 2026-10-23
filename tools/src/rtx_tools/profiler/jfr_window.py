#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
JFR Time-Window Drill-Down -- focus on a specific clock-time range.

Filters execution samples to a window and shows per-thread stack
breakdowns. Ideal for investigating spikes spotted in the timeline.

Usage:
    python -m rtx_tools.profiler.jfr_window profile.jfr --after 15:50 --before 15:52
    python -m rtx_tools.profiler.jfr_window profile.jfr --after 22:04 --before 22:05 --depth 15
    python -m rtx_tools.profiler.jfr_window profile.jfr --after 15:50 --before 15:52 --json
"""

import argparse
import sys
from collections import defaultdict
from datetime import datetime

from .jfr_parse import (
    compile_thread_filter,
    event_timestamp_ms,
    filter_by_time,
    jfr_events,
    json_output,
    matches_thread,
    parse_time_arg,
    stack_frames,
    thread_name,
)


def run(args):
    events = jfr_events(args.jfr_file, ["jdk.ExecutionSample", "jdk.NativeMethodSample"])
    if not events:
        print("No execution samples found", file=sys.stderr)
        sys.exit(1)

    thread_re = compile_thread_filter(args.thread)
    events = [ev for ev in events if matches_thread(ev, thread_re)]

    after_ms = parse_time_arg(args.after, reference_events=events)
    before_ms = parse_time_arg(args.before, reference_events=events)
    windowed = filter_by_time(events, after_ms, before_ms)

    first_ts = event_timestamp_ms(events[0])
    date_str = datetime.fromtimestamp(first_ts / 1000.0).strftime("%Y-%m-%d") if first_ts else "?"

    if not args.json:
        print(f"Recording date: {date_str}")
        print(f"Window: {args.after or '*'} - {args.before or '*'} ({len(windowed)} samples)")
        print()

    if not windowed:
        all_ts = [event_timestamp_ms(e) for e in events if event_timestamp_ms(e) > 0]
        if all_ts:
            min_dt = datetime.fromtimestamp(min(all_ts) / 1000.0).astimezone()
            max_dt = datetime.fromtimestamp(max(all_ts) / 1000.0).astimezone()
            print(f"Available range: {min_dt.strftime('%H:%M:%S')} - {max_dt.strftime('%H:%M:%S')}", file=sys.stderr)
        sys.exit(1)

    by_thread = defaultdict(list)
    for ev in windowed:
        by_thread[thread_name(ev)].append(ev)

    if args.json:
        result = {}
        for tname in sorted(by_thread, key=lambda t: len(by_thread[t]), reverse=True):
            tevents = by_thread[tname]
            stack_counts = defaultdict(int)
            for ev in tevents:
                frames = stack_frames(ev)[: args.depth]
                key = ";".join(frames) if frames else "[no stack]"
                stack_counts[key] += 1
            result[tname] = {
                "samples": len(tevents),
                "stacks": dict(sorted(stack_counts.items(), key=lambda x: x[1], reverse=True)),
            }
        json_output(result)
        return

    for tname in sorted(by_thread, key=lambda t: len(by_thread[t]), reverse=True):
        tevents = by_thread[tname]
        print(f"=== {tname} ({len(tevents)} samples) ===")

        stack_counts = defaultdict(int)
        stack_examples = {}
        for ev in tevents:
            frames = stack_frames(ev)[: args.depth]
            key = " -> ".join(frames) if frames else "[no stack]"
            stack_counts[key] += 1
            if key not in stack_examples:
                stack_examples[key] = frames

        for key, count in sorted(stack_counts.items(), key=lambda x: x[1], reverse=True)[: args.top]:
            pct = count / len(tevents) * 100
            print(f"  [{count:4d} samples, {pct:5.1f}%]")
            frames = stack_examples[key]
            for j, f in enumerate(frames):
                print(f"    {'  ' * j}{f}")
            print()
        print()


def main():
    parser = argparse.ArgumentParser(
        description="JFR time-window drill-down.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  python -m rtx_tools.profiler.jfr_window profile.jfr --after 15:50 --before 15:52
  python -m rtx_tools.profiler.jfr_window profile.jfr --after 22:04 --before 22:05 -t "Worker"
  python -m rtx_tools.profiler.jfr_window profile.jfr --after 15:50 --before 15:52 --json""",
    )
    parser.add_argument("jfr_file", help="Path to the .jfr recording file")
    parser.add_argument("--after", default=None, help="Start time (HH:MM or HH:MM:SS)")
    parser.add_argument("--before", default=None, help="End time (HH:MM or HH:MM:SS)")
    parser.add_argument("--thread", "-t", default=None, help="Filter threads by regex")
    parser.add_argument("--depth", type=int, default=10, help="Stack depth (default: 10)")
    parser.add_argument("--top", type=int, default=20, help="Top stacks per thread (default: 20)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    run(parser.parse_args())


if __name__ == "__main__":
    main()

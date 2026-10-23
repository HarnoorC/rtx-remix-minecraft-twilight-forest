#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
JFR Flamegraph Export -- emit collapsed stacks for flamegraph tools.

Outputs Brendan Gregg's collapsed stack format, one line per unique
stack with a trailing count. Pipe to flamegraph.pl, speedscope, or
any tool that accepts this format.

Modes:
  cpu    -- from ExecutionSample / NativeMethodSample
  alloc  -- from ObjectAllocationSample (count = allocation weight in bytes)
  lock   -- from JavaMonitorEnter (count = blocked duration in us)

Usage:
    python -m rtx_tools.profiler.jfr_flame profile.jfr > cpu.folded
    python -m rtx_tools.profiler.jfr_flame profile.jfr --mode alloc > alloc.folded
    python -m rtx_tools.profiler.jfr_flame profile.jfr --mode lock > lock.folded
    python -m rtx_tools.profiler.jfr_flame profile.jfr -t "^main$" --filter "Remix"
"""

import argparse
import sys
from collections import defaultdict

from .jfr_parse import (
    apply_common_filters,
    event_duration_ms,
    jfr_events,
    stack_frames,
    thread_name,
)


def run(args):
    jfr = args.jfr_file
    simple = not args.fqn

    if args.mode == "alloc":
        event_types = ["jdk.ObjectAllocationSample"]
    elif args.mode == "lock":
        event_types = ["jdk.JavaMonitorEnter"]
    else:
        event_types = ["jdk.ExecutionSample", "jdk.NativeMethodSample"]

    events = jfr_events(jfr, event_types)
    events = apply_common_filters(events, args)

    if args.filter:
        events = [ev for ev in events if any(args.filter.lower() in f.lower() for f in stack_frames(ev, simple=simple))]

    if not events:
        print(f"No events found for mode '{args.mode}'.", file=sys.stderr)
        sys.exit(1)

    print(f"# mode={args.mode}, events={len(events)}", file=sys.stderr)

    stacks = defaultdict(int)
    for ev in events:
        frames = stack_frames(ev, simple=simple)
        if not frames:
            continue
        frames.reverse()

        parts = []
        if args.include_thread:
            parts.append(thread_name(ev))
        parts.extend(frames)
        key = ";".join(parts)

        if args.mode == "alloc":
            weight = ev.get("values", {}).get("weight", 1)
            stacks[key] += weight
        elif args.mode == "lock":
            dur_us = int(event_duration_ms(ev) * 1000)
            stacks[key] += max(dur_us, 1)
        else:
            stacks[key] += 1

    for stack, count in sorted(stacks.items(), key=lambda x: x[1], reverse=True):
        print(f"{stack} {count}")


def main():
    parser = argparse.ArgumentParser(
        description="Export collapsed stacks for flamegraph tools.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  python -m rtx_tools.profiler.jfr_flame profile.jfr > cpu.folded
  python -m rtx_tools.profiler.jfr_flame profile.jfr --mode alloc > alloc.folded
  python -m rtx_tools.profiler.jfr_flame profile.jfr --mode lock -t "^main$" > lock.folded
  cat cpu.folded | flamegraph.pl > flamegraph.svg""",
    )
    parser.add_argument("jfr_file", help="Path to the .jfr recording file")
    parser.add_argument(
        "--mode",
        choices=["cpu", "alloc", "lock"],
        default="cpu",
        help="Stack source: cpu, alloc, or lock (default: cpu)",
    )
    parser.add_argument("--thread", "-t", default=None, help="Filter threads by regex")
    parser.add_argument("--filter", default=None, help="Only stacks containing this substring")
    parser.add_argument("--include-thread", action="store_true", help="Prefix each stack with thread name")
    parser.add_argument("--fqn", action="store_true", help="Fully qualified class names")
    parser.add_argument("--after", default=None, help="Only events after this time")
    parser.add_argument("--before", default=None, help="Only events before this time")
    run(parser.parse_args())


if __name__ == "__main__":
    main()

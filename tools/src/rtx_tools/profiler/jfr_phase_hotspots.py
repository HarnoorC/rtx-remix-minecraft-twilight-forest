#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Find CPU and allocation hotspots that occur inside minecraft.JavaPhase windows.

Examples:
  python -m rtx_tools.profiler.jfr_phase_hotspots profile.jfr --phase "Entities capture\\+submit" -t "^main$"
  python -m rtx_tools.profiler.jfr_phase_hotspots profile.jfr --phase "Chunk.Gen" --mode alloc --by size
"""

import argparse
import bisect
import re
import sys
from collections import defaultdict
from typing import Literal, NotRequired, TypedDict

from .jfr_parse import (
    apply_common_filters,
    event_duration_ms,
    event_timestamp_ms,
    fmt_bytes,
    fmt_count,
    fmt_ms,
    fmt_pct,
    get_sampling_period_ms,
    jfr_events,
    json_output,
    print_header,
    stack_frames,
    thread_name,
)

PHASE_EVENT = "minecraft.JavaPhase"

type _IntervalIndex = dict[str, tuple[list[float], list[tuple[float, float]]]]


class _AllocationSiteStats(TypedDict):
    count: int
    bytes: int
    classes: defaultdict[str, int]


class _CpuRow(TypedDict):
    method: str
    samples: int
    selfMs: float
    pct: float


_AllocationRow = TypedDict(
    "_AllocationRow",
    {"site": str, "class": str, "count": int, "bytes": int, "pctBytes": float, "pctCount": float},
)


class _HotspotResult(TypedDict):
    phase: str
    phaseEventCount: int
    phaseTotalMs: float
    threads: list[str]
    cpu: NotRequired[list[_CpuRow]]
    cpuSampleCount: NotRequired[int]
    cpuPeriodMs: NotRequired[float]
    allocations: NotRequired[list[_AllocationRow]]
    allocationSampleCount: NotRequired[int]


def alloc_class(event):
    oc = event.get("values", {}).get("objectClass")
    if isinstance(oc, dict):
        return oc.get("name", "?").replace("/", ".")
    if isinstance(oc, str):
        return oc
    return "?"


def alloc_weight(event):
    return event.get("values", {}).get("weight", 0)


def build_intervals(phase_events) -> tuple[_IntervalIndex, float]:
    by_thread: defaultdict[str, list[tuple[float, float]]] = defaultdict(list)
    total_ms = 0.0
    for ev in phase_events:
        start = event_timestamp_ms(ev)
        dur = event_duration_ms(ev)
        if start <= 0 or dur <= 0:
            continue
        by_thread[thread_name(ev)].append((start, start + dur))
        total_ms += dur

    indexed: _IntervalIndex = {}
    for thread, intervals in by_thread.items():
        intervals.sort()
        starts = [i[0] for i in intervals]
        indexed[thread] = (starts, intervals)
    return indexed, total_ms


def in_intervals(indexed: _IntervalIndex, event):
    thread = thread_name(event)
    ts = event_timestamp_ms(event)
    if ts <= 0 or thread not in indexed:
        return False
    starts, intervals = indexed[thread]
    idx = bisect.bisect_right(starts, ts) - 1
    return idx >= 0 and ts <= intervals[idx][1]


def cpu_rows(events, simple: bool, period_ms: float) -> list[_CpuRow]:
    counts: defaultdict[str, int] = defaultdict(int)
    for ev in events:
        frames = stack_frames(ev, simple=simple)
        if frames:
            counts[frames[0]] += 1
    total = sum(counts.values())
    rows: list[_CpuRow] = []
    for method, count in sorted(counts.items(), key=lambda kv: kv[1], reverse=True):
        rows.append(
            {
                "method": method,
                "samples": count,
                "selfMs": count * period_ms,
                "pct": (count / total * 100.0) if total else 0.0,
            }
        )
    return rows


def allocation_rows(events, simple: bool, by: str) -> list[_AllocationRow]:
    sites: defaultdict[str, _AllocationSiteStats] = defaultdict(
        lambda: {"count": 0, "bytes": 0, "classes": defaultdict(int)}
    )
    for ev in events:
        frames = stack_frames(ev, simple=simple)
        site = frames[0] if frames else "(no stack)"
        cls = alloc_class(ev)
        weight = alloc_weight(ev)
        sites[site]["count"] += 1
        sites[site]["bytes"] += weight
        sites[site]["classes"][cls] += 1

    sort_key: Literal["bytes", "count"] = "bytes" if by == "size" else "count"
    total_bytes = sum(s["bytes"] for s in sites.values())
    total_count = sum(s["count"] for s in sites.values())
    rows: list[_AllocationRow] = []
    for site, stats in sorted(sites.items(), key=lambda kv: kv[1][sort_key], reverse=True):
        top_class = max(stats["classes"].items(), key=lambda kv: kv[1])[0] if stats["classes"] else ""
        rows.append(
            {
                "site": site,
                "class": top_class,
                "count": stats["count"],
                "bytes": stats["bytes"],
                "pctBytes": (stats["bytes"] / total_bytes * 100.0) if total_bytes else 0.0,
                "pctCount": (stats["count"] / total_count * 100.0) if total_count else 0.0,
            }
        )
    return rows


def run(args):
    simple = not args.fqn
    phase_re = re.compile(args.phase, re.IGNORECASE)

    phase_events = jfr_events(args.jfr_file, [PHASE_EVENT])
    phase_events = apply_common_filters(phase_events, args)
    phase_events = [ev for ev in phase_events if phase_re.search(ev.get("values", {}).get("phase", ""))]
    if not phase_events:
        print(f"No {PHASE_EVENT} events matched phase '{args.phase}'.", file=sys.stderr)
        sys.exit(1)

    intervals, phase_total_ms = build_intervals(phase_events)
    if not intervals:
        print(f"Matched phase '{args.phase}', but no timed intervals were usable.", file=sys.stderr)
        sys.exit(1)

    result: _HotspotResult = {
        "phase": args.phase,
        "phaseEventCount": len(phase_events),
        "phaseTotalMs": phase_total_ms,
        "threads": sorted(intervals.keys()),
    }

    if args.mode in ("cpu", "both"):
        cpu_events = jfr_events(args.jfr_file, ["jdk.ExecutionSample", "jdk.NativeMethodSample"])
        cpu_events = [ev for ev in cpu_events if in_intervals(intervals, ev)]
        period_ms = get_sampling_period_ms(args.jfr_file)
        result["cpu"] = cpu_rows(cpu_events, simple, period_ms)[: args.top]
        result["cpuSampleCount"] = len(cpu_events)
        result["cpuPeriodMs"] = period_ms

    if args.mode in ("alloc", "both"):
        alloc_events = jfr_events(args.jfr_file, ["jdk.ObjectAllocationSample"])
        alloc_events = [ev for ev in alloc_events if in_intervals(intervals, ev)]
        result["allocations"] = allocation_rows(alloc_events, simple, args.by)[: args.top]
        result["allocationSampleCount"] = len(alloc_events)

    if args.json:
        json_output(result)
        return

    print_header(
        f"Java Phase Hotspots | phase /{args.phase}/ | "
        f"{fmt_count(len(phase_events))} phase events | {fmt_ms(phase_total_ms)} phase time"
    )
    print(f"\nThreads: {', '.join(result['threads'])}\n")

    if "cpu" in result:
        rows = result["cpu"]
        print(
            f"CPU samples inside phase: {fmt_count(result['cpuSampleCount'])} (period ~{fmt_ms(result['cpuPeriodMs'])})"
        )
        print(f"{'#':>3}  {'Method':<58}  {'Samples':>8}  {'~Time':>10}  {'%':>8}")
        print(f"{'':>3}  {'':-<58}  {'':->8}  {'':->10}  {'':->8}")
        total_samples = max(result["cpuSampleCount"], 1)
        for i, row in enumerate(rows, 1):
            print(
                f"{i:>3}  {row['method']:<58.58}  {fmt_count(row['samples']):>8}  "
                f"{fmt_ms(row['selfMs']):>10}  {fmt_pct(row['samples'], total_samples)}"
            )
        print()

    if "allocations" in result:
        rows = result["allocations"]
        total_bytes = sum(
            r["bytes"]
            for r in allocation_rows(
                [ev for ev in jfr_events(args.jfr_file, ["jdk.ObjectAllocationSample"]) if in_intervals(intervals, ev)],
                simple,
                args.by,
            )
        )
        print(f"Allocation samples inside phase: {fmt_count(result['allocationSampleCount'])}")
        print(f"{'#':>3}  {'Site':<46}  {'Count':>8}  {'Bytes':>12}  {'Top Class':<28}  {'% Size':>8}")
        print(f"{'':>3}  {'':-<46}  {'':->8}  {'':->12}  {'':-<28}  {'':->8}")
        for i, row in enumerate(rows, 1):
            print(
                f"{i:>3}  {row['site']:<46.46}  {fmt_count(row['count']):>8}  "
                f"{fmt_bytes(row['bytes']):>12}  {row['class']:<28.28}  "
                f"{fmt_pct(row['bytes'], total_bytes)}"
            )
        print()


def main():
    parser = argparse.ArgumentParser(description="CPU/allocation hotspots inside RTX Remix Java phase windows.")
    parser.add_argument("jfr_file", help="Path to the .jfr recording file")
    parser.add_argument("--phase", required=True, help="Phase name regex, e.g. 'Entities capture\\+submit'")
    parser.add_argument("--thread", "-t", default=None, help="Filter phase threads by regex")
    parser.add_argument("--mode", choices=("cpu", "alloc", "both"), default="both")
    parser.add_argument("--by", choices=("size", "count"), default="size", help="Allocation sort key")
    parser.add_argument("--top", "-n", type=int, default=20)
    parser.add_argument("--after", default=None, help="Only phase events after this time")
    parser.add_argument("--before", default=None, help="Only phase events before this time")
    parser.add_argument("--fqn", action="store_true", help="Use fully qualified class names")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    run(parser.parse_args())


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Summarize minecraft.JavaPhase events emitted by ProfileScope.

Examples:
  python -m rtx_tools.profiler.jfr_phase_summary profile.jfr -t "^main$"
  python -m rtx_tools.profiler.jfr_phase_summary profile.jfr --phase "Chunk|Entity" --json
"""

import argparse
import re
import sys
from collections import defaultdict

from .jfr_parse import (
    apply_common_filters,
    event_duration_ms,
    fmt_count,
    fmt_ms,
    jfr_events,
    json_output,
    print_header,
    thread_name,
)

EVENT_TYPE = "minecraft.JavaPhase"
NUMERIC_FIELDS = (
    "entityCount",
    "layerCount",
    "boneCount",
    "drawCalls",
    "meshCreates",
    "captureCount",
    "surfaceCount",
    "dirtyLeaves",
    "installCount",
    "meshCategory",
    "vertexCount",
    "blockCount",
    "fluidCount",
    "bytes",
    "collisionChecks",
    "collisionSkips",
    "collisionNanos",
    "visibleChunkCount",
    "scannedChunkCount",
    "blockEntityChunkCount",
    "blockEntityCount",
    "noCullBlockEntityCount",
    "blockBreakingCount",
    "renderLayerCalls",
    "renderLayerSkips",
)


def percentile(values, pct):
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    pos = (len(values) - 1) * pct
    lo = int(pos)
    hi = min(lo + 1, len(values) - 1)
    frac = pos - lo
    return values[lo] * (1.0 - frac) + values[hi] * frac


# Pool threads differ only by ordinal, so collapse the ordinal. Without this a phase running
# on a worker pool splits into one row per thread and the numbers become unreadable.
_POOL_ORDINAL_RE = re.compile(r"^(Worker-Main-|RTX Remix mesh builder |ForkJoinPool[^-]*-worker-|pool-\d+-thread-)\d+$")


def canonical_thread(event):
    """Thread name with pool ordinals collapsed, so a pool yields one row rather than N."""
    name = thread_name(event)
    match = _POOL_ORDINAL_RE.match(name)
    return match.group(1) + "*" if match else name


def summarize(events):
    buckets = defaultdict(list)
    for ev in events:
        phase = ev.get("values", {}).get("phase", "(unknown)")
        # Keyed by thread as well as phase. A phase that runs on more than one thread was
        # previously merged into a single row and labelled with whichever thread happened to
        # emit first, which reported off-thread work as render-thread cost.
        buckets[(phase, canonical_thread(ev))].append(ev)

    rows = []
    for (phase, thread), phase_events in buckets.items():
        durations = sorted(event_duration_ms(ev) for ev in phase_events)
        total = sum(durations)
        frames = {
            ev.get("values", {}).get("frameIndex")
            for ev in phase_events
            if ev.get("values", {}).get("frameIndex", -1) >= 0
        }
        # Work off the render thread carries frameIndex -1. Falling back to the event count
        # here made perFrameMs equal avgMs, which reads as a huge per-frame cost for a phase
        # that runs a handful of long times on a background thread. Such rows get no
        # per-frame figure at all, because they have no meaningful one.
        frame_count = len(frames)
        metrics = {}
        for field in NUMERIC_FIELDS:
            vals = [ev.get("values", {}).get(field) for ev in phase_events if ev.get("values", {}).get(field, -1) >= 0]
            if vals:
                metrics[field] = {
                    "avg": sum(vals) / len(vals),
                    "max": max(vals),
                    "count": len(vals),
                }
        budget_hits = sum(1 for ev in phase_events if ev.get("values", {}).get("budgetHit"))
        if budget_hits:
            metrics["budgetHit"] = {"count": budget_hits}

        rows.append(
            {
                "phase": phase,
                "count": len(phase_events),
                "frames": frame_count,
                "totalMs": total,
                "perFrameMs": total / frame_count if frame_count else None,
                "avgMs": total / len(durations) if durations else 0.0,
                "p50Ms": percentile(durations, 0.50),
                "p95Ms": percentile(durations, 0.95),
                "p99Ms": percentile(durations, 0.99),
                "maxMs": durations[-1] if durations else 0.0,
                "thread": thread,
                "metrics": metrics,
            }
        )
    return sorted(rows, key=lambda r: r["totalMs"], reverse=True)


def metric_hint(row):
    metrics = row.get("metrics", {})
    hints = []
    for key in (
        "drawCalls",
        "entityCount",
        "blockEntityCount",
        "visibleChunkCount",
        "scannedChunkCount",
        "blockEntityChunkCount",
        "captureCount",
        "dirtyLeaves",
        "installCount",
        "vertexCount",
        "renderLayerCalls",
        "renderLayerSkips",
        "collisionChecks",
        "collisionSkips",
        "collisionNanos",
        "bytes",
    ):
        if key in metrics:
            value = metrics[key]["avg"]
            if key == "collisionNanos":
                hints.append(f"collisionMs avg={value / 1_000_000.0:.2f}")
            else:
                hints.append(f"{key} avg={value:.0f}")
    if "budgetHit" in metrics:
        hints.append(f"budgetHit={metrics['budgetHit']['count']}")
    return ", ".join(hints[:4])


def run(args):
    events = jfr_events(args.jfr_file, [EVENT_TYPE])
    events = apply_common_filters(events, args)

    if args.phase:
        phase_re = re.compile(args.phase, re.IGNORECASE)
        events = [ev for ev in events if phase_re.search(ev.get("values", {}).get("phase", ""))]

    if not events:
        print("No minecraft.JavaPhase events matched.", file=sys.stderr)
        sys.exit(1)

    rows = summarize(events)

    if args.json:
        json_output(rows[: args.top])
        return

    print_header(f"Java Phase Summary ({fmt_count(len(events))} events)")
    print(
        f"\n{'#':>3}  {'Phase':<30}  {'Count':>8}  {'/Frame':>9}  "
        f"{'Avg':>9}  {'p95':>9}  {'p99':>9}  {'Max':>9}  Signals"
    )
    print(f"{'':>3}  {'':-<30}  {'':->8}  {'':->9}  {'':->9}  {'':->9}  {'':->9}  {'':->9}  {'':-<32}")
    for i, row in enumerate(rows[: args.top], 1):
        print(
            f"{i:>3}  {row['phase']:<30.30}  {fmt_count(row['count']):>8}  "
            f"{fmt_ms(row['perFrameMs']):>9}  {fmt_ms(row['avgMs']):>9}  "
            f"{fmt_ms(row['p95Ms']):>9}  {fmt_ms(row['p99Ms']):>9}  "
            f"{fmt_ms(row['maxMs']):>9}  {metric_hint(row)}"
        )
    print()


def main():
    parser = argparse.ArgumentParser(description="Summarize RTX Remix Java phase JFR events.")
    parser.add_argument("jfr_file", help="Path to the .jfr recording file")
    parser.add_argument("--thread", "-t", default=None, help="Filter threads by regex")
    parser.add_argument("--phase", default=None, help="Filter phase names by regex")
    parser.add_argument("--top", "-n", type=int, default=30, help="Number of phases to show")
    parser.add_argument("--after", default=None, help="Only events after this time")
    parser.add_argument("--before", default=None, help="Only events before this time")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    run(parser.parse_args())


if __name__ == "__main__":
    main()

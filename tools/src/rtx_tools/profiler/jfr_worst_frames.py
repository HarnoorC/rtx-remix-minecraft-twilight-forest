#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Correlate benchmark worst frames with minecraft.JavaPhase JFR events.

The benchmark stores frame times by recording order, while ProfileScope stores
Java phase data by an internal frameIndex. Benchmark session markers let us
recover that mapping and explain the slowest recorded frames.

Examples:
  python -m rtx_tools.profiler.jfr_worst_frames --benchmark benchmark.json --jfr profile.jfr
  python -m rtx_tools.profiler.jfr_worst_frames --benchmark benchmark.json --jfr profile.jfr -n 20 --phase-count 12
  python -m rtx_tools.profiler.jfr_worst_frames --benchmark benchmark.json --jfr profile.jfr --json
"""

import argparse
import json

from .jfr_parse import (
    compile_thread_filter,
    event_duration_ms,
    event_timestamp_ms,
    fmt_count,
    fmt_ms,
    jfr_events,
    json_output,
    matches_thread,
    parse_timestamp,
    print_header,
)

PHASE_EVENT = "minecraft.JavaPhase"
FRAME_LEDGER_EVENT = "minecraft.FrameLedger"
SESSION_MARKER_EVENT = "minecraft.Benchmark.SessionMarker"
RECORDING_START_MARKER = "recording-start"
RECORDING_END_MARKER = "recording-end"

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


def load_benchmark(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        raise SystemExit(f"Benchmark file not found: {path}") from None
    except json.JSONDecodeError as e:
        raise SystemExit(f"Benchmark file is not valid JSON: {path}: {e}") from None

    per_frame = data.get("perFrame") or []
    if not per_frame:
        raise SystemExit(f"Benchmark file has no perFrame data: {path}")
    return data, [float(ns) / 1_000_000.0 for ns in per_frame]


def phase_name(event):
    return event.get("values", {}).get("phase", "")


def frame_index(event):
    value = event.get("values", {}).get("frameIndex", -1)
    return value if isinstance(value, int) else -1


def ns_to_ms(value):
    return round((float(value or 0) / 1_000_000.0), 3)


def recording_window(marker_events):
    start = None
    end = None
    for event in marker_events or []:
        values = event.get("values", {})
        marker = values.get("marker")
        ts = parse_timestamp(values.get("startTime"))
        if marker == RECORDING_START_MARKER:
            start = ts
        elif marker == RECORDING_END_MARKER:
            end = ts
    if start and end and end >= start:
        return start, end
    return None, None


def in_window(event, start_ms, end_ms):
    if start_ms is None and end_ms is None:
        return True
    ts = event_timestamp_ms(event)
    if ts <= 0:
        return False
    if start_ms is not None and ts < start_ms:
        return False
    if end_ms is not None and ts > end_ms:
        return False
    return True


def selected_phase_events(phase_events, marker_events, thread_pattern):
    thread_re = compile_thread_filter(thread_pattern)
    events = [ev for ev in phase_events if matches_thread(ev, thread_re)]
    start_ms, end_ms = recording_window(marker_events)
    windowed = [ev for ev in events if in_window(ev, start_ms, end_ms)]
    if windowed:
        return windowed, start_ms, end_ms, "benchmark session markers"
    return events, None, None, "all matching phase events"


def sort_event_key(event):
    ts = event_timestamp_ms(event)
    idx = frame_index(event)
    return (ts if ts > 0 else float("inf"), idx)


def map_recorded_frames(per_frame_ms, phase_events):
    onframes = [ev for ev in phase_events if phase_name(ev) == "renderAndSubmitFrame" and frame_index(ev) >= 0]
    onframes.sort(key=sort_event_key)
    count = min(len(per_frame_ms), len(onframes))
    mapping = {i: onframes[i] for i in range(count)}
    warning = None
    if len(onframes) != len(per_frame_ms):
        warning = (
            f"mapped {fmt_count(count)} of {fmt_count(len(per_frame_ms))} benchmark frames "
            f"from {fmt_count(len(onframes))} renderAndSubmitFrame events"
        )
    return mapping, warning


def event_metrics(event):
    values = event.get("values", {})
    result = {}
    for field in NUMERIC_FIELDS:
        value = values.get(field)
        if value not in (-1, None):
            result[field] = value
    if values.get("budgetHit"):
        result["budgetHit"] = True
    return result


def merge_metric(metrics, key, value):
    if isinstance(value, bool):
        metrics[key] = bool(metrics.get(key, False) or value)
    elif isinstance(value, (int, float)):
        metrics[key] = max(metrics.get(key, value), value)


def aggregate_frame_phases(events):
    buckets = {}
    for event in events:
        phase = phase_name(event) or "(unknown)"
        row = buckets.setdefault(
            phase,
            {
                "phase": phase,
                "count": 0,
                "totalMs": 0.0,
                "maxMs": 0.0,
                "metrics": {},
            },
        )
        duration = event_duration_ms(event)
        row["count"] += 1
        row["totalMs"] += duration
        row["maxMs"] = max(row["maxMs"], duration)
        for key, value in event_metrics(event).items():
            merge_metric(row["metrics"], key, value)
    return sorted(buckets.values(), key=lambda r: r["totalMs"], reverse=True)


def ledger_row(event):
    if not event:
        return None
    values = event.get("values", {})
    return {
        "fullFrameMs": ns_to_ms(values.get("fullFrameNanos")),
        "preWorldRenderEndMs": ns_to_ms(values.get("preWorldRenderEndNanos")),
        "minecraftRenderMs": ns_to_ms(values.get("minecraftRenderNanos")),
        "minecraftRenderUnattributedMs": ns_to_ms(values.get("minecraftRenderUnattributedNanos")),
        "worldRendererMs": ns_to_ms(values.get("worldRendererNanos")),
        "worldRendererUnattributedMs": ns_to_ms(values.get("worldRendererUnattributedNanos")),
        "runTasksMs": ns_to_ms(values.get("minecraftRunTasksNanos")),
        "renderAndSubmitFrameMs": ns_to_ms(values.get("renderAndSubmitFrameNanos")),
        "updateVisibleChunksMs": ns_to_ms(values.get("updateVisibleChunksNanos")),
        "submitMs": ns_to_ms(values.get("submitNanos")),
        "taskCount": int(values.get("taskCount") or 0),
        "slowTaskCount": int(values.get("slowTaskCount") or 0),
        "maxTaskMs": ns_to_ms(values.get("maxTaskNanos")),
        "maxTaskName": values.get("maxTaskName") or "",
    }


def build_worst_frames(
    per_frame_ms,
    phase_events,
    marker_events=None,
    ledger_events=None,
    top_frames=20,
    phase_count=10,
    thread_pattern="^Render thread$|^main$",
):
    phase_events, start_ms, end_ms, window_source = selected_phase_events(phase_events, marker_events, thread_pattern)
    frame_map, warning = map_recorded_frames(per_frame_ms, phase_events)

    by_frame = {}
    for event in phase_events:
        idx = frame_index(event)
        if idx >= 0:
            by_frame.setdefault(idx, []).append(event)

    ledgers_by_frame = {}
    for event in ledger_events or []:
        idx = frame_index(event)
        if idx >= 0:
            ledgers_by_frame[idx] = event

    worst_indices = sorted(
        range(len(per_frame_ms)),
        key=lambda i: per_frame_ms[i],
        reverse=True,
    )[:top_frames]

    frames = []
    for rank, record_index in enumerate(worst_indices, 1):
        onframe = frame_map.get(record_index)
        jfr_frame = frame_index(onframe) if onframe else None
        phases = aggregate_frame_phases(by_frame.get(jfr_frame, [])) if jfr_frame is not None else []
        frames.append(
            {
                "rank": rank,
                "recordIndex": record_index,
                "benchmarkMs": per_frame_ms[record_index],
                "jfrFrameIndex": jfr_frame,
                "renderAndSubmitFrameMs": event_duration_ms(onframe) if onframe else None,
                "ledger": ledger_row(ledgers_by_frame.get(jfr_frame)),
                "topPhases": phases[:phase_count],
            }
        )

    return {
        "recordFrames": len(per_frame_ms),
        "mappedFrames": len(frame_map),
        "window": {
            "source": window_source,
            "startMs": start_ms,
            "endMs": end_ms,
        },
        "warning": warning,
        "frames": frames,
    }


def metric_hint(metrics):
    hints = []
    for key in (
        "drawCalls",
        "entityCount",
        "captureCount",
        "dirtyLeaves",
        "installCount",
        "meshCreates",
        "vertexCount",
    ):
        if key in metrics:
            hints.append(f"{key}={metrics[key]}")
    if metrics.get("budgetHit"):
        hints.append("budgetHit")
    return ", ".join(hints[:4])


def print_report(report, benchmark_path, jfr_path):
    print_header(f"Worst Benchmark Frames ({fmt_count(report['recordFrames'])} recorded frames)")
    print(f"\nBenchmark: {benchmark_path}")
    print(f"JFR:       {jfr_path}")
    print(
        f"Mapping:   {fmt_count(report['mappedFrames'])}/{fmt_count(report['recordFrames'])} "
        f"frames via {report['window']['source']}"
    )
    if report.get("warning"):
        print(f"Warning:   {report['warning']}")

    for frame in report["frames"]:
        onframe = frame["renderAndSubmitFrameMs"]
        onframe_text = fmt_ms(onframe) if onframe is not None else "n/a"
        jfr_frame = frame["jfrFrameIndex"] if frame["jfrFrameIndex"] is not None else "n/a"
        print(
            f"\n#{frame['rank']:>2}  record={frame['recordIndex']:>4}  "
            f"bench={fmt_ms(frame['benchmarkMs']):>8}  "
            f"jfrFrame={jfr_frame!s:>5}  renderAndSubmitFrame={onframe_text:>8}"
        )
        if not frame["topPhases"]:
            print("      (no Java phase events mapped)")
            continue
        ledger = frame.get("ledger")
        if ledger:
            max_task = ledger["maxTaskName"].rsplit(".", 1)[-1] if ledger["maxTaskName"] else ""
            max_task_suffix = f"  maxTask={ledger['maxTaskMs']:.3f}ms {max_task}" if max_task else ""
            print(
                f"      ledger: preEND={fmt_ms(ledger['preWorldRenderEndMs'])}  "
                f"runTasks={fmt_ms(ledger['runTasksMs'])}  "
                f"unknownMC={fmt_ms(ledger['minecraftRenderUnattributedMs'])}  "
                f"unknownWR={fmt_ms(ledger['worldRendererUnattributedMs'])}  "
                f"tasks={ledger['taskCount']} slow={ledger['slowTaskCount']}{max_task_suffix}"
            )
        for phase in frame["topPhases"]:
            hint = metric_hint(phase.get("metrics", {}))
            suffix = f"  {hint}" if hint else ""
            count = f" x{phase['count']}" if phase["count"] > 1 else ""
            print(f"      {phase['phase']:<38.38} {fmt_ms(phase['totalMs']):>8}{count:<4}{suffix}")
    print()


def run(args):
    _, per_frame_ms = load_benchmark(args.benchmark)
    phase_events = jfr_events(args.jfr, [PHASE_EVENT])
    ledger_events = jfr_events(args.jfr, [FRAME_LEDGER_EVENT])
    marker_events = jfr_events(args.jfr, [SESSION_MARKER_EVENT])
    report = build_worst_frames(
        per_frame_ms,
        phase_events,
        marker_events,
        ledger_events,
        top_frames=args.top,
        phase_count=args.phase_count,
        thread_pattern=args.thread,
    )

    if args.json:
        json_output(report)
    else:
        print_report(report, args.benchmark, args.jfr)


def main():
    parser = argparse.ArgumentParser(
        description="Correlate benchmark worst frames with Java phase JFR events.",
    )
    parser.add_argument("--benchmark", required=True, help="Path to benchmark.json")
    parser.add_argument("--jfr", required=True, help="Path to profile.jfr")
    parser.add_argument(
        "--thread", "-t", default="^Render thread$|^main$", help="Thread name filter for JavaPhase events"
    )
    parser.add_argument("--top", "-n", type=int, default=20, help="Number of worst benchmark frames to show")
    parser.add_argument("--phase-count", type=int, default=10, help="Number of phase rows per frame")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    run(parser.parse_args())


if __name__ == "__main__":
    main()

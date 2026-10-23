#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Combine benchmark.json + profile.jfr + Tracy capture metadata into profile-data.json.

Missing inputs produce empty blocks (profiling is additive).
"""

import argparse
import csv
import io
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import TypedDict

from .jfr_parse import (
    event_timestamp_ms,
    jfr_events,
    jfr_summary_text,
    parse_summary_events,
    parse_timestamp,
    stack_frames,
    thread_name,
)

SESSION_MARKER_EVENT = "minecraft.Benchmark.SessionMarker"
FRAME_LEDGER_EVENT = "minecraft.FrameLedger"
CLIENT_TASK_EVENT = "minecraft.ClientTask"
CLIENT_TASK_DRAIN_EVENT = "minecraft.ClientTaskDrain"
JAVA_EXCEPTION_THROW_EVENT = "jdk.JavaExceptionThrow"
JAVA_ERROR_THROW_EVENT = "jdk.JavaErrorThrow"
CLIENT_THREAD_HINTS = ("Render thread", "Worker-Main-", "Server thread")
RECORDING_START_MARKER = "recording-start"
RECORDING_END_MARKER = "recording-end"
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
ANONYMOUS_ZONE_NAMES = {"", "???"}
MAX_ANONYMOUS_TRACY_PCT = 25.0
PROFILE_TOOL_TIMEOUT_SECONDS = int(os.environ.get("BENCHMARK_PROFILE_TOOL_TIMEOUT_SECONDS", "120"))

_ThrowableRow = TypedDict(
    "_ThrowableRow",
    {"type": str, "class": str, "topFrame": str, "thread": str, "count": int},
)


def load_benchmark(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"error: benchmark file is not valid JSON: {path}: {e}", file=sys.stderr)
        sys.exit(2)


def build_frame(bench):
    s = bench.get("summary", {})
    return {
        "avgMs": s.get("avgFrameTimeMs", 0.0),
        "p1Ms": s.get("p1FrameTimeMs", 0.0),
        # p1FrameTimeMs in today's benchmark.json is the 99th percentile (slowest 1%)
        # so reuse it for p99Ms.
        "p99Ms": s.get("p1FrameTimeMs", 0.0),
        "minMs": s.get("minFrameTimeMs", 0.0),
        "maxMs": s.get("maxFrameTimeMs", 0.0),
        "stddevMs": s.get("stddevFrameTimeMs", 0.0),
        "cvPct": s.get("cvPct", 0.0),
        "sections": s.get("sections", {}),
        "counters": s.get("counters", {}),
    }


def build_meta(bench, run):
    md = bench.get("metadata", {})
    return {
        "branch": md.get("gitBranch", "unknown"),
        "commit": md.get("gitCommit", "unknown"),
        "run": run,
        "sessionId": md.get("sessionId", ""),
    }


def empty_jfr(valid=False, reason="no JFR file"):
    return {
        "valid": valid,
        "validation": {"valid": valid, "reason": reason},
        "window": None,
        "hotspots": [],
        "allocations": [],
        "phases": [],
        "frameLedger": {"count": 0},
        "clientTasks": {"taskEventCount": 0, "drainEventCount": 0, "topTasks": [], "topDrains": []},
        "throwables": {"exceptionCount": 0, "errorCount": 0, "top": []},
        "gc": {"pauseCountPerSec": 0.0, "p99PauseMs": 0.0, "totalPauseMs": 0.0, "events": []},
        "locks": [],
        "threads": [],
    }


def empty_tracy():
    return {
        "zones": [],
        "gpu": [],
        "frameMarkers": [],
        "frames": 0,
        "window": None,
        "csvKind": None,
        "rawEventCount": None,
        "health": {"valid": False, "reason": "no Tracy trace file", "warnings": []},
    }


def _run_json_tool(module, *args):
    """Invoke a helper module; if it fails or lacks --json, return None."""
    try:
        out = subprocess.run(
            [sys.executable, "-m", f"{__package__}.{module}", *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
            timeout=PROFILE_TOOL_TIMEOUT_SECONDS,
        ).stdout
        return json.loads(out)
    except subprocess.CalledProcessError as e:
        print(f"warn: {module}.py {args}: exited {e.returncode}", file=sys.stderr)
        return None
    except subprocess.TimeoutExpired:
        print(f"warn: {module}.py {args}: timed out after {PROFILE_TOOL_TIMEOUT_SECONDS}s", file=sys.stderr)
        return None
    except json.JSONDecodeError as e:
        print(f"warn: {module}.py {args}: JSON parse failed: {e}", file=sys.stderr)
        return None


def _jfr_event_counts(jfr_path):
    summary = jfr_summary_text(jfr_path)
    return {name: count for name, count, _ in parse_summary_events(summary)}


def validate_jfr(jfr_path):
    """Return (is_valid, reason) for benchmark client JFR recordings."""
    try:
        event_counts = _jfr_event_counts(jfr_path)
    except Exception as e:
        return False, f"could not read JFR summary: {e}"

    if event_counts.get(SESSION_MARKER_EVENT, 0) > 0:
        return True, "benchmark session marker present"

    try:
        events = jfr_events(
            jfr_path,
            ["jdk.ExecutionSample", "jdk.NativeMethodSample", "jdk.ThreadStart"],
        )
        names = {thread_name(ev) for ev in events}
    except Exception as e:
        return False, f"missing benchmark session marker; could not inspect threads: {e}"

    for name in names:
        if any(hint in name for hint in CLIENT_THREAD_HINTS):
            return True, f"benchmark session marker absent, but Minecraft client thread '{name}' present"

    return False, "missing benchmark session marker and Minecraft client threads"


def benchmark_window(jfr_path):
    """Return a marker-derived time window dict, or None if unavailable."""
    try:
        markers = jfr_events(jfr_path, [SESSION_MARKER_EVENT])
    except Exception as e:
        print(f"warn: could not inspect benchmark markers: {e}", file=sys.stderr)
        return None

    starts = []
    ends = []
    for ev in markers:
        vals = ev.get("values", {})
        marker = vals.get("marker")
        timestamp = vals.get("startTime")
        if not timestamp:
            continue
        if marker == RECORDING_START_MARKER:
            starts.append(timestamp)
        elif marker == RECORDING_END_MARKER:
            ends.append(timestamp)

    if not starts or not ends:
        return None

    after = starts[0]
    before = next((ts for ts in ends if ts >= after), ends[-1])
    return {
        "after": after,
        "before": before,
        "source": SESSION_MARKER_EVENT,
        "startMarker": RECORDING_START_MARKER,
        "endMarker": RECORDING_END_MARKER,
    }


def window_args(window):
    if not window:
        return []
    return ["--after", window["after"], "--before", window["before"]]


def _windowed_events(jfr_path, event_types, window):
    events = jfr_events(jfr_path, event_types)
    if not window:
        return events
    after_ms = parse_timestamp(window.get("after"))
    before_ms = parse_timestamp(window.get("before"))
    result = []
    for event in events:
        timestamp_ms = event_timestamp_ms(event)
        if timestamp_ms <= 0:
            continue
        if after_ms and timestamp_ms < after_ms:
            continue
        if before_ms and timestamp_ms > before_ms:
            continue
        result.append(event)
    return result


def _ns_to_ms(nanos):
    return round((float(nanos or 0) / 1_000_000.0), 3)


def _avg(values):
    return sum(values) / len(values) if values else 0.0


def _class_name(value):
    if isinstance(value, dict):
        name = value.get("name") or value.get("type") or ""
    else:
        name = str(value or "")
    return name.replace("/", ".") or "unknown"


LEDGER_NANOS_FIELDS = (
    "fullFrameNanos",
    "minecraftRenderNanos",
    "minecraftRenderTopLevelNanos",
    "minecraftRenderUnattributedNanos",
    "minecraftPreGameRendererNanos",
    "minecraftGameRendererNanos",
    "minecraftPostGameRendererNanos",
    "minecraftRunTasksNanos",
    "minecraftTickNanos",
    "worldRendererNanos",
    "worldRendererPhaseNanos",
    "worldRendererUnattributedNanos",
    "preWorldRenderEndNanos",
    "worldRenderEndNanos",
    "renderAndSubmitFrameNanos",
    "updateVisibleChunksNanos",
    "chunkGenNanos",
    "chunkDrawNanos",
    "entitiesNanos",
    "skyNanos",
    "atlasNanos",
    "submitNanos",
    "gcAssetStoresNanos",
    "taskNanos",
    "maxTaskNanos",
)


LEDGER_COUNT_FIELDS = (
    "taskDrainCount",
    "taskCount",
    "slowTaskCount",
    "maxTaskQueueDepth",
)


def _ms_key(field):
    return field[:-5] + "Ms" if field.endswith("Nanos") else field


def build_frame_ledger(jfr_path, window):
    try:
        events = _windowed_events(jfr_path, [FRAME_LEDGER_EVENT], window)
    except Exception as e:
        print(f"warn: could not read frame ledger events: {e}", file=sys.stderr)
        return {"count": 0}

    if not events:
        return {"count": 0}

    rows = [event.get("values", {}) for event in events]
    avg_ms = {}
    max_ms = {}
    for field in LEDGER_NANOS_FIELDS:
        values = [int(row.get(field) or 0) for row in rows]
        avg_ms[_ms_key(field)] = _ns_to_ms(_avg(values))
        max_ms[_ms_key(field)] = _ns_to_ms(max(values) if values else 0)

    avg_counts = {}
    max_counts = {}
    for field in LEDGER_COUNT_FIELDS:
        values = [int(row.get(field) or 0) for row in rows]
        avg_counts[field] = round(_avg(values), 3)
        max_counts[field] = max(values) if values else 0

    def mystery_cost(row):
        return int(row.get("minecraftRenderUnattributedNanos") or 0) + int(
            row.get("worldRendererUnattributedNanos") or 0
        )

    worst = []
    for row in sorted(rows, key=mystery_cost, reverse=True)[:20]:
        worst.append(
            {
                "frameIndex": row.get("frameIndex"),
                "fullFrameMs": _ns_to_ms(row.get("fullFrameNanos")),
                "preWorldRenderEndMs": _ns_to_ms(row.get("preWorldRenderEndNanos")),
                "minecraftRenderUnattributedMs": _ns_to_ms(row.get("minecraftRenderUnattributedNanos")),
                "worldRendererUnattributedMs": _ns_to_ms(row.get("worldRendererUnattributedNanos")),
                "runTasksMs": _ns_to_ms(row.get("minecraftRunTasksNanos")),
                "taskCount": int(row.get("taskCount") or 0),
                "slowTaskCount": int(row.get("slowTaskCount") or 0),
                "maxTaskMs": _ns_to_ms(row.get("maxTaskNanos")),
                "maxTaskName": row.get("maxTaskName") or "",
            }
        )

    return {
        "count": len(events),
        "avgMs": avg_ms,
        "maxMs": max_ms,
        "avgCounts": avg_counts,
        "maxCounts": max_counts,
        "worstUnattributedFrames": worst,
    }


def build_client_tasks(jfr_path, window):
    try:
        task_events = _windowed_events(jfr_path, [CLIENT_TASK_EVENT], window)
        drain_events = _windowed_events(jfr_path, [CLIENT_TASK_DRAIN_EVENT], window)
    except Exception as e:
        print(f"warn: could not read client task events: {e}", file=sys.stderr)
        return {"taskEventCount": 0, "drainEventCount": 0, "topTasks": [], "topDrains": []}

    task_buckets = {}
    for event in task_events:
        values = event.get("values", {})
        name = values.get("taskName") or "(unknown)"
        row = task_buckets.setdefault(
            name,
            {
                "taskName": name,
                "executorName": values.get("executorName") or "",
                "count": 0,
                "totalMs": 0.0,
                "maxMs": 0.0,
                "maxQueueDepthAfterRemove": 0,
            },
        )
        duration_ms = _ns_to_ms(values.get("durationNanos"))
        row["count"] += 1
        row["totalMs"] += duration_ms
        row["maxMs"] = max(row["maxMs"], duration_ms)
        row["maxQueueDepthAfterRemove"] = max(
            row["maxQueueDepthAfterRemove"],
            int(values.get("queueDepthAfterRemove") or 0),
        )

    top_tasks = []
    for row in sorted(task_buckets.values(), key=lambda r: r["totalMs"], reverse=True)[:30]:
        row = dict(row)
        row["totalMs"] = round(row["totalMs"], 3)
        row["avgMs"] = round(row["totalMs"] / row["count"], 3) if row["count"] else 0.0
        top_tasks.append(row)

    drains = [event.get("values", {}) for event in drain_events]
    drain_nanos = [int(row.get("drainNanos") or 0) for row in drains]
    task_counts = [int(row.get("taskCount") or 0) for row in drains]
    slow_counts = [int(row.get("slowTaskCount") or 0) for row in drains]
    top_drains = []
    for row in sorted(drains, key=lambda r: int(r.get("drainNanos") or 0), reverse=True)[:20]:
        top_drains.append(
            {
                "frameIndex": row.get("frameIndex"),
                "executorName": row.get("executorName") or "",
                "drainMs": _ns_to_ms(row.get("drainNanos")),
                "taskMs": _ns_to_ms(row.get("taskNanos")),
                "taskCount": int(row.get("taskCount") or 0),
                "slowTaskCount": int(row.get("slowTaskCount") or 0),
                "maxTaskMs": _ns_to_ms(row.get("maxTaskNanos")),
                "maxTaskName": row.get("maxTaskName") or "",
                "initialQueueDepth": int(row.get("initialQueueDepth") or 0),
                "endQueueDepth": int(row.get("endQueueDepth") or 0),
                "maxQueueDepth": int(row.get("maxQueueDepth") or 0),
            }
        )

    return {
        "taskEventCount": len(task_events),
        "drainEventCount": len(drain_events),
        "avgDrainMs": _ns_to_ms(_avg(drain_nanos)),
        "maxDrainMs": _ns_to_ms(max(drain_nanos) if drain_nanos else 0),
        "avgTasksPerDrain": round(_avg(task_counts), 3),
        "maxTasksPerDrain": max(task_counts) if task_counts else 0,
        "avgSlowTasksPerDrain": round(_avg(slow_counts), 3),
        "maxSlowTasksPerDrain": max(slow_counts) if slow_counts else 0,
        "topTasks": top_tasks,
        "topDrains": top_drains,
    }


def build_throwables(jfr_path, window):
    try:
        exception_events = _windowed_events(jfr_path, [JAVA_EXCEPTION_THROW_EVENT], window)
        error_events = _windowed_events(jfr_path, [JAVA_ERROR_THROW_EVENT], window)
    except Exception as e:
        print(f"warn: could not read throwable events: {e}", file=sys.stderr)
        return {"exceptionCount": 0, "errorCount": 0, "top": []}

    buckets: defaultdict[tuple[str, str, str], _ThrowableRow] = defaultdict(
        lambda: {
            "type": "",
            "class": "",
            "topFrame": "",
            "thread": "",
            "count": 0,
        }
    )

    def throwable_site(event):
        frames = stack_frames(event, simple=False)
        for frame in frames:
            if not frame.startswith("java.lang."):
                return frame
        return frames[0] if frames else ""

    def add(events, event_kind):
        for event in events:
            values = event.get("values", {})
            clazz = _class_name(values.get("thrownClass") or values.get("throwable") or values.get("exception"))
            top_frame = throwable_site(event)
            key = (event_kind, clazz, top_frame)
            row = buckets[key]
            row["type"] = event_kind
            row["class"] = clazz
            row["topFrame"] = top_frame
            row["thread"] = thread_name(event)
            row["count"] += 1

    add(exception_events, "exception")
    add(error_events, "error")
    return {
        "exceptionCount": len(exception_events),
        "errorCount": len(error_events),
        "top": sorted(buckets.values(), key=lambda r: r["count"], reverse=True)[:30],
    }


def build_jfr(jfr_path):
    if not jfr_path or not Path(jfr_path).exists():
        return empty_jfr()

    valid, reason = validate_jfr(jfr_path)
    if not valid:
        print(f"warn: ignoring invalid benchmark JFR: {reason}", file=sys.stderr)
        return empty_jfr(valid=False, reason=reason)

    block = empty_jfr()
    block["valid"] = True
    block["validation"] = {"valid": True, "reason": reason}
    window = benchmark_window(jfr_path)
    block["window"] = window
    common_args = window_args(window)

    if d := _run_json_tool("jfr_hotspots", str(jfr_path), "--json", "-n", "50", *common_args):
        block["hotspots"] = [
            {
                "method": h.get("method", ""),
                "selfMs": h.get("selfMs", 0.0),
                "totalMs": h.get("totalMs", 0.0),
                "thread": h.get("thread"),
                "package": h.get("package"),
            }
            for h in d.get("hotspots", [])
        ]

    if d := _run_json_tool("jfr_alloc", str(jfr_path), "--json", "--by", "size", "-n", "50", *common_args):
        block["allocations"] = [
            {"class": a.get("class", ""), "site": a.get("site"), "count": a.get("count", 0), "bytes": a.get("bytes", 0)}
            for a in d.get("allocations", [])
        ]

    # Deep enough to survive splitting phases by thread, measured at 126 rows on a full run.
    # At 50 the cap silently evicted real render-thread phases (applyFrustum, Sky,
    # MinecraftClient.tick) once background threads contributed rows of their own.
    if d := _run_json_tool("jfr_phase_summary", str(jfr_path), "--json", "-n", "250", *common_args):
        block["phases"] = d

    block["frameLedger"] = build_frame_ledger(jfr_path, window)
    block["clientTasks"] = build_client_tasks(jfr_path, window)
    block["throwables"] = build_throwables(jfr_path, window)

    if d := _run_json_tool("jfr_gc", str(jfr_path), "--json", *common_args):
        block["gc"]["pauseCountPerSec"] = d.get("pauseCountPerSec", 0.0)
        block["gc"]["p99PauseMs"] = d.get("p99PauseMs", 0.0)
        block["gc"]["totalPauseMs"] = d.get("totalPauseMs", 0.0)
        block["gc"]["events"] = d.get("events", [])

    if d := _run_json_tool("jfr_locks", str(jfr_path), "--json", "-n", "30", *common_args):
        block["locks"] = d.get("locks", [])

    if d := _run_json_tool("jfr_threads", str(jfr_path), "--json", *common_args):
        block["threads"] = d.get("threads", [])

    return block


def _tracy_health_from_logs(tracy_path):
    health = {"valid": True, "reason": "capture log looked clean", "warnings": []}
    if not tracy_path:
        health["valid"] = False
        health["reason"] = "no Tracy trace file"
        return health

    trace = Path(tracy_path)
    if not trace.exists() or trace.stat().st_size == 0:
        health["valid"] = False
        health["reason"] = "missing Tracy trace file"
        health["warnings"].append(health["reason"])

    base = trace.parent
    out_log = base / "profile.tracy.out.log"
    err_log = base / "profile.tracy.err.log"

    if out_log.exists():
        text = out_log.read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            if "Instrumentation failure:" in line:
                clean = ANSI_RE.sub("", line).strip()
                health["valid"] = False
                health["reason"] = clean
                health["warnings"].append(clean)
                break
        if "Saving trace" not in text:
            health["warnings"].append("capture log did not report trace save completion")
    else:
        health["warnings"].append("missing Tracy capture stdout log")

    if err_log.exists() and err_log.stat().st_size:
        health["valid"] = False
        health["warnings"].append("Tracy capture stderr is non-empty")

    if health["valid"] and health["warnings"]:
        health["reason"] = "; ".join(health["warnings"])
    return health


def _csv_int(value):
    try:
        return int(float(value or 0))
    except TypeError, ValueError:
        return 0


def _detect_csv_delimiter(text):
    header = text.splitlines()[0] if text else ""
    return "\t" if "\t" in header else ","


def _tracy_csv_quality(tracy_csv):
    path = Path(tracy_csv) if tracy_csv else None
    if not path or not path.exists():
        return None

    rows = 0
    named_rows = 0
    total_count = 0
    anonymous_count = 0
    total_ns = 0
    anonymous_ns = 0
    text = path.read_text(encoding="utf-8")
    reader = csv.DictReader(io.StringIO(text), delimiter=_detect_csv_delimiter(text))
    if reader.fieldnames is None:
        return None
    fieldnames = set(reader.fieldnames or [])
    has_counts = "counts" in fieldnames
    has_total_ns = "total_ns" in fieldnames
    for row in reader:
        rows += 1
        name = (row.get("name") or "").strip()
        is_anonymous = name in ANONYMOUS_ZONE_NAMES
        if not is_anonymous:
            named_rows += 1

        count = _csv_int(row.get("counts")) if has_counts else 1
        if count <= 0:
            count = 1
        total_count += count
        if is_anonymous:
            anonymous_count += count

        ns = _csv_int(row.get("total_ns")) if has_total_ns else 0
        total_ns += ns
        if is_anonymous:
            anonymous_ns += ns

    pct_basis = total_ns if total_ns > 0 else total_count
    anonymous_basis = anonymous_ns if total_ns > 0 else anonymous_count
    anonymous_pct = (anonymous_basis / pct_basis * 100.0) if pct_basis else 0.0
    anonymous_count_pct = (anonymous_count / total_count * 100.0) if total_count else 0.0
    return {
        "rows": rows,
        "namedRows": named_rows,
        "totalCount": total_count,
        "anonymousCount": anonymous_count,
        "totalNs": total_ns,
        "anonymousNs": anonymous_ns,
        "anonymousPct": round(anonymous_pct, 3),
        "anonymousCountPct": round(anonymous_count_pct, 3),
    }


def _apply_tracy_csv_quality(health, tracy_csv):
    quality = _tracy_csv_quality(tracy_csv)
    if not quality:
        return health

    health["csvQuality"] = quality
    if quality["rows"] and quality["namedRows"] == 0:
        warning = "Tracy CSV has no named zones."
        health["valid"] = False
        health["warnings"].append(warning)
        health["reason"] = warning
    elif quality["anonymousPct"] >= MAX_ANONYMOUS_TRACY_PCT:
        warning = f"Tracy CSV is {quality['anonymousPct']:.1f}% anonymous zones (???); trace is not useful."
        health["valid"] = False
        health["warnings"].append(warning)
        health["reason"] = warning
    elif health["valid"] and health["warnings"]:
        health["reason"] = "; ".join(health["warnings"])
    return health


def _record_frame_count(bench):
    per_frame = bench.get("perFrame") or []
    if per_frame:
        return len(per_frame)
    try:
        return int(bench.get("metadata", {}).get("recordFrames") or 0)
    except TypeError, ValueError:
        return 0


def build_tracy(tracy_path=None, tracy_csv=None, bench=None, expected=True):
    record_frames = _record_frame_count(bench or {})
    tracy_path = tracy_path or tracy_csv
    if not expected and not (tracy_path and Path(tracy_path).exists()) and not (tracy_csv and Path(tracy_csv).exists()):
        block = empty_tracy()
        block["frames"] = record_frames
        block["health"] = {"valid": True, "reason": "Tracy capture disabled for this run", "warnings": []}
        return block

    health = _apply_tracy_csv_quality(_tracy_health_from_logs(tracy_path), tracy_csv)
    block = empty_tracy()
    block["frames"] = record_frames
    block["health"] = health

    if not tracy_csv or not Path(tracy_csv).exists():
        return block

    args = [str(tracy_csv), "--compact-json"]
    if record_frames:
        args += ["--record-frames", str(record_frames)]
    if d := _run_json_tool("tracy_analyze", *args):
        detected_frames = d.get("detectedFrames")
        frame_source = d.get("frameSource")
        if d.get("csvKind") == "summary" and record_frames and detected_frames and detected_frames != record_frames:
            warning = (
                f"Tracy summary CSV frame source {frame_source or 'unknown'} counted "
                f"{detected_frames} frames while benchmark.json recorded {record_frames}; "
                "zone totals are not windowed to the benchmark recording interval."
            )
            health["warnings"].append(warning)
            if health.get("valid", False):
                health["reason"] = warning
        return {
            "zones": d.get("zones", []),
            "gpu": d.get("gpu", []),
            "frameMarkers": d.get("frameMarkers", []),
            "frames": d.get("frames", 0),
            "window": d.get("window"),
            "detectedFrames": detected_frames,
            "frameSource": frame_source,
            "csvKind": d.get("csvKind"),
            "rawEventCount": d.get("rawEventCount"),
            "health": health,
        }
    return block


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--benchmark", required=True, help="Path to benchmark.json")
    p.add_argument("--jfr", help="Path to profile.jfr (optional)")
    p.add_argument("--tracy", help="Path to raw profile.tracy capture (optional)")
    p.add_argument("--tracy-csv", help="Path to Tracy CSV export (legacy/manual, optional)")
    p.add_argument("--tracy-optional", action="store_true", help="do not mark missing Tracy artifacts as invalid")
    p.add_argument("--run", type=int, default=1)
    p.add_argument("--out", required=True, help="Output profile-data.json path")
    args = p.parse_args()

    if not Path(args.benchmark).exists():
        print(f"error: benchmark file not found: {args.benchmark}", file=sys.stderr)
        sys.exit(2)

    bench = load_benchmark(args.benchmark)
    doc = {
        "schemaVersion": 1,
        "kind": "profile-data",
        "meta": build_meta(bench, args.run),
        "frame": build_frame(bench),
        "jfr": build_jfr(args.jfr),
        "tracy": build_tracy(args.tracy, args.tracy_csv, bench, expected=not args.tracy_optional),
    }
    if args.jfr and doc["jfr"].get("valid"):
        if d := _run_json_tool(
            "jfr_worst_frames",
            "--benchmark",
            args.benchmark,
            "--jfr",
            args.jfr,
            "--json",
            "-n",
            "20",
            "--phase-count",
            "12",
        ):
            doc["jfr"]["worstFrames"] = d
    if "perFrame" in bench:
        doc["perFrame"] = bench["perFrame"]
    Path(args.out).write_text(json.dumps(doc, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

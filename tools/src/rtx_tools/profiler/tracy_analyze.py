#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Tracy CSV Analysis -- per-frame breakdown of Tracy profiler exports.

Parses inclusive and/or self-time CSV files exported by Tracy's
``csvexport`` tool and prints a sorted per-frame time breakdown.
For summary exports, frame count is inferred from frame-like zones because
Tracy frame marks are not present in the aggregate CSV.

Usage:
    python -m rtx_tools.profiler.tracy_analyze inclusive.csv
    python -m rtx_tools.profiler.tracy_analyze inclusive.csv self.csv
    python -m rtx_tools.profiler.tracy_analyze inclusive.csv self.csv --min-ms 0.05
    python -m rtx_tools.profiler.tracy_analyze inclusive.csv --json
"""

import argparse
import csv
import io
import math
import sys
from pathlib import Path

FRAME_MARKER_CANDIDATES = (
    "MinecraftClient.render.postFrame",
    "MinecraftClient.render.limitDisplayFPS",
    "MinecraftClient.render",
    "WorldRender.END",
    "renderAndSubmitFrame",
    "dxvk::D3D9DeviceEx::Present",
    "dxvk::D3D9DeviceEx::PresentEx",
    "Present",
)

WINDOW_MARKER_NAMES = {
    "Benchmark.recording",
    "Benchmark.recording-start",
    "Benchmark.recording-end",
    "benchmark.recording-start",
    "benchmark.recording-end",
}


def _dict_reader(text):
    if text.startswith("\ufeff"):
        text = text[1:]
    return csv.DictReader(io.StringIO(text), delimiter=_detect_delimiter(text))


def _detect_delimiter(text):
    header = text.splitlines()[0] if text else ""
    return "\t" if "\t" in header else ","


def _is_event_export(fieldnames):
    return fieldnames and "ns_since_start" in fieldnames and "exec_time_ns" in fieldnames


def parse_summary_csv(text):
    """Parse a Tracy aggregate CSV export into a list of zone dicts."""
    rows = []
    reader = _dict_reader(text)
    for r in reader:
        try:
            rows.append(
                {
                    "name": r.get("name", ""),
                    "src": (r.get("src_file") or "") + ":" + (r.get("src_line") or ""),
                    "total_ns": int(r.get("total_ns") or 0),
                    "count": int(r.get("counts") or 0),
                    "mean_ns": int(float(r.get("mean_ns") or 0)),
                    "max_ns": int(r.get("max_ns") or 0),
                }
            )
        except ValueError, TypeError:
            continue
    rows.sort(key=lambda row: row["total_ns"], reverse=True)
    return rows, {"kind": "summary"}


def parse_event_csv(text):
    """Parse a Tracy -u CSV export into individual zone events."""
    rows = []
    reader = _dict_reader(text)
    for r in reader:
        try:
            rows.append(
                {
                    "name": r.get("name", ""),
                    "src_file": r.get("src_file") or "",
                    "src_line": r.get("src_line") or "",
                    "start_ns": int(r.get("ns_since_start") or 0),
                    "duration_ns": int(r.get("exec_time_ns") or 0),
                }
            )
        except ValueError, TypeError:
            continue
    return rows


def choose_event_window(events, record_frames=0, frame_marker=""):
    if not record_frames or record_frames <= 0:
        return None

    recordings = [r for r in events if r["name"] == "Benchmark.recording" and r["duration_ns"] > 0]
    if recordings:
        recording = recordings[-1]
        return {
            "source": "Benchmark.recording",
            "startNs": recording["start_ns"],
            "endNs": recording["start_ns"] + recording["duration_ns"],
            "totalFrames": record_frames,
            "selectedFrames": record_frames,
        }

    start_names = {"Benchmark.recording-start", "benchmark.recording-start"}
    end_names = {"Benchmark.recording-end", "benchmark.recording-end"}
    starts = [r for r in events if r["name"] in start_names]
    ends = [r for r in events if r["name"] in end_names]
    if starts and ends:
        end_marker = ends[-1]
        start_marker = None
        for candidate in reversed(starts):
            if candidate["start_ns"] <= end_marker["start_ns"]:
                start_marker = candidate
                break
        if start_marker:
            return {
                "source": "benchmark.recording-start/end",
                "startNs": start_marker["start_ns"] + start_marker["duration_ns"],
                "endNs": end_marker["start_ns"],
                "totalFrames": record_frames,
                "selectedFrames": record_frames,
            }

    candidates = (frame_marker,) if frame_marker else FRAME_MARKER_CANDIDATES
    for marker in candidates:
        markers = [r for r in events if r["name"] == marker]
        if len(markers) < record_frames:
            continue

        first_index = len(markers) - record_frames
        previous = markers[first_index - 1] if first_index > 0 else None
        start_ns = (previous["start_ns"] + previous["duration_ns"]) if previous else markers[first_index]["start_ns"]
        end_ns = markers[-1]["start_ns"] + markers[-1]["duration_ns"]
        return {
            "source": marker,
            "startNs": start_ns,
            "endNs": end_ns,
            "totalFrames": len(markers),
            "selectedFrames": record_frames,
        }
    return None


def _std_ns(values, mean_ns):
    if len(values) <= 1:
        return 0
    return int(math.sqrt(sum((v - mean_ns) ** 2 for v in values) / len(values)))


def summarize_event_csv(text, record_frames=0, frame_marker=""):
    events = parse_event_csv(text)
    window = choose_event_window(events, record_frames, frame_marker)
    if window:
        start_ns = window["startNs"]
        end_ns = window["endNs"]
        events = [r for r in events if start_ns <= r["start_ns"] < end_ns]

    grouped = {}
    for ev in events:
        if ev["name"] in WINDOW_MARKER_NAMES:
            continue
        key = (ev["name"], ev["src_file"], ev["src_line"])
        grouped.setdefault(key, []).append(ev["duration_ns"])

    total_all_ns = sum(sum(values) for values in grouped.values()) or 1
    rows = []
    for (name, src_file, src_line), values in grouped.items():
        total_ns = sum(values)
        count = len(values)
        mean_ns = int(total_ns / count) if count else 0
        rows.append(
            {
                "name": name,
                "src": f"{src_file}:{src_line}",
                "total_ns": total_ns,
                "count": count,
                "mean_ns": mean_ns,
                "min_ns": min(values) if values else 0,
                "max_ns": max(values) if values else 0,
                "std_ns": _std_ns(values, mean_ns),
                "total_perc": total_ns / total_all_ns * 100.0,
            }
        )
    rows.sort(key=lambda r: r["total_ns"], reverse=True)
    frames = (window or {}).get("selectedFrames") or detect_frames(rows)
    return rows, {
        "kind": "events",
        "rawEventCount": len(events),
        "frames": frames,
        "window": window,
    }


def parse_csv(text, record_frames=0, frame_marker=""):
    """Parse either Tracy aggregate CSV or Tracy -u event CSV."""
    reader = _dict_reader(text)
    if _is_event_export(reader.fieldnames):
        return summarize_event_csv(text, record_frames, frame_marker)
    rows, meta = parse_summary_csv(text)
    detected_frames, frame_source = detect_frame_count(rows)
    meta["detectedFrames"] = detected_frames
    meta["frameSource"] = frame_source
    meta["frames"] = record_frames if record_frames and record_frames > 0 else detected_frames
    return rows, meta


def detect_frame_count(rows):
    """Return ``(count, source_zone)`` from the best frame-like zone in rows."""
    for marker in FRAME_MARKER_CANDIDATES:
        for r in rows:
            if r["name"] == marker:
                return r["count"], marker
    return 1, "fallback"


def detect_frames(rows):
    """Detect frame count from the best available frame-like zone."""
    return detect_frame_count(rows)[0]


def run(args):
    inclusive_text = ""
    selftime_text = ""

    if args.inclusive:
        inclusive_text = Path(args.inclusive).read_text(encoding="utf-8")
    if args.selftime:
        selftime_text = Path(args.selftime).read_text(encoding="utf-8")

    inc_rows, inc_meta = (
        parse_csv(inclusive_text, args.record_frames, args.frame_marker) if inclusive_text else ([], {})
    )
    self_rows, self_meta = (
        parse_csv(selftime_text, args.record_frames, args.frame_marker) if selftime_text else ([], {})
    )

    frames = inc_meta.get("frames") or self_meta.get("frames") or detect_frames(inc_rows or self_rows)

    if args.compact_json:
        import json

        zones = []
        compact_rows = inc_rows
        if args.compact_zone_limit and args.compact_zone_limit > 0:
            compact_rows = compact_rows[: args.compact_zone_limit]
        for r in compact_rows:
            zones.append(
                {
                    "name": r["name"],
                    "count": r["count"],
                    "meanUs": round(r["mean_ns"] / 1000, 3),
                    "maxUs": round(r["max_ns"] / 1000, 3),
                    "totalMs": round(r["total_ns"] / 1_000_000, 3),
                }
            )
        out = {
            "zones": zones,
            "gpu": [],
            "frameMarkers": [],
            "frames": frames,
            "window": inc_meta.get("window"),
            "detectedFrames": inc_meta.get("detectedFrames"),
            "frameSource": inc_meta.get("frameSource"),
            "rawEventCount": inc_meta.get("rawEventCount"),
            "csvKind": inc_meta.get("kind", "summary"),
        }
        print(json.dumps(out, indent=2))
        return

    if args.json:
        import json

        out = {"frames": frames, "inclusive": [], "self": []}
        for r in inc_rows:
            per_frame_ms = r["total_ns"] / frames / 1_000_000
            if per_frame_ms >= args.min_ms:
                out["inclusive"].append(
                    {
                        "name": r["name"],
                        "per_frame_ms": round(per_frame_ms, 3),
                        "calls_per_frame": round(r["count"] / frames, 1),
                        "mean_us": round(r["mean_ns"] / 1000, 1),
                    }
                )
        for r in self_rows:
            per_frame_ms = r["total_ns"] / frames / 1_000_000
            if per_frame_ms >= args.min_ms:
                out["self"].append(
                    {
                        "name": r["name"],
                        "per_frame_ms": round(per_frame_ms, 3),
                        "calls_per_frame": round(r["count"] / frames, 1),
                        "mean_us": round(r["mean_ns"] / 1000, 1),
                    }
                )
        json.dump(out, sys.stdout, indent=2)
        print()
        return

    print("=" * 80)
    print(f" TRACY FRAME ANALYSIS ({frames} frames captured)")
    print("=" * 80)

    present_mean_ms = 0
    for r in inc_rows or self_rows:
        if "Present" in r["name"]:
            present_mean_ms = r["mean_ns"] / 1_000_000
            break

    if present_mean_ms > 0:
        print(f"\n  Frame time: {present_mean_ms:.2f}ms  ({1000 / present_mean_ms:.1f} FPS)")

    if self_rows:
        self_rows.sort(key=lambda r: r["total_ns"], reverse=True)
        total_frame_ns = 0
        for r in self_rows:
            if "Present" in r["name"]:
                total_frame_ns = r["total_ns"] / frames
                break

        print(f"\n  {'SELF-TIME /frame':>22}  {'%frame':>7}  {'calls/f':>8}  {'us/call':>8}  Zone")
        print("  " + "-" * 100)

        for r in self_rows[: args.top]:
            per_frame_ns = r["total_ns"] / frames
            per_frame_ms = per_frame_ns / 1_000_000
            if per_frame_ms < args.min_ms:
                continue
            calls_per_frame = r["count"] / frames
            us_per_call = r["mean_ns"] / 1000
            pct = (per_frame_ns / total_frame_ns * 100) if total_frame_ns else 0
            name = r["name"]
            if len(name) > 60:
                name = "..." + name[-57:]
            print(f"  {per_frame_ms:8.2f}ms  {pct:6.1f}%  {calls_per_frame:8.0f}  {us_per_call:8.1f}  {name}")

    if inc_rows:
        inc_rows.sort(key=lambda r: r["total_ns"], reverse=True)
        print(f"\n  {'INCLUSIVE /frame':>22}  {'ms/call':>8}  {'calls/f':>8}  Zone")
        print("  " + "-" * 100)

        for r in inc_rows[: args.top]:
            per_frame_ms = r["total_ns"] / frames / 1_000_000
            if per_frame_ms < max(args.min_ms, 0.1):
                continue
            calls_per_frame = r["count"] / frames
            ms_per_call = r["mean_ns"] / 1_000_000
            name = r["name"]
            if len(name) > 60:
                name = "..." + name[-57:]
            print(f"  {per_frame_ms:8.2f}ms  {ms_per_call:8.2f}  {calls_per_frame:8.0f}  {name}")

    print()


def main():
    parser = argparse.ArgumentParser(
        description="Analyze Tracy CSV exports with per-frame breakdowns.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Tracy CSV export:
  csvexport.exe trace.tracy > inclusive.csv
  csvexport.exe -s trace.tracy > selftime.csv

Examples:
  python -m rtx_tools.profiler.tracy_analyze inclusive.csv
  python -m rtx_tools.profiler.tracy_analyze inclusive.csv selftime.csv
  python -m rtx_tools.profiler.tracy_analyze inclusive.csv selftime.csv --min-ms 0.05 -n 50""",
    )
    parser.add_argument("inclusive", nargs="?", default=None, help="Path to inclusive-time CSV (from csvexport)")
    parser.add_argument("selftime", nargs="?", default=None, help="Path to self-time CSV (from csvexport -s)")
    parser.add_argument("--min-ms", type=float, default=0.01, help="Minimum per-frame ms to display (default: 0.01)")
    parser.add_argument("--top", "-n", type=int, default=50, help="Top N zones to show (default: 50)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument(
        "--compact-json",
        action="store_true",
        help="Emit zones in the profile-schema shape (for generate_profile_data.py).",
    )
    parser.add_argument(
        "--compact-zone-limit", type=int, default=500, help="Maximum zones to emit with --compact-json; 0 keeps all."
    )
    parser.add_argument(
        "--record-frames",
        type=int,
        default=0,
        help="For Tracy -u exports, summarize only the last N frame-marker intervals.",
    )
    parser.add_argument("--frame-marker", default="", help="Frame marker zone name to use with --record-frames.")
    run(parser.parse_args())


if __name__ == "__main__":
    main()

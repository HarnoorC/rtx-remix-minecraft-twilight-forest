#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Aggregate N profile-data.json files (run_1/, run_2/, ...) into one aggregate.json.

Frame stats: averaged across runs.
JFR hotspots / allocations / locks / threads: merged by key; numeric values averaged.
Tracy zones: merged by name; numeric values averaged.
GC: scalar fields averaged; events concatenated.
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path


def mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def _mean_or_none(xs):
    """Mean over the values that exist, or None when a row has no per-frame figure at all."""
    present = [x for x in xs if x is not None]
    return round(mean(present), 3) if present else None


# A single frame longer than this is a stall/hang (world load, shader
# compilation, a one-off hitch), not a representative render frame. A run whose
# worst frame exceeds it is excluded from the headline cross-run aggregate so one
# degenerate run cannot fabricate a regression. Such runs are still kept in
# perRun and reported via excludedRunCount/excludedRuns.
DEGENERATE_MAX_FRAME_MS = 5000.0


def _is_degenerate_run(run):
    max_ms = (run.get("frame") or {}).get("maxMs")
    return isinstance(max_ms, (int, float)) and not isinstance(max_ms, bool) and max_ms > DEGENERATE_MAX_FRAME_MS


def load_runs(input_dir):
    runs = []
    for d in sorted(Path(input_dir).iterdir()):
        if d.is_dir() and d.name.startswith("run_"):
            f = d / "profile-data.json"
            if f.exists():
                runs.append(json.loads(f.read_text(encoding="utf-8")))
    return runs


def agg_frame(runs):
    excluded = [r for r in runs if _is_degenerate_run(r)]
    valid = [r for r in runs if not _is_degenerate_run(r)]
    # Aggregate over the healthy runs. If every run is degenerate, fall back to
    # all of them so we still emit numbers (flagged via allRunsDegenerate) rather
    # than nothing.
    agg_runs = valid or runs
    fields = ["avgMs", "p1Ms", "p99Ms", "minMs", "maxMs", "stddevMs", "cvPct"]
    out = {k: round(mean([r["frame"].get(k, 0.0) for r in agg_runs]), 3) for k in fields}
    out["runsTotal"] = len(runs)
    out["runsAggregated"] = len(agg_runs)
    out["excludedRunCount"] = len(runs) - len(agg_runs)
    if excluded:
        out["excludedRuns"] = [
            {
                "run": (r.get("meta") or {}).get("run"),
                "maxMs": round(float((r.get("frame") or {}).get("maxMs") or 0.0), 3),
            }
            for r in excluded
        ]
        out["allRunsDegenerate"] = not valid
    sections = defaultdict(list)
    for r in agg_runs:
        for k, v in r["frame"].get("sections", {}).items():
            sections[k].append(v)
    section_fields = ("avgMs", "pct", "minMs", "p50Ms", "p95Ms", "p99Ms", "maxMs")
    out["sections"] = {k: aggregate_frame_value(vs, section_fields) for k, vs in sections.items()}
    counters = defaultdict(list)
    for r in agg_runs:
        for k, v in r["frame"].get("counters", {}).items():
            counters[k].append(v)
    out["counters"] = {k: aggregate_frame_value(vs, ("avg",)) for k, vs in counters.items()}
    return out


def aggregate_frame_value(values, dict_fields):
    if all(isinstance(v, dict) for v in values):
        return {field: round(mean([v.get(field, 0.0) for v in values]), 3) for field in dict_fields}
    if all(isinstance(v, (int, float, bool)) for v in values):
        return {"avg": round(mean([float(v) for v in values]), 3)}
    return {"value": values[-1] if values else None}


def agg_hotspots(runs):
    by_method = defaultdict(list)
    for r in runs:
        for h in r["jfr"].get("hotspots", []):
            by_method[h["method"]].append(h)
    out = []
    for method, hs in by_method.items():
        out.append(
            {
                "method": method,
                "selfMs": round(mean([h["selfMs"] for h in hs]), 3),
                "totalMs": round(mean([h["totalMs"] for h in hs]), 3),
                "thread": hs[0].get("thread"),
                "package": hs[0].get("package"),
            }
        )
    out.sort(key=lambda h: h["selfMs"], reverse=True)
    return out


def agg_allocations(runs):
    by_key = defaultdict(list)
    for r in runs:
        for a in r["jfr"].get("allocations", []):
            key = (a["class"], a.get("site"))
            by_key[key].append(a)
    out = []
    for (cls, site), alloc in by_key.items():
        out.append(
            {
                "class": cls,
                "site": site,
                "count": int(mean([a["count"] for a in alloc])),
                "bytes": int(mean([a["bytes"] for a in alloc])),
            }
        )
    out.sort(key=lambda a: a["bytes"], reverse=True)
    return out


def agg_phases(runs):
    # Keyed by thread as well as phase, mirroring jfr_phase_summary. Merging a phase that runs
    # on several threads into one row and labelling it with the first run's thread reported
    # background work as render-thread cost.
    by_phase = defaultdict(list)
    for r in runs:
        for p in r["jfr"].get("phases", []):
            by_phase[(p["phase"], p.get("thread"))].append(p)
    out = []
    for (phase, thread), phases in by_phase.items():
        metric_names = set()
        for p in phases:
            metric_names.update((p.get("metrics") or {}).keys())
        metrics = {}
        for name in metric_names:
            values = [p.get("metrics", {}).get(name, {}) for p in phases if name in p.get("metrics", {})]
            if not values:
                continue
            metrics[name] = (
                {
                    "avg": round(mean([v.get("avg", 0.0) for v in values]), 3),
                    "max": max(v.get("max", 0.0) for v in values),
                    "count": int(mean([v.get("count", 0) for v in values])),
                }
                if "avg" in values[0]
                else {
                    "count": int(mean([v.get("count", 0) for v in values])),
                }
            )
        out.append(
            {
                "phase": phase,
                "count": int(mean([p.get("count", 0) for p in phases])),
                "frames": int(mean([p.get("frames", 0) for p in phases])),
                "totalMs": round(mean([p.get("totalMs", 0.0) for p in phases]), 3),
                "perFrameMs": _mean_or_none([p.get("perFrameMs") for p in phases]),
                "avgMs": round(mean([p.get("avgMs", 0.0) for p in phases]), 3),
                "p50Ms": round(mean([p.get("p50Ms", 0.0) for p in phases]), 3),
                "p95Ms": round(mean([p.get("p95Ms", 0.0) for p in phases]), 3),
                "p99Ms": round(mean([p.get("p99Ms", 0.0) for p in phases]), 3),
                "maxMs": round(max(p.get("maxMs", 0.0) for p in phases), 3),
                "thread": thread,
                "metrics": metrics,
            }
        )
    out.sort(key=lambda p: p["totalMs"], reverse=True)
    return out


def agg_gc(runs):
    gcs = [r["jfr"].get("gc", {}) for r in runs]
    return {
        "pauseCountPerSec": round(mean([g.get("pauseCountPerSec", 0.0) for g in gcs]), 3),
        "p99PauseMs": round(mean([g.get("p99PauseMs", 0.0) for g in gcs]), 3),
        "totalPauseMs": round(mean([g.get("totalPauseMs", 0.0) for g in gcs]), 3),
        "events": [ev for g in gcs for ev in g.get("events", [])],
    }


def agg_locks(runs):
    by_key = defaultdict(list)
    for r in runs:
        for lk in r["jfr"].get("locks", []):
            by_key[(lk["monitor"], lk.get("site"))].append(lk)
    out = []
    for (monitor, site), ls in by_key.items():
        out.append(
            {
                "monitor": monitor,
                "site": site,
                "waitMs": round(mean([lk["waitMs"] for lk in ls]), 3),
                "count": int(mean([lk["count"] for lk in ls])),
            }
        )
    out.sort(key=lambda lk: lk["waitMs"], reverse=True)
    return out


def agg_threads(runs):
    by_name = defaultdict(list)
    for r in runs:
        for t in r["jfr"].get("threads", []):
            by_name[t["name"]].append(t)
    out = []
    for name, ts in by_name.items():
        out.append(
            {
                "name": name,
                "cpuPct": round(mean([t.get("cpuPct", 0.0) for t in ts]), 3),
                "sampleCount": int(mean([t["sampleCount"] for t in ts])),
            }
        )
    out.sort(key=lambda t: t["cpuPct"], reverse=True)
    return out


def agg_jfr_validation(runs):
    total = len(runs)
    valid_runs = [r for r in runs if r["jfr"].get("valid", True)]
    reasons = []
    for r in runs:
        validation = r["jfr"].get("validation", {})
        reason = validation.get("reason")
        if reason and reason not in reasons:
            reasons.append(reason)
    return {
        "valid": len(valid_runs) == total,
        "validation": {
            "valid": len(valid_runs) == total,
            "validRunCount": len(valid_runs),
            "totalRunCount": total,
            "reason": "; ".join(reasons),
        },
    }


def agg_jfr_window(runs):
    windows = [r["jfr"].get("window") for r in runs if r["jfr"].get("window")]
    if not windows:
        return None
    return windows[0] if len(windows) == 1 else {"source": "per-run", "runCount": len(windows)}


def agg_zones(runs, key):
    by_name = defaultdict(list)
    for r in runs:
        for z in r["tracy"].get(key, []):
            by_name[z["name"]].append(z)
    out = []
    for name, zs in by_name.items():
        out.append(
            {
                "name": name,
                "count": int(mean([z["count"] for z in zs])),
                "meanUs": round(mean([z["meanUs"] for z in zs]), 3),
                "maxUs": round(mean([z.get("maxUs", 0.0) for z in zs]), 3),
                "totalMs": round(mean([z["totalMs"] for z in zs]), 3),
            }
        )
    out.sort(key=lambda z: z["totalMs"], reverse=True)
    return out


def agg_tracy_health(runs):
    healths = [r["tracy"].get("health", {}) for r in runs]
    total = len(runs)
    valid = [h for h in healths if h.get("valid", True)]
    warnings = []
    for h in healths:
        reason = h.get("reason")
        if reason and reason != "capture log looked clean" and reason not in warnings:
            warnings.append(reason)
        for warning in h.get("warnings", []):
            if warning and warning not in warnings:
                warnings.append(warning)
    health = {
        "valid": len(valid) == total,
        "validRunCount": len(valid),
        "totalRunCount": total,
        "reason": "; ".join(warnings) if warnings else "all Tracy capture logs looked clean",
        "warnings": warnings,
    }
    csv_quality = agg_tracy_csv_quality(healths)
    if csv_quality:
        health["csvQuality"] = csv_quality
    return health


def agg_tracy_csv_quality(healths):
    qualities = [h.get("csvQuality") for h in healths if h.get("csvQuality")]
    if not qualities:
        return None

    rows = sum(int(q.get("rows") or 0) for q in qualities)
    named_rows = sum(int(q.get("namedRows") or 0) for q in qualities)
    total_count = sum(int(q.get("totalCount") or 0) for q in qualities)
    anonymous_count = sum(int(q.get("anonymousCount") or 0) for q in qualities)
    total_ns = sum(int(q.get("totalNs") or 0) for q in qualities)
    anonymous_ns = sum(int(q.get("anonymousNs") or 0) for q in qualities)

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


def agg_tracy_window(runs):
    windows = [r["tracy"].get("window") for r in runs if r["tracy"].get("window")]
    if not windows:
        return None
    return windows[0] if len(windows) == 1 else {"source": "per-run", "runCount": len(windows)}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input-dir", required=True, help="Directory containing run_N/ subdirs")
    p.add_argument("--out", required=True)
    args = p.parse_args()

    runs = load_runs(args.input_dir)
    if not runs:
        raise SystemExit("no run_N/profile-data.json found under " + args.input_dir)

    meta = runs[0]["meta"].copy()
    meta["run"] = None

    doc = {
        "schemaVersion": 1,
        "kind": "aggregate",
        "meta": meta,
        "frame": agg_frame(runs),
        "jfr": {
            "hotspots": agg_hotspots(runs),
            "allocations": agg_allocations(runs),
            "phases": agg_phases(runs),
            "gc": agg_gc(runs),
            "locks": agg_locks(runs),
            "threads": agg_threads(runs),
        },
        "tracy": {
            "zones": agg_zones(runs, "zones"),
            "gpu": agg_zones(runs, "gpu"),
            "frameMarkers": [m for r in runs for m in r["tracy"].get("frameMarkers", [])],
            "frames": int(mean([r["tracy"].get("frames", 0) for r in runs])),
            "window": agg_tracy_window(runs),
            "health": agg_tracy_health(runs),
        },
        "perRun": runs,
    }
    doc["jfr"].update(agg_jfr_validation(runs))
    doc["jfr"]["window"] = agg_jfr_window(runs)
    Path(args.out).write_text(json.dumps(doc, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

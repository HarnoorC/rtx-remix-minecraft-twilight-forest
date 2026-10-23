# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import datetime as dt
import json
import shutil
from pathlib import Path

from . import util
from .dashboard import DASHBOARD_HTML

CATALOG_VERSION = 1


def result_dirs(results_dir: Path = util.RESULTS_DIR) -> list[Path]:
    if not results_dir.exists():
        return []
    dirs = []
    for child in results_dir.iterdir():
        if child.is_dir() and (child / "manifest.json").exists():
            dirs.append(child)
    return sorted(dirs, key=lambda p: p.name)


def load_manifest(run_dir: Path, results_dir: Path = util.RESULTS_DIR) -> dict:
    manifest = util.read_json(run_dir / "manifest.json")
    manifest.setdefault("path", util.rel(run_dir, results_dir))
    return manifest


# Frame times are autocorrelated: stalls cluster, so treating frames as
# independent samples badly understates the uncertainty on the mean. Batch
# means over blocks of this many frames restores a usable estimate.
RESOLUTION_BLOCK_FRAMES = 50


def _batch_mean_se(samples: list[float], block: int = RESOLUTION_BLOCK_FRAMES) -> float:
    """Standard error of the mean via batch means, for an autocorrelated series."""
    blocks = len(samples) // block
    if blocks < 2:
        return 0.0
    means = [sum(samples[i * block : (i + 1) * block]) / block for i in range(blocks)]
    grand = sum(means) / blocks
    var = sum((m - grand) ** 2 for m in means) / (blocks - 1)
    return (var / blocks) ** 0.5


def aggregated_runs(doc: dict) -> list[dict]:
    """The perRun entries that fed the headline frame mean.

    The aggregate leaves degenerate runs out of frame.avgMs but keeps them in
    perRun for transparency. Any statistic taken relative to that mean has to
    apply the same exclusion, or it mixes a population the mean never saw.
    """
    per_run = doc.get("perRun") or []
    frame = doc.get("frame") or {}
    if frame.get("allRunsDegenerate"):
        return per_run
    excluded = {entry.get("run") for entry in frame.get("excludedRuns") or []}
    if not excluded:
        return per_run
    return [r for r in per_run if (r.get("meta") or {}).get("run") not in excluded]


def frame_resolution(doc: dict) -> dict[str, object]:
    """Smallest frame-time delta this run set can distinguish from noise.

    With two or more runs the between-run spread is the honest estimate: it
    absorbs thermal drift and machine state, which a within-run statistic cannot
    see. With a single run only batch means are available, so the result is a
    lower bound and is flagged as such: it cannot observe run-to-run drift at all.
    """
    per_run = aggregated_runs(doc)
    run_means = [
        float(((r.get("frame") or {}).get("avgMs")) or 0.0) for r in per_run if ((r.get("frame") or {}).get("avgMs"))
    ]
    mean = float((doc.get("frame") or {}).get("avgMs") or 0.0)
    if mean <= 0.0:
        return {}

    if len(run_means) >= 2:
        grand = sum(run_means) / len(run_means)
        var = sum((m - grand) ** 2 for m in run_means) / (len(run_means) - 1)
        se = (var / len(run_means)) ** 0.5
        basis = "between-run"
    else:
        frames = [float(v) / 1e6 for v in ((per_run[0] if per_run else {}).get("perFrame") or [])]
        se = _batch_mean_se(frames)
        basis = "batch-means"

    if se <= 0.0:
        return {}
    return {
        "seMs": round(se, 4),
        "sePct": round(100.0 * se / mean, 3),
        "ci95Pct": round(100.0 * 1.96 * se / mean, 3),
        "basis": basis,
        "runs": len(run_means) or 1,
        "lowerBound": basis == "batch-means",
    }


def summarize_frame(frame: dict) -> dict[str, object]:
    avg_ms = float(frame.get("avgMs") or 0.0)
    p99_ms = float(frame.get("p99Ms") or frame.get("p1Ms") or 0.0)
    return {
        "avgMs": avg_ms,
        "avgFps": round(1000.0 / avg_ms, 3) if avg_ms else 0.0,
        "p99Ms": p99_ms,
        "onePctLowFps": round(1000.0 / p99_ms, 3) if p99_ms else 0.0,
        "cvPct": float(frame.get("cvPct") or 0.0),
        "minMs": float(frame.get("minMs") or 0.0),
        "maxMs": float(frame.get("maxMs") or 0.0),
        "stddevMs": float(frame.get("stddevMs") or 0.0),
    }


def summarize_profile_data(doc: dict) -> dict[str, object]:
    summary = summarize_frame(doc.get("frame") or {})
    run_number = (doc.get("meta") or {}).get("run")
    if run_number is not None:
        summary["run"] = run_number
    return summary


def summarize_aggregate(aggregate_path: Path) -> dict:
    if not aggregate_path.exists():
        return {}
    doc = util.read_json(aggregate_path)
    frame = doc.get("frame", {})
    tracy_health = (doc.get("tracy") or {}).get("health") or {}
    tracy_quality = tracy_health.get("csvQuality") or {}
    summary = summarize_frame(frame)
    summary.update(
        {
            "runs": len(doc.get("perRun") or []),
            "runsAggregated": int(frame.get("runsAggregated") or len(doc.get("perRun") or [])),
            "excludedRunCount": int(frame.get("excludedRunCount") or 0),
            "allRunsDegenerate": bool(frame.get("allRunsDegenerate", False)),
            "tracyValid": bool(tracy_health.get("valid", False)),
            "tracyHealthReason": str(tracy_health.get("reason") or ""),
            "tracyValidRunCount": int(tracy_health.get("validRunCount") or 0),
            "tracyTotalRunCount": int(tracy_health.get("totalRunCount") or 0),
            "tracyAnonymousPct": float(tracy_quality.get("anonymousPct") or 0.0),
            "jfrValid": bool((doc.get("jfr") or {}).get("valid", False)),
        }
    )
    summary["perRun"] = [summarize_profile_data(item) for item in doc.get("perRun") or []]
    sections = frame.get("sections") or {}
    # Deep enough to hold every section the mod registers. A top-8 cut dropped sections as
    # they were optimised, which hid exactly the ones most likely to regress back.
    summary["sections"] = {
        name: value
        for name, value in sorted(
            sections.items(),
            key=lambda item: float((item[1] or {}).get("avgMs") or 0.0),
            reverse=True,
        )[:16]
    }
    # Scene-completeness counters. A run whose terrain never finished streaming
    # renders a smaller world than the view distance implies, so its frame time
    # is not comparable to a run that drew the whole scene. Carried into the
    # manifest so the CI report can gate on it without reopening aggregate.json.
    counters = frame.get("counters") or {}

    def _counter(name: str) -> float:
        return float((counters.get(name) or {}).get("avg") or 0.0)

    summary["scene"] = {
        "sections": _counter("Chunk.Sections"),
        "drawnPages": _counter("Chunk.RetainedPages"),
        "captureQueue": _counter("Chunk.CaptureQueue"),
        "missingSections": _counter("Chunk.MissingSections"),
        "lightsDrawn": _counter("Chunk.LightsDrawn"),
        "lightsBeyondReach": _counter("Chunk.LightsBeyondReach"),
        "floodIncrementalUs": _counter("Chunk.FloodIncrementalUs"),
    }
    summary["resolution"] = frame_resolution(doc)
    return summary


def attach_per_run_summaries(manifest: dict) -> None:
    per_run = (manifest.get("summary") or {}).get("perRun") or []
    by_number = {str(item.get("run")): item for item in per_run if item.get("run") is not None}
    for run_artifact in (manifest.get("artifacts") or {}).get("runs") or []:
        summary = by_number.get(str(run_artifact.get("run")))
        if summary:
            run_artifact["summary"] = summary


def eligible_for_comparison(manifest: dict) -> bool:
    outcome = manifest.get("outcome") or {}
    # Legacy manifests carry an explicit flag; current writers emit only
    # status (passed == comparable). Honor both for existing result dirs.
    if "eligibleForComparison" in outcome:
        return bool(outcome["eligibleForComparison"])
    return str(outcome.get("status") or "passed") == "passed"


def build_catalog(results_dir: Path = util.RESULTS_DIR, default_a: str = "", default_b: str = "") -> dict:
    runs = []
    for run_dir in result_dirs(results_dir):
        manifest = load_manifest(run_dir, results_dir)
        if not manifest.get("summary") or "perRun" not in (manifest.get("summary") or {}):
            manifest["summary"] = summarize_aggregate(run_dir / "aggregate.json")
        attach_per_run_summaries(manifest)
        manifest["path"] = util.rel(run_dir, results_dir)
        runs.append(manifest)

    runs.sort(key=lambda item: item.get("timestamp", {}).get("utc", item.get("id", "")))
    comparable_runs = [run for run in runs if eligible_for_comparison(run)]
    if not default_b and comparable_runs:
        default_b = comparable_runs[-1]["id"]
    if not default_a and len(comparable_runs) > 1:
        default_a = comparable_runs[-2]["id"]

    return {
        "schemaVersion": CATALOG_VERSION,
        "generatedAt": dt.datetime.now(dt.UTC).isoformat(),
        "defaultA": default_a,
        "defaultB": default_b,
        "runs": runs,
    }


def write_dashboard(results_dir: Path = util.RESULTS_DIR, default_a: str = "", default_b: str = "") -> dict:
    results_dir.mkdir(parents=True, exist_ok=True)
    catalog = build_catalog(results_dir, default_a=default_a, default_b=default_b)
    (results_dir / "index.html").write_text(DASHBOARD_HTML, encoding="utf-8")
    payload = "window.BENCHMARK_CATALOG = "
    payload += json.dumps(catalog, indent=2)
    payload += ";\n"
    (results_dir / "catalog.js").write_text(payload, encoding="utf-8")
    return catalog


def merge_tags(existing: list | None, extra: list[str] | None) -> list[str]:
    tags = []
    for tag in [*(existing or []), *(extra or [])]:
        text = str(tag).strip()
        if text and text not in tags:
            tags.append(text)
    return tags


def import_run_dir(src: Path, results_dir: Path = util.RESULTS_DIR, tags: list[str] | None = None) -> Path:
    manifest = util.read_json(src / "manifest.json")
    run_id = manifest.get("id") or src.name
    dst = results_dir / run_id
    suffix = 2
    while dst.exists():
        dst = results_dir / f"{run_id}_{suffix}"
        suffix += 1
    shutil.copytree(src, dst)
    if dst.name != run_id:
        manifest["originalId"] = run_id
        manifest["id"] = dst.name
    if tags:
        manifest["tags"] = merge_tags(manifest.get("tags") or [], tags)
    if tags or dst.name != run_id:
        util.write_json(dst / "manifest.json", manifest)
    return dst


def resolve_run_dir(run_id: str, results_dir: Path = util.RESULTS_DIR) -> Path:
    query = run_id.strip()
    if not query:
        raise RuntimeError("run id cannot be empty")

    dirs = result_dirs(results_dir)
    exact = [
        path for path in dirs if path.name == query or str(load_manifest(path, results_dir).get("id") or "") == query
    ]
    if exact:
        return exact[0]

    matches = [
        path
        for path in dirs
        if path.name.startswith(query) or str(load_manifest(path, results_dir).get("id") or "").startswith(query)
    ]
    if not matches:
        raise RuntimeError(f"no benchmark run matches {query}")
    if len(matches) > 1:
        raise RuntimeError(f"ambiguous benchmark run {query}: {', '.join(path.name for path in matches[:8])}")
    return matches[0]


def delete_run(run_id: str, results_dir: Path = util.RESULTS_DIR) -> Path:
    run_dir = resolve_run_dir(run_id, results_dir)
    util.ensure_inside(run_dir, results_dir)
    shutil.rmtree(run_dir)
    write_dashboard(results_dir)
    return run_dir


def annotate_run(
    run_id: str,
    results_dir: Path = util.RESULTS_DIR,
    *,
    note: str | None = None,
    tags: list[str] | None = None,
    clear_note: bool = False,
) -> Path:
    if note is None and not tags and not clear_note:
        raise RuntimeError("nothing to update; pass --note, --tag, or --clear-note")

    run_dir = resolve_run_dir(run_id, results_dir)
    util.ensure_inside(run_dir, results_dir)
    manifest_path = run_dir / "manifest.json"
    manifest = util.read_json(manifest_path)
    if clear_note:
        manifest["notes"] = ""
    if note is not None:
        manifest["notes"] = note
    if tags:
        manifest["tags"] = merge_tags(manifest.get("tags") or [], tags)
    util.write_json(manifest_path, manifest)
    write_dashboard(results_dir)
    return run_dir

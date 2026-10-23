# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import copy
import json
import subprocess
import sys
from importlib.resources import files

import jsonschema

MODULE = "rtx_tools.profiler.aggregate_profile_data"
SCHEMA = files("rtx_tools.profiler").joinpath("profile-schema.json")


def _validator_for(schema, def_name):
    root = copy.deepcopy(schema)
    root["$ref"] = f"#/$defs/{def_name}"
    return jsonschema.Draft202012Validator(root)


def make_pd(run, avg_ms, zone_total_ms):
    total_ns = run * 1_000_000
    anonymous_ns = run * 100_000
    total_count = run * 100
    anonymous_count = run * 10
    return {
        "schemaVersion": 1,
        "kind": "profile-data",
        "meta": {"branch": "main", "commit": "abc1234", "run": run, "sessionId": "x"},
        "frame": {
            "avgMs": avg_ms,
            "p1Ms": avg_ms + 2,
            "p99Ms": avg_ms + 2,
            "minMs": avg_ms - 1,
            "maxMs": avg_ms + 3,
            "stddevMs": 0.5,
            "cvPct": 5.0,
            "sections": {},
            "counters": {},
        },
        "jfr": {
            "hotspots": [{"method": "X.y", "selfMs": 1.0 * run, "totalMs": 2.0 * run, "thread": "T", "package": "X"}],
            "allocations": [{"class": "C", "site": None, "count": 100 * run, "bytes": 1000 * run}],
            "phases": [
                {
                    "phase": "Chunk.Gen",
                    "count": 10 * run,
                    "frames": 5 * run,
                    "totalMs": 1.5 * run,
                    "perFrameMs": 0.3,
                    "avgMs": 0.15,
                    "p50Ms": 0.1,
                    "p95Ms": 0.2,
                    "p99Ms": 0.3,
                    "maxMs": 0.4 * run,
                    "thread": "main",
                    "metrics": {"captureCount": {"avg": run, "max": 2 * run, "count": run}},
                }
            ],
            "gc": {"pauseCountPerSec": 1.0, "p99PauseMs": 5.0, "totalPauseMs": 10.0 * run, "events": []},
            "locks": [],
            "threads": [],
        },
        "tracy": {
            "zones": [{"name": "Z", "count": 10, "meanUs": 100.0, "maxUs": 200.0, "totalMs": zone_total_ms}],
            "gpu": [],
            "frameMarkers": [],
            "health": {
                "valid": True,
                "validRunCount": 1,
                "totalRunCount": 1,
                "reason": "capture log looked clean",
                "warnings": [],
                "csvQuality": {
                    "rows": 2,
                    "namedRows": 1,
                    "totalCount": total_count,
                    "anonymousCount": anonymous_count,
                    "totalNs": total_ns,
                    "anonymousNs": anonymous_ns,
                    "anonymousPct": 10.0,
                    "anonymousCountPct": 10.0,
                },
            },
        },
    }


def _make_run_dirs(tmp_path, n_runs, avg_seq, zone_total_seq):
    for i in range(1, n_runs + 1):
        (tmp_path / f"run_{i}").mkdir()
        (tmp_path / f"run_{i}" / "profile-data.json").write_text(
            json.dumps(make_pd(i, avg_seq[i - 1], zone_total_seq[i - 1])), encoding="utf-8"
        )


def test_aggregate_averages_frame(tmp_path):
    _make_run_dirs(tmp_path, 3, [8.0, 9.0, 10.0], [1.0, 2.0, 3.0])
    out = tmp_path / "aggregate.json"
    subprocess.run(
        [sys.executable, "-m", MODULE, "--input-dir", str(tmp_path), "--out", str(out)],
        check=True,
    )
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["frame"]["avgMs"] == 9.0
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    _validator_for(schema, "Aggregate").validate(doc)


def test_aggregate_excludes_degenerate_run(tmp_path):
    # Three runs; run 1 contains a catastrophic multi-second stall frame (world
    # load / shader-comp hitch), like the real win64 CI regression false alarm.
    _make_run_dirs(tmp_path, 3, [60.0, 15.0, 15.0], [1.0, 1.0, 1.0])
    path = tmp_path / "run_1" / "profile-data.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["frame"]["maxMs"] = 66666.0
    path.write_text(json.dumps(doc), encoding="utf-8")

    out = tmp_path / "aggregate.json"
    subprocess.run(
        [sys.executable, "-m", MODULE, "--input-dir", str(tmp_path), "--out", str(out)],
        check=True,
    )
    doc = json.loads(out.read_text(encoding="utf-8"))
    # Headline avg is the mean of the two healthy runs (15, 15), not (60+15+15)/3 = 30.
    assert doc["frame"]["avgMs"] == 15.0
    assert doc["frame"]["runsTotal"] == 3
    assert doc["frame"]["runsAggregated"] == 2
    assert doc["frame"]["excludedRunCount"] == 1
    assert doc["frame"]["excludedRuns"][0]["run"] == 1
    # All runs are still retained for transparency.
    assert len(doc["perRun"]) == 3
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    _validator_for(schema, "Aggregate").validate(doc)


def test_aggregate_keeps_all_runs_when_every_run_is_degenerate(tmp_path):
    # Single run that is itself degenerate: fall back to using it (don't emit
    # nothing), but flag it so the report can warn loudly.
    _make_run_dirs(tmp_path, 1, [15.0], [1.0])
    path = tmp_path / "run_1" / "profile-data.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["frame"]["maxMs"] = 66666.0
    path.write_text(json.dumps(doc), encoding="utf-8")

    out = tmp_path / "aggregate.json"
    subprocess.run(
        [sys.executable, "-m", MODULE, "--input-dir", str(tmp_path), "--out", str(out)],
        check=True,
    )
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["frame"]["avgMs"] == 15.0
    assert doc["frame"]["runsAggregated"] == 1
    assert doc["frame"]["excludedRunCount"] == 0
    assert doc["frame"]["allRunsDegenerate"] is True


def test_aggregate_accepts_scalar_frame_counters(tmp_path):
    _make_run_dirs(tmp_path, 2, [8.0, 10.0], [1.0, 1.0])
    for run, value in ((1, True), (2, False)):
        path = tmp_path / f"run_{run}" / "profile-data.json"
        doc = json.loads(path.read_text(encoding="utf-8"))
        doc["frame"]["counters"]["surfaceReady"] = value
        path.write_text(json.dumps(doc), encoding="utf-8")

    out = tmp_path / "aggregate.json"
    subprocess.run(
        [sys.executable, "-m", MODULE, "--input-dir", str(tmp_path), "--out", str(out)],
        check=True,
    )
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["frame"]["counters"]["surfaceReady"]["avg"] == 0.5


def test_aggregate_averages_hotspot_times(tmp_path):
    _make_run_dirs(tmp_path, 3, [8.0, 8.0, 8.0], [1.0, 1.0, 1.0])
    out = tmp_path / "aggregate.json"
    subprocess.run(
        [sys.executable, "-m", MODULE, "--input-dir", str(tmp_path), "--out", str(out)],
        check=True,
    )
    doc = json.loads(out.read_text(encoding="utf-8"))
    xy = next(h for h in doc["jfr"]["hotspots"] if h["method"] == "X.y")
    assert xy["selfMs"] == 2.0


def test_aggregate_averages_java_phases(tmp_path):
    _make_run_dirs(tmp_path, 3, [8.0, 8.0, 8.0], [1.0, 1.0, 1.0])
    out = tmp_path / "aggregate.json"
    subprocess.run(
        [sys.executable, "-m", MODULE, "--input-dir", str(tmp_path), "--out", str(out)],
        check=True,
    )
    doc = json.loads(out.read_text(encoding="utf-8"))
    phase = next(p for p in doc["jfr"]["phases"] if p["phase"] == "Chunk.Gen")
    assert phase["count"] == 20
    assert phase["totalMs"] == 3.0
    assert phase["maxMs"] == 1.2
    assert phase["metrics"]["captureCount"]["avg"] == 2.0


def test_aggregate_keeps_phases_on_different_threads_apart(tmp_path):
    # One phase name on several threads must stay several rows, or background work
    # is reported as render-thread cost. A row that never had a per-frame figure
    # stays None instead of being averaged in as zero.
    _make_run_dirs(tmp_path, 2, [8.0, 8.0], [1.0, 1.0])
    for run in (1, 2):
        path = tmp_path / f"run_{run}" / "profile-data.json"
        doc = json.loads(path.read_text(encoding="utf-8"))
        main_phase = doc["jfr"]["phases"][0]
        doc["jfr"]["phases"].append(dict(main_phase, thread="worker", perFrameMs=None if run == 1 else 0.5))
        doc["jfr"]["phases"].append(dict(main_phase, thread="io", perFrameMs=None))
        path.write_text(json.dumps(doc), encoding="utf-8")

    out = tmp_path / "aggregate.json"
    subprocess.run(
        [sys.executable, "-m", MODULE, "--input-dir", str(tmp_path), "--out", str(out)],
        check=True,
    )
    doc = json.loads(out.read_text(encoding="utf-8"))
    rows = {p["thread"]: p for p in doc["jfr"]["phases"] if p["phase"] == "Chunk.Gen"}
    assert sorted(rows) == ["io", "main", "worker"]
    assert rows["main"]["perFrameMs"] == 0.3
    assert rows["worker"]["perFrameMs"] == 0.5
    assert rows["io"]["perFrameMs"] is None
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    _validator_for(schema, "Aggregate").validate(doc)


def test_aggregate_kind_is_aggregate(tmp_path):
    _make_run_dirs(tmp_path, 2, [8.0, 8.0], [1.0, 1.0])
    out = tmp_path / "aggregate.json"
    subprocess.run(
        [sys.executable, "-m", MODULE, "--input-dir", str(tmp_path), "--out", str(out)],
        check=True,
    )
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["kind"] == "aggregate"
    assert doc["meta"]["run"] is None


def test_aggregate_carries_tracy_csv_quality(tmp_path):
    _make_run_dirs(tmp_path, 3, [8.0, 8.0, 8.0], [1.0, 1.0, 1.0])
    out = tmp_path / "aggregate.json"
    subprocess.run(
        [sys.executable, "-m", MODULE, "--input-dir", str(tmp_path), "--out", str(out)],
        check=True,
    )
    doc = json.loads(out.read_text(encoding="utf-8"))
    quality = doc["tracy"]["health"]["csvQuality"]
    assert quality["rows"] == 6
    assert quality["namedRows"] == 3
    assert quality["totalNs"] == 6_000_000
    assert quality["anonymousNs"] == 600_000
    assert quality["anonymousPct"] == 10.0
    assert quality["anonymousCountPct"] == 10.0


def test_aggregate_fails_on_empty_dir(tmp_path):
    out = tmp_path / "aggregate.json"
    result = subprocess.run(
        [sys.executable, "-m", MODULE, "--input-dir", str(tmp_path), "--out", str(out)],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode != 0

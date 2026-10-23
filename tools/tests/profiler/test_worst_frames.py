# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import pytest

from rtx_tools.profiler.jfr_worst_frames import build_worst_frames


def phase_event(phase, timestamp, duration_ms, frame_index, thread="main", **metrics):
    return {
        "type": "minecraft.JavaPhase",
        "values": {
            "startTime": timestamp,
            "duration": f"PT{duration_ms / 1000.0:.6f}S",
            "eventThread": {"javaName": thread},
            "thread": thread,
            "phase": phase,
            "frameIndex": frame_index,
            **metrics,
        },
    }


def marker_event(marker, timestamp):
    return {
        "type": "minecraft.Benchmark.SessionMarker",
        "values": {
            "startTime": timestamp,
            "marker": marker,
        },
    }


def test_build_worst_frames_maps_recorded_frames_and_aggregates_phases():
    per_frame_ms = [8.0, 15.0, 10.0]
    markers = [
        marker_event("recording-start", "2026-04-28T12:00:00.000000Z"),
        marker_event("recording-end", "2026-04-28T12:00:00.060000Z"),
    ]
    phases = [
        phase_event("renderAndSubmitFrame", "2026-04-28T11:59:59.990000Z", 20.0, 99),
        phase_event("renderAndSubmitFrame", "2026-04-28T12:00:00.010000Z", 8.0, 101),
        phase_event("renderAndSubmitFrame", "2026-04-28T12:00:00.026000Z", 15.0, 102),
        phase_event("Chunk.Draw", "2026-04-28T12:00:00.027000Z", 9.0, 102, drawCalls=42),
        phase_event("createMesh", "2026-04-28T12:00:00.028000Z", 1.0, 102, meshCategory=1),
        phase_event("createMesh", "2026-04-28T12:00:00.029000Z", 2.0, 102, meshCategory=2),
        phase_event("renderAndSubmitFrame", "2026-04-28T12:00:00.042000Z", 10.0, 103),
    ]

    report = build_worst_frames(
        per_frame_ms,
        phases,
        markers,
        top_frames=2,
        phase_count=3,
    )

    assert report["mappedFrames"] == 3
    assert report["warning"] is None
    assert report["frames"][0]["recordIndex"] == 1
    assert report["frames"][0]["jfrFrameIndex"] == 102
    assert report["frames"][0]["benchmarkMs"] == pytest.approx(15.0)
    assert report["frames"][0]["renderAndSubmitFrameMs"] == pytest.approx(15.0)

    phase_rows = {row["phase"]: row for row in report["frames"][0]["topPhases"]}
    assert phase_rows["Chunk.Draw"]["totalMs"] == pytest.approx(9.0)
    assert phase_rows["Chunk.Draw"]["metrics"]["drawCalls"] == 42
    assert phase_rows["createMesh"]["totalMs"] == pytest.approx(3.0)
    assert phase_rows["createMesh"]["count"] == 2
    assert phase_rows["createMesh"]["metrics"]["meshCategory"] == 2


def test_build_worst_frames_warns_when_onframe_count_does_not_match_benchmark():
    per_frame_ms = [8.0, 15.0, 10.0]
    phases = [
        phase_event("renderAndSubmitFrame", "2026-04-28T12:00:00.010000Z", 8.0, 101),
        phase_event("renderAndSubmitFrame", "2026-04-28T12:00:00.026000Z", 15.0, 102),
    ]

    report = build_worst_frames(
        per_frame_ms,
        phases,
        marker_events=[],
        top_frames=3,
        phase_count=1,
    )

    assert report["mappedFrames"] == 2
    assert "mapped 2 of 3 benchmark frames" in report["warning"]
    assert report["frames"][0]["jfrFrameIndex"] == 102
    assert report["frames"][1]["jfrFrameIndex"] is None

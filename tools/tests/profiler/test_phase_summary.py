# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import pytest

from rtx_tools.profiler.jfr_phase_summary import summarize


def phase_event(phase, start_ms, duration_ms, frame_index, thread="main", **metrics):
    base_seconds = start_ms / 1000.0
    return {
        "type": "minecraft.JavaPhase",
        "values": {
            "startTime": f"2026-04-28T12:00:{base_seconds:09.6f}Z",
            "duration": f"PT{duration_ms / 1000.0:.6f}S",
            "eventThread": {"javaName": thread},
            "phase": phase,
            "frameIndex": frame_index,
            **metrics,
        },
    }


def test_summarize_groups_phase_events_and_metrics():
    rows = summarize(
        [
            phase_event("Chunk.Gen", 0, 1.0, 1, captureCount=4, dirtyLeaves=2),
            phase_event("Chunk.Gen", 16, 3.0, 2, captureCount=6, dirtyLeaves=4),
            phase_event("Present", 0, 5.0, 1),
        ]
    )

    chunk = next(row for row in rows if row["phase"] == "Chunk.Gen")
    assert chunk["count"] == 2
    assert chunk["frames"] == 2
    assert chunk["totalMs"] == pytest.approx(4.0)
    assert chunk["perFrameMs"] == pytest.approx(2.0)
    assert chunk["avgMs"] == pytest.approx(2.0)
    assert chunk["p50Ms"] == pytest.approx(2.0)
    assert chunk["maxMs"] == pytest.approx(3.0)
    assert chunk["thread"] == "main"
    assert chunk["metrics"]["captureCount"]["avg"] == pytest.approx(5.0)
    assert chunk["metrics"]["captureCount"]["max"] == 6
    assert chunk["metrics"]["dirtyLeaves"]["count"] == 2


def test_summarize_reports_no_per_frame_figure_when_frame_index_absent():
    # Work off the render thread carries frameIndex -1. Falling back to the event count here
    # made perFrameMs equal avgMs, which reads as an enormous per-frame cost for a phase that
    # runs a few long times on a background thread.
    rows = summarize(
        [
            phase_event("WorkerPhase", 0, 2.0, -1, thread="Worker-Main-1"),
            phase_event("WorkerPhase", 2, 2.0, -1, thread="Worker-Main-1"),
        ]
    )

    row = rows[0]
    assert row["frames"] == 0
    assert row["perFrameMs"] is None
    assert row["thread"] == "Worker-Main-*"


def test_summarize_splits_one_phase_across_threads():
    # A phase that runs on both the render thread and a worker used to merge into a single row
    # stamped with whichever thread emitted first, reporting background work as render cost.
    rows = summarize(
        [
            phase_event("Visibility", 0, 1.0, 1, thread="main"),
            phase_event("Visibility", 2, 1.0, 2, thread="main"),
            phase_event("Visibility", 4, 40.0, -1, thread="RTX Remix chunk visibility"),
        ]
    )

    by_thread = {row["thread"]: row for row in rows}
    assert set(by_thread) == {"main", "RTX Remix chunk visibility"}

    assert by_thread["main"]["totalMs"] == pytest.approx(2.0)
    assert by_thread["main"]["perFrameMs"] == pytest.approx(1.0)

    worker = by_thread["RTX Remix chunk visibility"]
    assert worker["totalMs"] == pytest.approx(40.0)
    assert worker["perFrameMs"] is None


def test_summarize_collapses_pool_ordinals_into_one_row():
    rows = summarize(
        [
            phase_event("Build", 0, 1.0, -1, thread="Worker-Main-3"),
            phase_event("Build", 2, 1.0, -1, thread="Worker-Main-7"),
            phase_event("Build", 4, 1.0, -1, thread="RTX Remix mesh builder 2"),
        ]
    )

    by_thread = {row["thread"]: row for row in rows}
    assert set(by_thread) == {"Worker-Main-*", "RTX Remix mesh builder *"}
    assert by_thread["Worker-Main-*"]["count"] == 2

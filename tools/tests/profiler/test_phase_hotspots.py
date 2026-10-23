# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import pytest

from rtx_tools.profiler.jfr_phase_hotspots import (
    allocation_rows,
    build_intervals,
    cpu_rows,
    in_intervals,
)


def _time(ms):
    return f"2026-04-28T12:00:{ms / 1000.0:09.6f}Z"


def phase_event(phase, start_ms, duration_ms, thread="main"):
    return {
        "type": "minecraft.JavaPhase",
        "values": {
            "startTime": _time(start_ms),
            "duration": f"PT{duration_ms / 1000.0:.6f}S",
            "eventThread": {"javaName": thread},
            "phase": phase,
        },
    }


def sample_event(start_ms, thread="main", cls="com/example/Foo", method="work"):
    return {
        "type": "jdk.ExecutionSample",
        "values": {
            "startTime": _time(start_ms),
            "sampledThread": {"javaName": thread},
            "stackTrace": {"frames": [{"method": {"type": {"name": cls}, "name": method}, "lineNumber": 42}]},
        },
    }


def alloc_event(start_ms, thread="main", weight=128, cls="byte[]"):
    ev = sample_event(start_ms, thread=thread, cls="com/example/Allocator", method="make")
    ev["type"] = "jdk.ObjectAllocationSample"
    ev["values"]["objectClass"] = {"name": cls}
    ev["values"]["weight"] = weight
    return ev


def test_build_intervals_filters_samples_by_thread_and_time():
    intervals, total_ms = build_intervals(
        [
            phase_event("Chunk.Gen", 1000, 10, "main"),
            phase_event("Chunk.Gen", 2000, 5, "Worker-Main-1"),
        ]
    )

    assert total_ms == pytest.approx(15.0)
    assert in_intervals(intervals, sample_event(1005, "main"))
    assert not in_intervals(intervals, sample_event(1015, "main"))
    assert in_intervals(intervals, sample_event(2002, "Worker-Main-1"))
    assert not in_intervals(intervals, sample_event(2002, "main"))


def test_cpu_rows_counts_top_stack_frames():
    rows = cpu_rows(
        [
            sample_event(1001, cls="com/example/Foo", method="work"),
            sample_event(1002, cls="com/example/Foo", method="work"),
            sample_event(1003, cls="com/example/Bar", method="tick"),
        ],
        simple=True,
        period_ms=2.5,
    )

    assert rows[0]["method"] == "Foo.work:42"
    assert rows[0]["samples"] == 2
    assert rows[0]["selfMs"] == pytest.approx(5.0)
    assert rows[0]["pct"] == pytest.approx(66.666, rel=0.01)


def test_allocation_rows_can_sort_by_size_or_count():
    rows_by_size = allocation_rows(
        [
            alloc_event(1001, weight=1024, cls="byte[]"),
            alloc_event(1002, weight=512, cls="int[]"),
            alloc_event(1003, weight=8, cls="java/lang/String"),
            alloc_event(1004, weight=8, cls="java/lang/String"),
        ],
        simple=True,
        by="size",
    )

    assert rows_by_size[0]["site"] == "Allocator.make:42"
    assert rows_by_size[0]["bytes"] == 1552
    assert rows_by_size[0]["count"] == 4
    assert rows_by_size[0]["class"] == "java.lang.String"

    rows_by_count = allocation_rows(
        [
            alloc_event(1001, weight=1024, cls="byte[]"),
            alloc_event(1002, weight=8, cls="java/lang/String"),
            alloc_event(1003, weight=8, cls="java/lang/String"),
        ],
        simple=True,
        by="count",
    )

    assert rows_by_count[0]["count"] == 3

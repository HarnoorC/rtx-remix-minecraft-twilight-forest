# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for jfr_gc.py --json output shape compatibility with generate_profile_data.py."""

from rtx_tools.profiler.jfr_gc import _render_json


def _sample_gc_events():
    """Synthetic list of (cause, duration_ms, timestamp_ms) tuples."""
    return [
        ("G1 Young Generation", 12.5, 1_000_000),
        ("G1 Young Generation", 8.3, 2_000_000),
        ("G1 Concurrent GC", 3.1, 3_000_000),
        ("G1 Young Generation", 25.0, 4_000_000),
    ]


def test_render_json_total_pause_ms():
    events = _sample_gc_events()
    result = _render_json(events, duration_sec=4.0)
    assert abs(result["totalPauseMs"] - 48.9) < 0.001


def test_render_json_pause_count_per_sec():
    events = _sample_gc_events()
    result = _render_json(events, duration_sec=4.0)
    # 4 events over 4 seconds = 1.0/s
    assert abs(result["pauseCountPerSec"] - 1.0) < 0.001


def test_render_json_p99_pause_ms():
    events = _sample_gc_events()
    result = _render_json(events, duration_sec=4.0)
    # Sorted durations: 3.1, 8.3, 12.5, 25.0 -- p99 of 4 items = max = 25.0
    assert result["p99PauseMs"] == 25.0


def test_render_json_events_list():
    events = _sample_gc_events()
    result = _render_json(events, duration_sec=4.0)
    assert result["events"] == [
        {"cause": "G1 Young Generation", "durationMs": 12.5},
        {"cause": "G1 Young Generation", "durationMs": 8.3},
        {"cause": "G1 Concurrent GC", "durationMs": 3.1},
        {"cause": "G1 Young Generation", "durationMs": 25.0},
    ]


def test_render_json_empty_events():
    result = _render_json([], duration_sec=1.0)
    assert result["pauseCountPerSec"] == 0.0
    assert result["p99PauseMs"] == 0.0
    assert result["totalPauseMs"] == 0.0
    assert result["events"] == []


def test_render_json_zero_duration_no_crash():
    result = _render_json(_sample_gc_events(), duration_sec=0.0)
    assert result["pauseCountPerSec"] == 0.0

# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for jfr_threads.py --json output shape compatibility with generate_profile_data.py."""

from rtx_tools.profiler.jfr_threads import _render_json


def _sample_thread_counts():
    """Synthetic dict of {thread_name: sample_count} as collected from ExecutionSample events."""
    return {
        "main": 250,
        "Worker-1": 180,
        "Render-Thread": 120,
        "GC Thread": 5,
        "Reference Handler": 2,
    }


def test_render_json_list_is_sorted_by_sample_count():
    result = _render_json(_sample_thread_counts(), total_samples=557)
    counts = [t["sampleCount"] for t in result["threads"]]
    assert counts == sorted(counts, reverse=True)


def test_render_json_required_fields():
    result = _render_json(_sample_thread_counts(), total_samples=557)
    assert result["threads"] == [
        {"name": "main", "cpuPct": 44.88, "sampleCount": 250},
        {"name": "Worker-1", "cpuPct": 32.32, "sampleCount": 180},
        {"name": "Render-Thread", "cpuPct": 21.54, "sampleCount": 120},
        {"name": "GC Thread", "cpuPct": 0.90, "sampleCount": 5},
        {"name": "Reference Handler", "cpuPct": 0.36, "sampleCount": 2},
    ]


def test_render_json_cpu_pct_sums_to_100_approx():
    result = _render_json(_sample_thread_counts(), total_samples=557)
    total_pct = sum(t["cpuPct"] for t in result["threads"])
    # All threads included, so should sum to ~100%
    assert abs(total_pct - 100.0) < 0.1


def test_render_json_empty():
    result = _render_json({}, total_samples=0)
    assert result == {"threads": []}


def test_render_json_zero_total_no_crash():
    result = _render_json({"main": 10}, total_samples=0)
    assert result["threads"][0]["cpuPct"] == 0.0

# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for jfr_locks.py --json output shape compatibility with generate_profile_data.py."""

from rtx_tools.profiler.jfr_locks import _render_json


def _sample_monitors():
    """Synthetic (monitor_class, total_ms, count, max_ms, thread_count) tuples."""
    return [
        ("java.util.concurrent.locks.ReentrantLock", 45.0, 12, 8.0, 3),
        ("net.minecraft.world.World", 12.5, 4, 5.0, 2),
        ("java.lang.Object", 3.1, 1, 3.1, 1),
    ]


def test_render_json_list_length_capped_by_top():
    result = _render_json(_sample_monitors(), top=2)
    assert len(result["locks"]) == 2


def test_render_json_required_fields():
    result = _render_json(_sample_monitors(), top=10)
    assert result["locks"][0] == {
        "monitor": "java.util.concurrent.locks.ReentrantLock",
        "site": None,
        "waitMs": 45.0,
        "count": 12,
    }


def test_render_json_empty():
    result = _render_json([], top=10)
    assert result == {"locks": []}

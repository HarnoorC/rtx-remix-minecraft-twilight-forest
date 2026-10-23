# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for jfr_alloc.py --json output shape compatibility with generate_profile_data.py."""

from rtx_tools.profiler.jfr_alloc import _render_json


def _sample_sites():
    """Synthetic site_stats as built by run(): a list of (site, stats_dict) pairs."""
    return [
        (
            "com.example.Renderer.allocBuffer",
            {"count": 500, "bytes": 1_048_576, "classes": {"byte[]": 400, "int[]": 100}},
        ),
        ("com.example.World.buildChunk", {"count": 200, "bytes": 204_800, "classes": {"net.minecraft.Chunk": 200}}),
        ("<no stack>", {"count": 10, "bytes": 1024, "classes": {"java.lang.Object": 10}}),
    ]


def test_render_json_list_length_capped_by_top():
    result = _render_json(_sample_sites(), top=2)
    assert len(result["allocations"]) == 2


def test_render_json_class_is_top_class():
    """The 'class' field must be the most frequent allocated class at that site."""
    result = _render_json(_sample_sites(), top=10)
    assert result["allocations"][0] == {
        "class": "byte[]",
        "site": "com.example.Renderer.allocBuffer",
        "count": 500,
        "bytes": 1_048_576,
    }


def test_render_json_empty():
    result = _render_json([], top=10)
    assert result == {"allocations": []}

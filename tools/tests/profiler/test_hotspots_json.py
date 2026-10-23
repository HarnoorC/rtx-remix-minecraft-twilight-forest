# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for jfr_hotspots.py --json output shape compatibility with generate_profile_data.py."""

import pytest

from rtx_tools.profiler.jfr_hotspots import _render_json


def _sample_rows():
    """Minimal synthetic rows as collected by collect_self_time / collect_total_time."""
    return [
        ("com.example.Foo.render", 120),
        ("com.example.Bar.update", 80),
        ("java.util.HashMap.get", 30),
    ]


@pytest.mark.parametrize(
    "rows,total,expected",
    [
        (
            _sample_rows(),
            230,
            {
                "hotspots": [
                    {
                        "method": "com.example.Foo.render",
                        "selfMs": 120.0,
                        "totalMs": 120.0,
                        "thread": None,
                        "package": None,
                    },
                    {
                        "method": "com.example.Bar.update",
                        "selfMs": 80.0,
                        "totalMs": 80.0,
                        "thread": None,
                        "package": None,
                    },
                    {
                        "method": "java.util.HashMap.get",
                        "selfMs": 30.0,
                        "totalMs": 30.0,
                        "thread": None,
                        "package": None,
                    },
                ]
            },
        ),
        (
            [("some.package.MyClass.doWork", 5)],
            5,
            {
                "hotspots": [
                    {
                        "method": "some.package.MyClass.doWork",
                        "selfMs": 5.0,
                        "totalMs": 5.0,
                        "thread": None,
                        "package": None,
                    },
                ]
            },
        ),
    ],
)
def test_render_json_required_fields(rows, total, expected):
    result = _render_json(rows, period_ms=1.0, total=total)
    assert result == expected


def test_render_json_selfMs_derived_from_period():
    """selfMs = samples * period_ms."""
    rows = [("com.example.Foo.work", 10)]
    result = _render_json(rows, period_ms=2.5, total=10)
    assert result["hotspots"][0]["selfMs"] == pytest.approx(25.0)


def test_render_json_empty_rows():
    result = _render_json([], period_ms=1.0, total=0)
    assert result == {"hotspots": []}

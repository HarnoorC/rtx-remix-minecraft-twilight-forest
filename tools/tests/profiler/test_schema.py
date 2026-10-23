# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import copy
import json
from importlib.resources import files

import jsonschema

SCHEMA = files("rtx_tools.profiler").joinpath("profile-schema.json")


def load_schema():
    return json.loads(SCHEMA.read_text(encoding="utf-8"))


def _validator_for(schema, def_name):
    """Return a validator scoped to a named $def, with $defs resolvable."""
    root = copy.deepcopy(schema)
    root["$ref"] = f"#/$defs/{def_name}"
    return jsonschema.Draft202012Validator(root)


def test_valid_profile_data_passes():
    schema = load_schema()
    doc = {
        "schemaVersion": 1,
        "kind": "profile-data",
        "meta": {"branch": "main", "commit": "abc1234", "run": 1, "sessionId": "20260422T120000"},
        "frame": {"avgMs": 8.3, "p1Ms": 12.0, "p99Ms": 12.0, "sections": {}, "counters": {}},
        "jfr": {
            "hotspots": [],
            "allocations": [],
            "phases": [
                {
                    "phase": "Chunk.Gen",
                    "count": 1,
                    "frames": 1,
                    "totalMs": 1.0,
                    "perFrameMs": 1.0,
                    "avgMs": 1.0,
                    "p50Ms": 1.0,
                    "p95Ms": 1.0,
                    "p99Ms": 1.0,
                    "maxMs": 1.0,
                    "thread": "main",
                    "metrics": {"captureCount": {"avg": 2.0, "max": 2.0, "count": 1}},
                }
            ],
            "gc": {"pauseCountPerSec": 0.0, "p99PauseMs": 0.0, "events": []},
            "locks": [],
            "threads": [],
        },
        "tracy": {"zones": [], "gpu": [], "frameMarkers": []},
    }
    _validator_for(schema, "ProfileData").validate(doc)


def test_invalid_profile_data_fails():
    schema = load_schema()
    doc = {"schemaVersion": 1, "kind": "profile-data"}  # missing required fields
    import jsonschema
    import pytest

    with pytest.raises(jsonschema.ValidationError):
        _validator_for(schema, "ProfileData").validate(doc)


def test_invalid_java_phase_fails():
    schema = load_schema()
    doc = {
        "schemaVersion": 1,
        "kind": "profile-data",
        "meta": {"branch": "main", "commit": "abc1234", "run": 1, "sessionId": "20260422T120000"},
        "frame": {"avgMs": 8.3, "p1Ms": 12.0, "p99Ms": 12.0, "sections": {}, "counters": {}},
        "jfr": {
            "hotspots": [],
            "allocations": [],
            "phases": [{"phase": "Chunk.Gen", "count": "one"}],
            "gc": {"pauseCountPerSec": 0.0, "p99PauseMs": 0.0, "events": []},
            "locks": [],
            "threads": [],
        },
        "tracy": {"zones": [], "gpu": [], "frameMarkers": []},
    }
    import jsonschema
    import pytest

    with pytest.raises(jsonschema.ValidationError):
        _validator_for(schema, "ProfileData").validate(doc)


def test_valid_aggregate_passes():
    schema = load_schema()
    pd = {
        "schemaVersion": 1,
        "kind": "profile-data",
        "meta": {"branch": "main", "commit": "abc1234", "run": 1, "sessionId": "20260422T120000"},
        "frame": {"avgMs": 8.3, "p1Ms": 12.0, "p99Ms": 12.0, "sections": {}, "counters": {}},
        "jfr": {
            "hotspots": [],
            "allocations": [],
            "gc": {"pauseCountPerSec": 0.0, "p99PauseMs": 0.0, "events": []},
            "locks": [],
            "threads": [],
        },
        "tracy": {"zones": [], "gpu": [], "frameMarkers": []},
    }
    doc = {
        "schemaVersion": 1,
        "kind": "aggregate",
        "meta": {"branch": "main", "commit": "abc1234", "run": None, "sessionId": "20260422T120000"},
        "frame": pd["frame"],
        "jfr": pd["jfr"],
        "tracy": pd["tracy"],
        "perRun": [pd, pd],
    }
    _validator_for(schema, "Aggregate").validate(doc)


def test_invalid_aggregate_fails():
    schema = load_schema()
    doc = {"schemaVersion": 1, "kind": "aggregate"}  # missing required fields
    import jsonschema
    import pytest

    with pytest.raises(jsonschema.ValidationError):
        _validator_for(schema, "Aggregate").validate(doc)

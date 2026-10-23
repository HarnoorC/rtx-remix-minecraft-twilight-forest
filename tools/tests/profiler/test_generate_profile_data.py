# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import copy
import json
import subprocess
import sys
from importlib.resources import files
from pathlib import Path

import jsonschema

HERE = Path(__file__).parent
MODULE = "rtx_tools.profiler.generate_profile_data"
SCHEMA = files("rtx_tools.profiler").joinpath("profile-schema.json")
BENCH = HERE / "fixtures" / "synth_benchmark.json"
TRACY = HERE / "fixtures" / "synth_tracy.csv"


def _validator_for(schema, def_name):
    root = copy.deepcopy(schema)
    root["$ref"] = f"#/$defs/{def_name}"
    return jsonschema.Draft202012Validator(root)


def run(tmp_path, extra=()):
    out = tmp_path / "profile-data.json"
    subprocess.run(
        [
            sys.executable,
            "-m",
            MODULE,
            "--benchmark",
            str(BENCH),
            "--tracy-csv",
            str(TRACY),
            "--run",
            "1",
            "--out",
            str(out),
            *extra,
        ],
        check=True,
    )
    return json.loads(out.read_text(encoding="utf-8"))


def test_produces_schema_valid_output(tmp_path):
    doc = run(tmp_path)
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    _validator_for(schema, "ProfileData").validate(doc)


def test_meta_populated_from_benchmark(tmp_path):
    doc = run(tmp_path)
    assert doc["meta"]["branch"] == "main"
    assert doc["meta"]["commit"] == "abc1234"
    assert doc["meta"]["run"] == 1
    assert doc["meta"]["sessionId"] == "20260422T120000"


def test_frame_copied_from_summary(tmp_path):
    doc = run(tmp_path)
    assert doc["frame"]["avgMs"] == 8.3
    assert doc["frame"]["p1Ms"] == 12.0
    assert doc["frame"]["sections"]["Chunk.Gen"]["avgMs"] == 2.1


def test_tracy_zones_populated(tmp_path):
    doc = run(tmp_path)
    names = {z["name"] for z in doc["tracy"]["zones"]}
    assert "Chunk.BFS" in names


def test_tracy_health_rejects_anonymous_csv(tmp_path):
    tracy = tmp_path / "anonymous_tracy.csv"
    tracy.write_text(
        "name,src_file,src_line,total_ns,counts,mean_ns,max_ns\n"
        "???,unknown,0,990000000,990,1000000,2000000\n"
        "Useful.zone,useful.cpp,10,10000000,10,1000000,1000000\n",
        encoding="utf-8",
    )
    out = tmp_path / "profile-data.json"
    subprocess.run(
        [
            sys.executable,
            "-m",
            MODULE,
            "--benchmark",
            str(BENCH),
            "--tracy-csv",
            str(tracy),
            "--run",
            "1",
            "--out",
            str(out),
        ],
        check=True,
    )
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["tracy"]["health"]["valid"] is False
    assert "anonymous zones" in doc["tracy"]["health"]["reason"]
    assert doc["tracy"]["health"]["csvQuality"]["anonymousPct"] == 99.0


def test_tracy_health_accepts_tab_separated_names_with_commas(tmp_path):
    tracy = tmp_path / "tracy.csv"
    tracy.write_text(
        "name\tsrc_file\tsrc_line\ttotal_ns\tcounts\tmean_ns\tmax_ns\n"
        "SectionBuilder 67,0,26\tJava\t0\t990000000\t990\t1000000\t2000000\n"
        "Useful.zone\tuseful.cpp\t10\t10000000\t10\t1000000\t1000000\n",
        encoding="utf-8",
    )
    out = tmp_path / "profile-data.json"
    subprocess.run(
        [
            sys.executable,
            "-m",
            MODULE,
            "--benchmark",
            str(BENCH),
            "--tracy-csv",
            str(tracy),
            "--run",
            "1",
            "--out",
            str(out),
        ],
        check=True,
    )
    doc = json.loads(out.read_text(encoding="utf-8"))
    names = {z["name"] for z in doc["tracy"]["zones"]}
    assert "SectionBuilder 67,0,26" in names
    assert doc["tracy"]["health"]["csvQuality"]["rows"] == 2
    assert doc["tracy"]["health"]["csvQuality"]["namedRows"] == 2


def test_jfr_block_empty_when_no_jfr(tmp_path):
    doc = run(tmp_path)
    assert doc["jfr"]["hotspots"] == []
    assert doc["jfr"]["allocations"] == []
    assert doc["jfr"]["phases"] == []
    assert doc["jfr"]["gc"]["events"] == []


def test_missing_tracy_yields_empty_block(tmp_path):
    out = tmp_path / "profile-data.json"
    subprocess.run(
        [sys.executable, "-m", MODULE, "--benchmark", str(BENCH), "--run", "1", "--out", str(out)],
        check=True,
    )
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["tracy"]["zones"] == []


def test_missing_tracy_can_be_optional(tmp_path):
    out = tmp_path / "profile-data.json"
    subprocess.run(
        [sys.executable, "-m", MODULE, "--benchmark", str(BENCH), "--run", "1", "--tracy-optional", "--out", str(out)],
        check=True,
    )
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["tracy"]["zones"] == []
    assert doc["tracy"]["health"]["valid"] is True
    assert doc["tracy"]["health"]["reason"] == "Tracy capture disabled for this run"


def test_missing_benchmark_fails_cleanly(tmp_path):
    out = tmp_path / "profile-data.json"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            MODULE,
            "--benchmark",
            str(tmp_path / "does-not-exist.json"),
            "--run",
            "1",
            "--out",
            str(out),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 2


def test_malformed_benchmark_exits_cleanly(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("this is not json {", encoding="utf-8")
    out = tmp_path / "profile-data.json"
    result = subprocess.run(
        [sys.executable, "-m", MODULE, "--benchmark", str(bad), "--run", "1", "--out", str(out)],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 2
    assert "not valid JSON" in result.stderr


def test_per_frame_copied_through(tmp_path):
    doc = run(tmp_path)
    assert doc.get("perFrame") == [8300000, 8100000, 8500000]

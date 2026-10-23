# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import json
import subprocess
import sys
from pathlib import Path

MODULE = "rtx_tools.profiler.tracy_analyze"
FIXTURE = Path(__file__).parent / "fixtures" / "synth_tracy.csv"


def run_compact(*args):
    result = subprocess.run(
        [sys.executable, "-m", MODULE, str(FIXTURE), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return json.loads(result.stdout)


def test_compact_json_has_zones():
    doc = run_compact("--compact-json")
    names = {z["name"] for z in doc["zones"]}
    assert "Chunk.BFS" in names
    assert "Chunk.Draw" in names


def test_compact_json_zone_fields():
    doc = run_compact("--compact-json")
    bfs = next(z for z in doc["zones"] if z["name"] == "Chunk.BFS")
    assert bfs["count"] == 1000
    assert bfs["meanUs"] == 100.0  # 100000 ns = 100 us
    assert bfs["totalMs"] == 100.0  # 100000000 ns = 100 ms
    assert bfs["maxUs"] == 500.0


def test_compact_json_includes_present_zone():
    # dxvk::D3D9DeviceEx::Present is used to detect frame count; the zone itself
    # is still emitted so downstream consumers can filter if they want.
    doc = run_compact("--compact-json")
    assert any(z["name"] == "dxvk::D3D9DeviceEx::Present" for z in doc["zones"])


def test_unwrapped_csv_can_be_windowed_to_recorded_frames(tmp_path):
    csv_path = tmp_path / "events.csv"
    csv_path.write_text(
        "\n".join(
            [
                "name,src_file,src_line,ns_since_start,exec_time_ns",
                "Work,Java,0,0,10000000",
                "MinecraftClient.render.postFrame,Java,0,10000000,1000",
                "Work,Java,0,20000000,20000000",
                "MinecraftClient.render.postFrame,Java,0,40000000,1000",
                "Work,Java,0,50000000,30000000",
                "MinecraftClient.render.postFrame,Java,0,80000000,1000",
            ]
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, "-m", MODULE, str(csv_path), "--compact-json", "--record-frames", "2"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    doc = json.loads(result.stdout)
    work = next(z for z in doc["zones"] if z["name"] == "Work")
    assert doc["frames"] == 2
    assert doc["window"]["source"] == "MinecraftClient.render.postFrame"
    assert work["count"] == 2
    assert work["totalMs"] == 50.0


def test_unwrapped_csv_prefers_recording_window_and_hides_markers(tmp_path):
    csv_path = tmp_path / "events.csv"
    csv_path.write_text(
        "\n".join(
            [
                "name,src_file,src_line,ns_since_start,exec_time_ns",
                "Warmup,Java,0,0,10000000",
                "Benchmark.recording,Java,0,10000000,40000000",
                "Work,Java,0,20000000,10000000",
                "Work,Java,0,30000000,10000000",
                "MinecraftClient.render.postFrame,Java,0,35000000,1000",
                "Cooldown,Java,0,60000000,10000000",
            ]
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, "-m", MODULE, str(csv_path), "--compact-json", "--record-frames", "2"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    doc = json.loads(result.stdout)
    names = {z["name"] for z in doc["zones"]}
    work = next(z for z in doc["zones"] if z["name"] == "Work")
    assert doc["frames"] == 2
    assert doc["window"]["source"] == "Benchmark.recording"
    assert "Benchmark.recording" not in names
    assert "Warmup" not in names
    assert "Cooldown" not in names
    assert work["count"] == 2


def test_unwrapped_csv_uses_recording_start_end_markers(tmp_path):
    csv_path = tmp_path / "events.csv"
    csv_path.write_text(
        "\n".join(
            [
                "name,src_file,src_line,ns_since_start,exec_time_ns",
                "Warmup,Java,0,0,10000000",
                "benchmark.recording-start,Java,0,10000000,1000",
                "Work,Java,0,20000000,10000000",
                "Work,Java,0,30000000,10000000",
                "benchmark.recording-end,Java,0,50000000,1000",
                "Cooldown,Java,0,60000000,10000000",
            ]
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, "-m", MODULE, str(csv_path), "--compact-json", "--record-frames", "2"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    doc = json.loads(result.stdout)
    names = {z["name"] for z in doc["zones"]}
    work = next(z for z in doc["zones"] if z["name"] == "Work")
    assert doc["frames"] == 2
    assert doc["window"]["source"] == "benchmark.recording-start/end"
    assert "benchmark.recording-start" not in names
    assert "benchmark.recording-end" not in names
    assert "Warmup" not in names
    assert "Cooldown" not in names
    assert work["count"] == 2


def test_summary_csv_uses_record_frame_count(tmp_path):
    csv_path = tmp_path / "summary.csv"
    csv_path.write_text(
        "\n".join(
            [
                "name,src_file,src_line,total_ns,total_perc,counts,mean_ns,min_ns,max_ns,std_ns",
                "dxvk::D3D9DeviceEx::Present,dx.cpp,1,30000000,100,3,10000000,10000000,10000000,0",
                "Work,Java,0,20000000,50,2,10000000,10000000,10000000,0",
            ]
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, "-m", MODULE, str(csv_path), "--compact-json", "--record-frames", "2"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    doc = json.loads(result.stdout)
    assert doc["frames"] == 2
    assert doc["detectedFrames"] == 3
    assert doc["frameSource"] == "dxvk::D3D9DeviceEx::Present"
    assert doc["csvKind"] == "summary"


def test_summary_csv_detects_minecraft_render_frames(tmp_path):
    csv_path = tmp_path / "summary.csv"
    csv_path.write_text(
        "\n".join(
            [
                "name,src_file,src_line,total_ns,total_perc,counts,mean_ns,min_ns,max_ns,std_ns",
                "MinecraftClient.render,Java,0,30000000,100,3,10000000,10000000,10000000,0",
                "Work,Java,0,20000000,50,2,10000000,10000000,10000000,0",
            ]
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, "-m", MODULE, str(csv_path), "--compact-json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    doc = json.loads(result.stdout)
    assert doc["frames"] == 3
    assert doc["detectedFrames"] == 3
    assert doc["frameSource"] == "MinecraftClient.render"


def test_summary_tsv_preserves_zone_names_with_commas(tmp_path):
    csv_path = tmp_path / "summary.csv"
    csv_path.write_text(
        "\n".join(
            [
                "name\tsrc_file\tsrc_line\ttotal_ns\ttotal_perc\tcounts\tmean_ns\tmin_ns\tmax_ns\tstd_ns",
                "SectionBuilder 67,0,26\tJava\t0\t30000000\t100\t3\t10000000\t10000000\t10000000\t0",
                "WorldRender.END\tJava\t0\t20000000\t50\t2\t10000000\t10000000\t10000000\t0",
            ]
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, "-m", MODULE, str(csv_path), "--compact-json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    doc = json.loads(result.stdout)
    assert any(z["name"] == "SectionBuilder 67,0,26" for z in doc["zones"])
    assert doc["detectedFrames"] == 2
    assert doc["frameSource"] == "WorldRender.END"


def test_compact_json_limits_zone_count_by_default(tmp_path):
    csv_path = tmp_path / "summary.csv"
    lines = ["name,src_file,src_line,total_ns,total_perc,counts,mean_ns,min_ns,max_ns,std_ns"]
    for i in range(505):
        lines.append(f"Zone{i},Java,0,{1000000 + i},1,1,{1000000 + i},0,{1000000 + i},0")
    csv_path.write_text("\n".join(lines), encoding="utf-8")

    limited = subprocess.run(
        [sys.executable, "-m", MODULE, str(csv_path), "--compact-json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    unlimited = subprocess.run(
        [sys.executable, "-m", MODULE, str(csv_path), "--compact-json", "--compact-zone-limit", "0"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )

    assert len(json.loads(limited.stdout)["zones"]) == 500
    assert len(json.loads(unlimited.stdout)["zones"]) == 505

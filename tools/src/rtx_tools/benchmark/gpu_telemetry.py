# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""GPU state sampled from nvidia-smi while the benchmark client runs.

A box that leaves P0, throttles, or lost its power tuning renders the same
scene slower for reasons the code under test cannot influence. The poll loop
records one sample per tick tagged with the benchmark state, so the manifest
can say how the GPU behaved during the recording window rather than at an
idle preflight, where a healthy card sits in P8 anyway.
"""

from __future__ import annotations

import os
import shutil
import time
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any

from . import util

QUERY_FIELDS = (
    "pstate",
    "clocks.gr",
    "clocks.max.gr",
    "power.draw",
    "power.limit",
    "temperature.gpu",
    "clocks_event_reasons.active",
)

# Bit values of clocks_event_reasons.active (nvmlClocksEventReason* in nvml.h).
EVENT_REASON_BITS = {
    0x1: "gpu_idle",
    0x2: "applications_clocks_setting",
    0x4: "sw_power_cap",
    0x8: "hw_slowdown",
    0x10: "sync_boost",
    0x20: "sw_thermal_slowdown",
    0x40: "hw_thermal_slowdown",
    0x80: "hw_power_brake_slowdown",
    0x100: "display_clock_setting",
}

# Reasons that mean heat or power delivery held the GPU below its clocks.
# sw_power_cap is deliberately absent: a path tracer sits at the board power
# limit by design, so that flag is the normal state of a healthy run.
SLOWDOWN_REASONS = ("hw_slowdown", "sw_thermal_slowdown", "hw_thermal_slowdown", "hw_power_brake_slowdown")

RECORDING_STATE = "RECORDING"
STARTUP_PHASE = "startup"
QUERY_TIMEOUT_SECONDS = 10


def nvidia_smi_path() -> str | None:
    found = shutil.which("nvidia-smi")
    if found:
        return found
    system32 = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "nvidia-smi.exe"
    return str(system32) if system32.exists() else None


def query_nvidia_smi(executable: str | None = None) -> str | None:
    """One CSV line for the first GPU, or None when nvidia-smi is unusable."""
    exe = executable or nvidia_smi_path()
    if not exe:
        return None
    try:
        result = util.run(
            [exe, f"--query-gpu={','.join(QUERY_FIELDS)}", "--format=csv,noheader,nounits"],
            capture=True,
            check=False,
            timeout=QUERY_TIMEOUT_SECONDS,
        )
    except OSError, RuntimeError:
        return None
    if result.returncode != 0:
        return None
    lines = [line for line in (result.stdout or "").splitlines() if line.strip()]
    return lines[0] if lines else None


def _number(text: str, cast: Callable[[str], Any]) -> Any:
    text = text.strip()
    # nvidia-smi prints [N/A] or [Not Supported] for fields the board lacks.
    if not text or text.startswith("["):
        return None
    try:
        return cast(text)
    except ValueError:
        return None


def parse_sample(line: str) -> dict | None:
    parts = [part.strip() for part in (line or "").strip().split(",")]
    if len(parts) != len(QUERY_FIELDS) or not parts[0].startswith("P"):
        return None
    try:
        reasons = int(parts[6], 16)
    except ValueError:
        return None
    return {
        "pstate": parts[0],
        "graphicsClockMhz": _number(parts[1], int),
        "maxGraphicsClockMhz": _number(parts[2], int),
        "powerDrawW": _number(parts[3], float),
        "powerLimitW": _number(parts[4], float),
        "temperatureC": _number(parts[5], int),
        "eventReasons": reasons,
    }


class Sampler:
    """Collects one GPU sample per poll tick, tagged with the benchmark state.

    The first failed query disables the sampler for the rest of the run, so a
    box without nvidia-smi pays for exactly one probe.
    """

    def __init__(
        self,
        query: Callable[[], str | None] = query_nvidia_smi,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._query = query
        self._clock = clock
        self.samples: list[dict] = []
        self.available = True

    def record(self, status: Mapping[str, Any] | None) -> dict | None:
        if not self.available:
            return None
        parsed = parse_sample(self._query() or "")
        if parsed is None:
            self.available = False
            return None
        parsed["t"] = round(self._clock(), 3)
        parsed["phase"] = str((status or {}).get("state") or STARTUP_PHASE)
        self.samples.append(parsed)
        return parsed

    def write(self, path: Path) -> Path | None:
        if not self.samples:
            return None
        util.write_json(path, {"schemaVersion": 1, "fields": list(QUERY_FIELDS), "samples": self.samples})
        return path


def _values(samples: list[Mapping[str, Any]], key: str) -> list[float]:
    return [sample[key] for sample in samples if isinstance(sample.get(key), int | float)]


def summarize(samples: Iterable[Mapping[str, Any]]) -> dict:
    """Recording-phase P-state share, clocks, power, temperature, and throttle shares."""
    all_samples = list(samples)
    recording = [sample for sample in all_samples if sample.get("phase") == RECORDING_STATE]
    summary: dict[str, Any] = {"samples": len(all_samples), "recordingSamples": len(recording)}
    if not recording:
        return summary
    count = len(recording)
    pstates = Counter(str(sample.get("pstate") or "unknown") for sample in recording)
    summary["pstateShare"] = {state: round(n / count, 4) for state, n in sorted(pstates.items())}
    if clocks := _values(recording, "graphicsClockMhz"):
        summary["graphicsClockMhz"] = {
            "min": min(clocks),
            "avg": round(sum(clocks) / len(clocks), 2),
            "max": max(clocks),
        }
    if max_clocks := _values(recording, "maxGraphicsClockMhz"):
        summary["maxGraphicsClockMhz"] = max(max_clocks)
    if power := _values(recording, "powerDrawW"):
        summary["powerDrawW"] = {"avg": round(sum(power) / len(power), 2), "max": max(power)}
    if limits := _values(recording, "powerLimitW"):
        summary["powerLimitW"] = max(limits)
    if temps := _values(recording, "temperatureC"):
        summary["temperatureC"] = {"max": max(temps)}
    reasons = [int(sample.get("eventReasons") or 0) for sample in recording]
    summary["eventReasonShare"] = {
        name: round(sum(1 for mask in reasons if mask & bit) / count, 4)
        for bit, name in EVENT_REASON_BITS.items()
        if name != "gpu_idle"
    }
    return summary


def summarize_result_dir(result_dir: Path) -> dict:
    """Merge every run's gpu_samples.json under result_dir; {} when none exist."""
    per_run: dict[str, dict] = {}
    merged: list[Mapping[str, Any]] = []
    for path in sorted(result_dir.glob("run_*/gpu_samples.json")):
        try:
            doc = util.read_json(path)
        except OSError, ValueError:
            continue
        samples = doc.get("samples") if isinstance(doc, dict) else None
        if not isinstance(samples, list):
            continue
        per_run[path.parent.name] = summarize(samples)
        merged.extend(samples)
    if not per_run:
        return {}
    summary = summarize(merged)
    summary["perRun"] = per_run
    return summary

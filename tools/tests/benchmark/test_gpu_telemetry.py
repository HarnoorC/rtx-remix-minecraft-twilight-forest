# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import json
import tempfile
import unittest
from pathlib import Path

from rtx_tools.benchmark import gpu_telemetry

CSV_LINE = "P0, 2505, 2505, 287.12, 300.00, 71, 0x0000000000000004"


def sample(phase, pstate, clock, power, temp, reasons):
    return {
        "phase": phase,
        "pstate": pstate,
        "graphicsClockMhz": clock,
        "maxGraphicsClockMhz": 2505,
        "powerDrawW": power,
        "powerLimitW": 300.0,
        "temperatureC": temp,
        "eventReasons": reasons,
    }


class GpuTelemetryTests(unittest.TestCase):
    def test_parse_sample_reads_one_nvidia_smi_csv_line(self):
        parsed = gpu_telemetry.parse_sample(CSV_LINE)
        assert parsed is not None

        self.assertEqual(parsed["pstate"], "P0")
        self.assertEqual(parsed["graphicsClockMhz"], 2505)
        self.assertEqual(parsed["maxGraphicsClockMhz"], 2505)
        self.assertAlmostEqual(parsed["powerDrawW"], 287.12)
        self.assertAlmostEqual(parsed["powerLimitW"], 300.0)
        self.assertEqual(parsed["temperatureC"], 71)
        self.assertEqual(parsed["eventReasons"], 0x4)

    def test_parse_sample_treats_not_available_fields_as_missing(self):
        parsed = gpu_telemetry.parse_sample("P8, [N/A], 2505, [N/A], 300.00, 40, 0x0000000000000001")
        assert parsed is not None

        self.assertEqual(parsed["pstate"], "P8")
        self.assertIsNone(parsed["graphicsClockMhz"])
        self.assertIsNone(parsed["powerDrawW"])
        self.assertEqual(parsed["eventReasons"], 0x1)

    def test_parse_sample_rejects_garbage(self):
        self.assertIsNone(gpu_telemetry.parse_sample(""))
        self.assertIsNone(gpu_telemetry.parse_sample("NVIDIA-SMI has failed"))

    def test_sampler_tags_each_sample_with_the_benchmark_state(self):
        lines = iter([CSV_LINE, CSV_LINE, "P2, 1800, 2505, 120.00, 300.00, 60, 0x0000000000000008"])
        sampler = gpu_telemetry.Sampler(query=lambda: next(lines))

        sampler.record(None)
        sampler.record({"state": "WARMUP", "phase": "warmup"})
        sampler.record({"state": "RECORDING", "phase": "recording"})

        phases = [item["phase"] for item in sampler.samples]
        self.assertEqual(phases, ["startup", "WARMUP", "RECORDING"])
        self.assertTrue(sampler.available)

    def test_sampler_goes_inert_when_nvidia_smi_is_unavailable(self):
        calls = []

        def query():
            calls.append(1)
            return None

        sampler = gpu_telemetry.Sampler(query=query)

        sampler.record({"state": "RECORDING"})
        sampler.record({"state": "RECORDING"})

        self.assertFalse(sampler.available)
        self.assertEqual(sampler.samples, [])
        # One failed probe is enough; the poll loop must not pay for nvidia-smi every tick.
        self.assertEqual(len(calls), 1)

    def test_sampler_writes_samples_as_json(self):
        sampler = gpu_telemetry.Sampler(query=lambda: CSV_LINE)
        sampler.record({"state": "RECORDING"})
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "gpu_samples.json"

            written = sampler.write(out)

            self.assertEqual(written, out)
            data = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(data["schemaVersion"], 1)
            self.assertEqual(len(data["samples"]), 1)
            self.assertEqual(data["samples"][0]["phase"], "RECORDING")

    def test_sampler_writes_nothing_when_it_never_sampled(self):
        sampler = gpu_telemetry.Sampler(query=lambda: None)
        sampler.record({"state": "RECORDING"})
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(sampler.write(Path(tmp) / "gpu_samples.json"))

    def test_summarize_reports_recording_phase_pstate_clocks_and_throttle_shares(self):
        samples = [
            sample("WARMUP", "P8", 210, 30.0, 40, 0x1),
            sample("RECORDING", "P0", 2505, 290.0, 70, 0x4),
            sample("RECORDING", "P0", 2490, 295.0, 74, 0x4),
            sample("RECORDING", "P0", 2400, 300.0, 78, 0x4 | 0x40),
            sample("RECORDING", "P2", 1800, 120.0, 60, 0x8),
        ]

        summary = gpu_telemetry.summarize(samples)

        self.assertEqual(summary["samples"], 5)
        self.assertEqual(summary["recordingSamples"], 4)
        self.assertAlmostEqual(summary["pstateShare"]["P0"], 0.75)
        self.assertAlmostEqual(summary["pstateShare"]["P2"], 0.25)
        self.assertEqual(summary["graphicsClockMhz"], {"min": 1800, "avg": 2298.75, "max": 2505})
        self.assertEqual(summary["maxGraphicsClockMhz"], 2505)
        self.assertEqual(summary["powerDrawW"], {"avg": 251.25, "max": 300.0})
        self.assertEqual(summary["powerLimitW"], 300.0)
        self.assertEqual(summary["temperatureC"], {"max": 78})
        self.assertAlmostEqual(summary["eventReasonShare"]["sw_power_cap"], 0.75)
        self.assertAlmostEqual(summary["eventReasonShare"]["hw_thermal_slowdown"], 0.25)
        self.assertAlmostEqual(summary["eventReasonShare"]["hw_slowdown"], 0.25)
        self.assertNotIn("gpu_idle", summary["eventReasonShare"])

    def test_summarize_without_recording_samples_only_counts(self):
        summary = gpu_telemetry.summarize([{"phase": "startup", "pstate": "P8", "eventReasons": 0x1}])

        self.assertEqual(summary, {"samples": 1, "recordingSamples": 0})

    def test_summarize_result_dir_merges_the_samples_of_several_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for run, pstate in (("run_1", "P0"), ("run_2", "P2")):
                (root / run).mkdir()
                doc = {"schemaVersion": 1, "samples": [sample("RECORDING", pstate, 2000, 200.0, 60, 0)]}
                (root / run / "gpu_samples.json").write_text(json.dumps(doc), encoding="utf-8")

            summary = gpu_telemetry.summarize_result_dir(root)

            self.assertEqual(summary["recordingSamples"], 2)
            self.assertAlmostEqual(summary["pstateShare"]["P0"], 0.5)
            self.assertEqual(sorted(summary["perRun"]), ["run_1", "run_2"])
            self.assertAlmostEqual(summary["perRun"]["run_2"]["pstateShare"]["P2"], 1.0)

    def test_summarize_result_dir_without_samples_is_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(gpu_telemetry.summarize_result_dir(Path(tmp)), {})


if __name__ == "__main__":
    unittest.main()

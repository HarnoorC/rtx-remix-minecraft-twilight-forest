# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import datetime as dt
import unittest

from rtx_tools.benchmark import machine


class MachineTests(unittest.TestCase):
    def test_select_gpu_prefers_nvidia_over_first_adapter(self):
        selected = machine.select_gpu(
            [
                {
                    "Name": "AMD Radeon(TM) Graphics",
                    "AdapterCompatibility": "Advanced Micro Devices, Inc.",
                    "AdapterRAM": 536870912,
                    "Status": "OK",
                    "CurrentHorizontalResolution": 3840,
                    "CurrentVerticalResolution": 2160,
                },
                {
                    "Name": "NVIDIA RTX PRO 6000 Blackwell Workstation Edition",
                    "AdapterCompatibility": "NVIDIA",
                    "PNPDeviceID": "PCI\\VEN_10DE&DEV_2BB1",
                    "AdapterRAM": 4293918720,
                    "Status": "OK",
                    "CurrentHorizontalResolution": 2560,
                    "CurrentVerticalResolution": 1440,
                },
            ]
        )

        self.assertEqual(selected["Name"], "NVIDIA RTX PRO 6000 Blackwell Workstation Edition")
        self.assertEqual(selected["selectionIndex"], 1)
        self.assertIn("nvidia", selected["selectionReason"])

    def test_benchmark_gpu_from_system_keeps_selected_driver(self):
        gpu = machine.benchmark_gpu_from_system(
            {
                "gpu": "NVIDIA RTX PRO 6000 Blackwell Workstation Edition/PCIe/SSE2",
                "gpuVendor": "NVIDIA Corporation",
                "glVersion": "4.6.0 NVIDIA 596.36",
            },
            {"DriverVersion": "32.0.15.9636"},
        )

        self.assertEqual(gpu["Name"], "NVIDIA RTX PRO 6000 Blackwell Workstation Edition/PCIe/SSE2")
        self.assertEqual(gpu["DriverVersion"], "32.0.15.9636")
        self.assertEqual(gpu["GL_VENDOR"], "NVIDIA Corporation")

    def test_parse_power_scheme_reads_the_active_plan_name_and_guid(self):
        text = "Power Scheme GUID: 8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c  (High performance)\n"

        power = machine.parse_power_scheme(text)

        self.assertEqual(power["activeScheme"], "High performance")
        self.assertEqual(power["schemeGuid"], "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c")

    def test_parse_power_scheme_returns_nothing_for_unreadable_output(self):
        self.assertEqual(machine.parse_power_scheme(""), {})
        self.assertEqual(machine.parse_power_scheme("powercfg is not recognized"), {})

    def test_uptime_seconds_counts_from_the_last_boot(self):
        now = dt.datetime(2026, 9, 1, 18, 21, 0, tzinfo=dt.UTC)

        self.assertEqual(machine.uptime_seconds("2026-09-01T11:21:00+00:00", now), 7 * 3600)
        self.assertIsNone(machine.uptime_seconds("", now))
        self.assertIsNone(machine.uptime_seconds("not a date", now))

    def test_runner_expectations_are_optional(self):
        self.assertEqual(machine.runner_expectations({}), {})
        self.assertEqual(
            machine.runner_expectations({"RTXREMIX_EXPECT_POWER_PLAN": " ", "RTXREMIX_EXPECT_LOGICAL_PROCESSORS": ""}),
            {},
        )

    def test_runner_expectations_read_environment_independently(self):
        self.assertEqual(
            machine.runner_expectations({"RTXREMIX_EXPECT_POWER_PLAN": " High performance "}),
            {"powerPlan": "High performance"},
        )
        self.assertEqual(
            machine.runner_expectations({"RTXREMIX_EXPECT_LOGICAL_PROCESSORS": "32"}),
            {"logicalProcessors": 32},
        )

    def test_runner_expectations_reject_invalid_processor_counts(self):
        for value in ("0", "-1", "many", "1.5"):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "RTXREMIX_EXPECT_LOGICAL_PROCESSORS"):
                machine.runner_expectations({"RTXREMIX_EXPECT_LOGICAL_PROCESSORS": value})

    def test_off_spec_reasons_is_silent_without_expectations(self):
        info = {"logicalCores": 18, "power": {"activeScheme": "Balanced"}}

        self.assertEqual(machine.off_spec_reasons(info, {}), [])

    def test_off_spec_reasons_flags_a_lost_power_plan_and_missing_cores(self):
        # A reboot can reset tuning without changing the host identity.
        # Such a run must not be compared as though its machine were unchanged.
        info = {"logicalCores": 18, "power": {"activeScheme": "Balanced"}}
        spec = {"powerPlan": "High performance", "logicalProcessors": 32}

        reasons = machine.off_spec_reasons(info, spec)

        self.assertEqual(len(reasons), 2)
        self.assertIn("power plan is Balanced, expected High performance", reasons)
        self.assertIn("18 logical CPUs, expected 32", reasons)

    def test_off_spec_reasons_accepts_a_matching_box(self):
        info = {
            "logicalCores": 32,
            "power": {"activeScheme": "high performance"},
            "gpuTelemetry": {
                "recordingSamples": 120,
                "pstateShare": {"P0": 0.98, "P2": 0.02},
                "eventReasonShare": {"sw_power_cap": 0.6, "hw_thermal_slowdown": 0.0},
            },
        }
        spec = {"powerPlan": "High performance", "logicalProcessors": 32}

        self.assertEqual(machine.off_spec_reasons(info, spec), [])

    def test_off_spec_reasons_flags_a_gpu_that_left_p0_or_throttled_while_recording(self):
        info = {
            "logicalCores": 32,
            "power": {"activeScheme": "High performance"},
            "gpuTelemetry": {
                "recordingSamples": 100,
                "pstateShare": {"P0": 0.6, "P2": 0.4},
                "eventReasonShare": {"sw_power_cap": 0.9, "hw_thermal_slowdown": 0.12},
            },
        }
        spec = {"powerPlan": "High performance", "logicalProcessors": 32}

        reasons = machine.off_spec_reasons(info, spec)

        self.assertEqual(len(reasons), 2)
        self.assertIn("GPU spent 60% of the recording in P0, expected at least 90%", reasons)
        self.assertIn("GPU reported hw_thermal_slowdown in 12% of recording samples", reasons)

    def test_off_spec_reasons_ignores_facts_that_were_not_collected(self):
        spec = {"powerPlan": "High performance", "logicalProcessors": 32}

        self.assertEqual(machine.off_spec_reasons({"logicalCores": 32}, spec), [])
        self.assertEqual(machine.off_spec_reasons({"power": {"activeScheme": "High performance"}}, spec), [])
        self.assertEqual(machine.off_spec_reasons({"gpuTelemetry": {"samples": 0}}, spec), [])


if __name__ == "__main__":
    unittest.main()

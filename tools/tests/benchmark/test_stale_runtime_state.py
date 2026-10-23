# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from conftest import FakeLauncher

from rtx_tools.benchmark import runner


def write_run_dir(root: Path, *names: str) -> Path:
    run_dir = root / "run"
    run_dir.mkdir()
    for name in names:
        (run_dir / name).write_text(f"stale {name}", encoding="utf-8")
    return run_dir


def test_stale_state_includes_the_javaw_cache():
    # Prism starts the game with javaw.exe, which names the runtime's shader cache after itself.
    assert "javaw.dxvk-cache" in runner.STALE_RUNTIME_STATE_FILES


class ParkStaleRuntimeStateTests(unittest.TestCase):
    def test_parks_the_state_files_that_exist_and_leaves_the_rest_of_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = write_run_dir(Path(tmp), "java.dxvk-cache", "metrics.txt", "rtx.conf")
            with patch.object(runner.util, "RUN_DIR", run_dir):
                parked = runner.park_stale_runtime_state()

            assert parked is not None
            self.assertEqual(parked.parent, run_dir / runner.RUN_STATE_ASIDE_DIR_NAME)
            self.assertEqual(sorted(path.name for path in parked.iterdir()), ["java.dxvk-cache", "metrics.txt"])
            self.assertEqual((parked / "java.dxvk-cache").read_text(encoding="utf-8"), "stale java.dxvk-cache")
            self.assertFalse((run_dir / "java.dxvk-cache").exists())
            self.assertFalse((run_dir / "metrics.txt").exists())
            self.assertTrue((run_dir / "rtx.conf").is_file())

    def test_nothing_to_park_touches_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = write_run_dir(Path(tmp), "rtx.conf")
            with patch.object(runner.util, "RUN_DIR", run_dir):
                self.assertIsNone(runner.park_stale_runtime_state())

            self.assertEqual([path.name for path in run_dir.iterdir()], ["rtx.conf"])

    def test_tolerates_a_run_dir_that_does_not_exist_yet(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            with patch.object(runner.util, "RUN_DIR", run_dir):
                self.assertIsNone(runner.park_stale_runtime_state())

            self.assertFalse(run_dir.exists())

    def test_prunes_the_aside_directory_to_the_newest_sets(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = write_run_dir(Path(tmp), "java.dxvk-cache")
            aside = run_dir / runner.RUN_STATE_ASIDE_DIR_NAME
            surplus = 2
            older = [f"20260101_{index:06d}" for index in range(runner.RUN_STATE_ASIDE_KEEP + surplus)]
            for name in older:
                (aside / name).mkdir(parents=True)
                (aside / name / "java.dxvk-cache").write_bytes(b"old")
            with patch.object(runner.util, "RUN_DIR", run_dir):
                parked = runner.park_stale_runtime_state()

            assert parked is not None
            remaining = sorted(path.name for path in aside.iterdir())
            # The new set counts toward the limit, so one more old set goes than the surplus.
            self.assertEqual(remaining, older[surplus + 1 :] + [parked.name])


class LaunchPathsParkStaleStateTests(unittest.TestCase):
    """Every client launch parks the previous session's state before the launcher starts the client."""

    @pytest.fixture(autouse=True)
    def _launcher(self, fake_launcher: FakeLauncher) -> None:
        self.launcher = fake_launcher

    def test_world_launch_parks_before_start(self):
        order = Mock()
        order.start.side_effect = self.launcher.start
        with (
            patch.object(runner, "load_config", return_value={}),
            patch.object(runner, "ensure_no_live_client"),
            patch.object(runner, "ensure_world_staged"),
            patch.object(runner, "resolve_world_name", return_value="DemoWorld"),
            patch.object(runner, "configure_benchmark_selection", return_value=SimpleNamespace(world="DemoWorld")),
            patch.object(runner, "host_arch", return_value="win64"),
            patch.object(runner, "fetch_sdk", return_value=runner.util.PROJECT_DIR / "d3d9.dll"),
            patch.object(runner, "sdk_metadata", return_value={"variant": "release", "arch": "win64"}),
            patch.object(runner, "write_sdk_version"),
            patch.object(runner, "install_fixtures"),
            patch.object(runner, "write_auto_trigger"),
            patch.object(runner, "gradle_env", return_value={}),
            patch.object(runner, "park_stale_runtime_state", order.park),
            patch.object(self.launcher, "start", order.start),
        ):
            runner.launch_client_for_selection(world="DemoWorld", mode="play")

        self.assertEqual([name for name, _, _ in order.mock_calls], ["park", "start"])

    def test_main_menu_launch_parks_before_start(self):
        order = Mock()
        order.start.side_effect = self.launcher.start
        with (
            patch.object(runner, "load_config", return_value={}),
            patch.object(runner, "ensure_no_live_client"),
            patch.object(runner, "host_arch", return_value="win64"),
            patch.object(runner, "fetch_sdk", return_value=runner.util.PROJECT_DIR / "d3d9.dll"),
            patch.object(runner, "resolve_art_pack", return_value=None),
            patch.object(runner, "stage_resource_packs", return_value=[]),
            patch.object(runner, "write_options"),
            patch.object(runner, "write_rtx_settings"),
            patch("pathlib.Path.mkdir"),
            patch.object(runner, "gradle_env", return_value={}),
            patch.object(runner, "park_stale_runtime_state", order.park),
            patch.object(self.launcher, "start", order.start),
        ):
            runner.launch_client_main_menu()

        self.assertEqual([name for name, _, _ in order.mock_calls], ["park", "start"])

    def test_benchmark_launch_parks_before_start(self):
        order = Mock()
        order.start.side_effect = self.launcher.start
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_run_dir(root, "rtx.conf")
            with (
                patch.object(runner.util, "RUN_DIR", run_dir),
                patch.object(runner.util, "PROJECT_DIR", root),
                patch.object(runner, "install_fixtures"),
                patch.object(runner, "write_auto_trigger"),
                patch.object(runner, "windows_crash_dump_dir", return_value=root / "crash-source"),
                patch.object(runner, "crash_dump_snapshot", return_value=set()),
                patch.object(runner, "kill_leftovers"),
                patch.object(runner, "start_tracy_capture", return_value=None),
                patch.object(runner, "collect_windows_crash_dumps", return_value=[]),
                patch.object(runner, "park_stale_runtime_state", order.park),
                patch.object(self.launcher, "start", order.start),
            ):
                selection = runner.BenchmarkSelection(
                    world="DemoWorld",
                    camera="simple",
                    world_dir=root / "fixture",
                    world_path=root / "fixture" / "world",
                    cameras_dir=root / "fixture" / "cameras",
                    camera_path=root / "fixture" / "cameras" / "simple.json",
                )
                runner.run_client_once(
                    {"pollTimeoutSeconds": 0}, selection, None, root / "runClient.log", True, "win64"
                )

        self.assertEqual([name for name, _, _ in order.mock_calls], ["park", "start"])


if __name__ == "__main__":
    unittest.main()

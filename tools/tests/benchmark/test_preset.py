# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest

from rtx_tools.benchmark import runner

pytestmark = pytest.mark.usefixtures("isolated_tools_config")


class ConfiguredPresetTests(unittest.TestCase):
    def test_the_pinned_preset_is_read_from_the_render_block(self):
        self.assertEqual("high", runner.configured_preset({"render": {"preset": "high"}}))

    def test_an_absent_preset_means_custom(self):
        self.assertEqual(runner.CUSTOM_PRESET, runner.configured_preset({"render": {}}))

    def test_an_unknown_preset_fails_loudly_rather_than_measuring_the_wrong_tier(self):
        with self.assertRaises(RuntimeError) as caught:
            runner.configured_preset({"render": {"preset": "ultraa"}})
        self.assertIn("ultraa", str(caught.exception))

    def test_shipped_config_leaves_the_preset_to_in_game_settings(self):
        self.assertEqual(runner.CUSTOM_PRESET, runner.configured_preset(runner.load_config()))


class ConfiguredPresetValueTests(unittest.TestCase):
    def test_a_named_preset_is_passed_to_this_launch(self):
        self.assertEqual("high", runner.configured_preset_value({"render": {"preset": "high"}}))

    def test_custom_passes_nothing_so_remix_keeps_its_own_tier(self):
        self.assertIsNone(runner.configured_preset_value({"render": {"preset": "Custom"}}))
        self.assertIsNone(runner.configured_preset_value({"render": {}}))

    def test_an_unknown_preset_fails_before_launch(self):
        with self.assertRaises(RuntimeError):
            runner.configured_preset_value({"render": {"preset": "ultraa"}})


class PresetOverrideTests(unittest.TestCase):
    def tearDown(self):
        runner.set_runtime_preset_override(None)

    def test_the_command_line_override_wins_over_the_local_config(self):
        runner.util.write_json(
            runner.util.SHARED_CONFIG_PATH.with_name("config.local.json"), {"render": {"preset": "high"}}
        )
        runner.set_runtime_preset_override("low")
        self.assertEqual("low", runner.load_config()["render"]["preset"])


class WriteOptionsTests(unittest.TestCase):
    def written_options(self, render: dict) -> dict[str, str]:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            with patch.object(runner.util, "RUN_DIR", run_dir):
                runner.write_options({"render": render}, resource_pack_files=[])
            lines = (run_dir / "options.txt").read_text(encoding="utf-8").splitlines()
        return dict(line.split(":", 1) for line in lines if ":" in line)

    def test_the_harness_pins_the_world_a_preset_no_longer_sets(self):
        options = self.written_options({"renderDistance": 16, "simulationDistance": 10, "graphicsMode": 2})

        self.assertEqual("16", options["renderDistance"])
        self.assertEqual("10", options["simulationDistance"])
        self.assertEqual("2", options["graphicsMode"])

    def test_unset_world_keys_default_to_the_ultra_world(self):
        options = self.written_options({})

        self.assertEqual("32", options["renderDistance"])
        self.assertEqual("12", options["simulationDistance"])
        self.assertEqual("1", options["graphicsMode"])

    def test_shipped_config_keeps_shared_scene_defaults(self):
        render = runner.load_config()["render"]

        self.assertEqual(32, render["renderDistance"])
        self.assertEqual(12, render["simulationDistance"])
        self.assertEqual(1, render["graphicsMode"])


class WriteRtxSettingsTests(unittest.TestCase):
    PINNED = {"dist.light": 0, "dist.entity": 0, "light.reach": 192}

    def settings_file(self, run_dir: Path) -> Path:
        return run_dir / "config" / runner.RTX_SETTINGS_FILE

    def write_settings_file(self, run_dir: Path, body: str) -> None:
        target = self.settings_file(run_dir)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")

    def read_settings(self, run_dir: Path) -> dict:
        root = json.loads(self.settings_file(run_dir).read_text(encoding="utf-8"))
        self.assertEqual(runner.RTX_SETTINGS_VERSION, root["version"])
        return root["settings"]

    def pin(self, run_dir: Path, mod_settings: dict | None = None) -> None:
        render = {} if mod_settings is None else {"modSettings": mod_settings}
        runner.write_rtx_settings({"render": render}, run_dir=run_dir)

    def test_the_pinned_settings_are_written_to_a_new_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            self.pin(run_dir, self.PINNED)

            self.assertEqual(self.PINNED, self.read_settings(run_dir))

    def test_other_settings_in_the_file_survive_and_pinned_ones_win(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            self.write_settings_file(
                run_dir, json.dumps({"version": 2, "settings": {"framerate.unfocused": 30, "light.reach": 64}})
            )
            self.pin(run_dir, self.PINNED)

            self.assertEqual({"framerate.unfocused": 30, **self.PINNED}, self.read_settings(run_dir))

    def test_a_stale_preset_entry_is_dropped(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            self.write_settings_file(run_dir, json.dumps({"version": 2, "settings": {"preset": "ultra"}}))
            self.pin(run_dir, self.PINNED)

            self.assertEqual(self.PINNED, self.read_settings(run_dir))

    def test_a_file_the_mod_would_not_read_starts_over(self):
        for body in (json.dumps({"version": 1, "settings": {"dist.light": 64}}), "{not json"):
            with self.subTest(body=body), tempfile.TemporaryDirectory() as tmp:
                run_dir = Path(tmp)
                self.write_settings_file(run_dir, body)
                self.pin(run_dir, self.PINNED)

                self.assertEqual(self.PINNED, self.read_settings(run_dir))

    def test_nothing_to_keep_removes_the_file_as_the_mod_does(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            self.write_settings_file(run_dir, json.dumps({"version": 2, "settings": {"preset": "ultra"}}))
            self.pin(run_dir)

            self.assertFalse(self.settings_file(run_dir).exists())

    def test_the_shipped_config_pins_auto_light_and_entity_distances(self):
        self.assertEqual(self.PINNED, runner.load_config()["render"]["modSettings"])


if __name__ == "__main__":
    unittest.main()

# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

import pytest

from rtx_tools.benchmark import runner

pytestmark = pytest.mark.usefixtures("isolated_tools_config")


class ConfigSplitTests(unittest.TestCase):
    def test_load_config_merges_shared_and_benchmark_keys(self):
        config = runner.load_config()

        self.assertIsInstance(config.get("render"), dict)
        self.assertIsInstance(config.get("resourcePack"), dict)

        # Benchmark-only keys must survive the merge.
        self.assertIn("runs", config)
        self.assertIsInstance(config.get("profiling"), dict)

    def test_shipped_fixture_pins_are_complete_and_fetchable(self):
        config = runner.load_config()
        world = config["world"]
        pack = config["resourcePack"]

        self.assertTrue(world["name"] and world["camera"])
        self.assertRegex(world["version"], runner.WORLD_VERSION_RE)
        self.assertEqual(pack["mode"], "pinned")
        self.assertTrue(pack["name"] and pack["package"])
        self.assertRegex(pack["version"], runner.PACK_VERSION_RE)
        # Both fixtures move between Packman remotes together, and the mod's own
        # download-only config must define that remote or a fresh clone cannot fetch.
        self.assertEqual(world["remote"], pack["remote"])
        self.assertEqual(config["sdk"]["tracyRemote"], world["remote"])
        packman_config = ET.parse(runner.util.PROJECT_DIR / "packman" / "config.packman.xml").getroot()
        self.assertIn(world["remote"], [remote.get("name") for remote in packman_config.findall("remote2")])
        self.assertFalse(config["render"].get("preset"))

    def _write_local(self, value: dict) -> None:
        runner.util.write_json(runner.util.SHARED_CONFIG_PATH.with_name("config.local.json"), value)

    def test_a_local_world_named_alone_does_not_inherit_the_shipped_pin(self):
        shipped = runner.load_config()["world"]
        self._write_local({"world": {"name": "MyWorld"}})
        config = runner.load_config()

        self.assertEqual(config["world"], {"name": "MyWorld", "remote": shipped["remote"]})
        self.assertIsNone(runner.world_pin_version(config, "MyWorld"))
        self.assertIsNone(runner.world_pin_camera(config, "MyWorld"))
        self.assertEqual(runner.world_package_name("MyWorld", config), runner.WORLD_PACKAGE_PREFIX + "MyWorld")

    def test_an_imported_world_named_alone_stages_its_local_save_without_a_fetch(self):
        self._write_local({"world": {"name": "MyWorld"}})
        with tempfile.TemporaryDirectory() as tmp:
            save = Path(tmp) / "worlds" / "MyWorld" / "world"
            save.mkdir(parents=True)
            (save / "level.dat").write_bytes(b"")
            with (
                patch.object(runner.util, "ASSETS_DIR", Path(tmp)),
                patch.object(runner, "fetch_world", side_effect=AssertionError("the local save must be used")),
            ):
                runner.ensure_world_staged(runner.load_config(), "MyWorld")

    def test_a_local_art_pack_without_a_package_uses_its_own_package(self):
        shipped = runner.load_config()["resourcePack"]
        self._write_local({"resourcePack": {"name": "MyArt", "version": "1.0.0"}})
        config = runner.load_config()
        pack = config["resourcePack"]

        self.assertEqual(runner.resource_pack_package("MyArt", config), "rtx_remix_minecraft_resourcepack_MyArt")
        self.assertNotIn("package", pack)
        self.assertEqual(pack["version"], "1.0.0")
        for key in ("mode", "remote", "stageName"):
            self.assertEqual(pack[key], shipped[key])

    def test_a_local_pin_of_the_shipped_name_keeps_its_other_keys(self):
        shipped = runner.load_config()
        self._write_local(
            {"world": {"name": shipped["world"]["name"], "version": "v9.9.9"}, "resourcePack": {"version": "9.9.9"}}
        )
        config = runner.load_config()

        self.assertEqual(config["world"], {**shipped["world"], "version": "v9.9.9"})
        self.assertEqual(config["resourcePack"], {**shipped["resourcePack"], "version": "9.9.9"})

    def test_a_local_pin_name_with_a_trailing_space_is_still_the_shipped_pin(self):
        shipped = runner.load_config()
        world, pack = shipped["world"], shipped["resourcePack"]
        self._write_local(
            {"world": {"name": f"{world['name']} "}, "resourcePack": {"name": f"{pack['name']} ", "version": "9.9.9"}}
        )
        config = runner.load_config()

        self.assertEqual(config["world"]["version"], world["version"])
        self.assertEqual(config["world"]["camera"], world["camera"])
        self.assertEqual(runner.resource_pack_package(pack["name"], config), pack["package"])

    def test_a_trailing_space_world_name_still_finds_its_pin(self):
        shipped = runner.load_config()
        world, pack = shipped["world"], shipped["resourcePack"]
        self._write_local(
            {
                "world": {"name": f"{world['name']} ", "package": "demo_world"},
                "resourcePack": {"name": f"{pack['name']} "},
            }
        )
        config = runner.load_config()
        name = runner.resolve_world_name(config)

        self.assertEqual(name, world["name"])
        self.assertEqual(runner.configured_world_name(config), name)
        self.assertEqual(runner.world_pin_version(config, name), world["version"])
        self.assertEqual(runner.world_pin_camera(config, name), world["camera"])
        self.assertEqual(runner.world_package_name(name, config), "demo_world")
        with tempfile.TemporaryDirectory() as tmp, patch.object(runner.util, "ASSETS_DIR", Path(tmp)):
            self.assertEqual(runner.world_versions_report(name)["pinned"], world["version"])
            self.assertEqual(runner.resource_pack_versions_report(pack["name"])["pinned"], pack["version"])

    def test_a_world_request_with_stray_spaces_finds_the_pin(self):
        # world fetch or a dashboard launch can pass the name unstripped; the pin compare must strip it.
        config = runner.load_config()
        world = config["world"]
        request = f" {world['name']} "

        self.assertEqual(runner.world_pin_version(config, request), world["version"])
        self.assertEqual(runner.world_pin_camera(config, request), world["camera"])

    def test_a_fixture_art_pack_of_another_name_does_not_inherit_the_shipped_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            world_dir = Path(tmp)
            runner.util.write_json(
                world_dir / "config.json", {"resourcePack": {"name": "FixtureArt", "version": "2.0.0"}}
            )
            config = runner.effective_config_for_world(runner.load_config(), world_dir)

        self.assertEqual(
            runner.resource_pack_package("FixtureArt", config), "rtx_remix_minecraft_resourcepack_FixtureArt"
        )

    def test_benchmark_without_a_world_names_the_missing_setting(self):
        config = runner.load_config()
        config.pop("world")
        with self.assertRaisesRegex(RuntimeError, r"world\.name' and 'world\.version"):
            runner.resolve_world_name(config)


if __name__ == "__main__":
    unittest.main()

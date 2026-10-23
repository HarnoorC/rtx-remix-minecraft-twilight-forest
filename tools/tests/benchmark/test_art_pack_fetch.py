# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest

from rtx_tools.benchmark import runner

pytestmark = pytest.mark.usefixtures("isolated_tools_config")


class ArtPackFetchTests(unittest.TestCase):
    def test_resource_pack_package_name(self):
        self.assertEqual(
            runner.resource_pack_package_name("DemoArt"),
            "rtx_remix_minecraft_resourcepack_DemoArt",
        )

    def test_resource_pack_package_prefers_config_override(self):
        # A deployment can publish under its own package naming convention.
        # resourcePack.package maps the selected pack to that package.
        config = {
            "resourcePack": {
                "mode": "pinned",
                "name": "texture",
                "version": "0.1.0",
                "package": "demo_textures",
            }
        }

        self.assertEqual(
            runner.resource_pack_package("texture", config),
            "demo_textures",
        )
        # Other pack names keep the derived package.
        self.assertEqual(
            runner.resource_pack_package("DemoArt", config),
            "rtx_remix_minecraft_resourcepack_DemoArt",
        )
        # No override configured: derived package.
        self.assertEqual(
            runner.resource_pack_package("texture", {"resourcePack": {"name": "texture"}}),
            "rtx_remix_minecraft_resourcepack_texture",
        )

    def test_validate_resource_pack_version_accepts_bare_and_v_prefixed(self):
        self.assertEqual(runner.validate_resource_pack_version("0.1.0"), "0.1.0")
        self.assertEqual(runner.validate_resource_pack_version("v0.1.0"), "v0.1.0")
        with self.assertRaisesRegex(RuntimeError, "resource pack version"):
            runner.validate_resource_pack_version("latest")

    def test_apply_resource_pack_spec_accepts_bare_versions(self):
        config = {}
        runner._apply_resource_pack_spec(config, "texture@0.1.0")

        self.assertEqual(
            config["resourcePack"],
            {
                "mode": "pinned",
                "name": "texture",
                "version": "0.1.0",
                "package": "rtx_remix_minecraft_resourcepack_texture",
            },
        )

    def test_build_resource_pack_pull_project_xml_contains_package_version_and_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            xml = runner.build_resource_pack_pull_project_xml(
                "rtx_remix_minecraft_resourcepack_DemoArt", "v0.1.0", dest
            )

        self.assertIn("rtx_remix_minecraft_resourcepack_DemoArt", xml)
        self.assertIn("v0.1.0", xml)
        self.assertIn(str(dest.resolve()).replace("\\", "/"), xml)

    def test_fetch_uses_configured_remote_and_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = {
                "resourcePack": {
                    "name": "DemoArt",
                    "package": "demo_textures",
                    "remote": "demo-art",
                },
            }
            manifests = []
            dest = root / "assets" / "resourcepacks" / "DemoArt_v0.1.0"

            def pull(args):
                manifests.append(Path(args[1]).read_text(encoding="utf-8"))
                dest.mkdir()
                (dest / ".demo_textures@v0.1.0").touch()

            with (
                patch.object(runner.util, "ASSETS_DIR", root / "assets"),
                patch.object(runner, "load_config", return_value=config),
                patch.object(runner, "run_packman", side_effect=pull) as run_packman,
            ):
                dest = runner.fetch_resource_pack("DemoArt", version="v0.1.0", config=config)

        args = run_packman.call_args.args[0]
        self.assertEqual(args[0], "pull")
        self.assertIn("demo-art", args)
        self.assertEqual(dest.name, "DemoArt_v0.1.0")
        self.assertNotIn("<import", manifests[0])
        self.assertIn('name="demo_textures"', manifests[0])

    def test_fetch_without_remote_names_the_missing_setting(self):
        with self.assertRaisesRegex(RuntimeError, r"resourcePack\.remote"):
            runner.fetch_resource_pack("DemoArt", version="v0.1.0", config={})


if __name__ == "__main__":
    unittest.main()

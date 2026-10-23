# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from rtx_tools import cli
from rtx_tools.benchmark import runner

pytestmark = pytest.mark.usefixtures("isolated_tools_config")


class ResourcePackOverrideTests(unittest.TestCase):
    def tearDown(self):
        # The runtime override is a module global; never leak it into other tests.
        runner.set_runtime_resource_pack_override(None)

    def test_override_none(self):
        config = {"resourcePack": {"mode": "pinned", "name": "DemoArt", "version": "v0.1.0"}}
        runner._apply_resource_pack_spec(config, "none")
        self.assertEqual(config["resourcePack"]["mode"], "none")

    def test_override_local(self):
        config = {"resourcePack": {}}
        runner._apply_resource_pack_spec(config, "local:C:/work/pack")
        self.assertEqual(config["resourcePack"]["mode"], "local")
        self.assertEqual(config["resourcePack"]["localPath"], "C:/work/pack")

    def test_override_name_at_version_is_pinned(self):
        config = {"resourcePack": {}}
        runner._apply_resource_pack_spec(config, "DemoArt@v0.1.0")
        self.assertEqual(config["resourcePack"]["mode"], "pinned")
        self.assertEqual(config["resourcePack"]["name"], "DemoArt")
        self.assertEqual(config["resourcePack"]["version"], "v0.1.0")

    def test_override_name_at_invalid_version_raises(self):
        with self.assertRaises(RuntimeError):
            runner._apply_resource_pack_spec({"resourcePack": {}}, "DemoArt@1.0")

    def test_override_pinned_keyword(self):
        config = {"resourcePack": {"name": "DemoArt", "version": "v0.1.0"}}
        runner._apply_resource_pack_spec(config, "pinned")
        self.assertEqual(config["resourcePack"]["mode"], "pinned")

    def test_override_none_value_is_noop(self):
        config = {"resourcePack": {"mode": "local"}}
        runner._apply_resource_pack_spec(config, None)
        self.assertEqual(config["resourcePack"]["mode"], "local")

    def test_override_invalid_spec_raises(self):
        with self.assertRaises(RuntimeError):
            runner._apply_resource_pack_spec({"resourcePack": {}}, "garbage")

    def test_runtime_override_flows_through_load_config(self):
        runner.util.write_json(
            runner.util.SHARED_CONFIG_PATH.with_name("config.local.json"),
            {"resourcePack": {"mode": "pinned", "name": "DemoArt", "version": "v1.0.0"}},
        )
        runner.set_runtime_resource_pack_override("none")
        config = runner.load_config()
        self.assertEqual(config["resourcePack"]["mode"], "none")


class ResourcePackFetchTests(unittest.TestCase):
    def test_unpinned_pack_requires_explicit_version(self):
        args = SimpleNamespace(name="OtherArt", version=None)
        config = {"resourcePack": {"mode": "pinned", "name": "PinnedArt", "version": "v1.0.0"}}
        with (
            patch.object(cli.runner, "load_config", return_value=config),
            patch.object(cli.runner, "fetch_resource_pack") as fetch,
            self.assertRaisesRegex(RuntimeError, r"OtherArt.*--version"),
        ):
            cli.cmd_resource_pack_fetch(args)
        fetch.assert_not_called()

    def test_explicit_version_fetches_requested_pack_without_changing_pin(self):
        args = SimpleNamespace(name="OtherArt", version="2.0.0")
        config = {"resourcePack": {"mode": "pinned", "name": "PinnedArt", "version": "v1.0.0"}}
        with (
            patch.object(cli.runner, "load_config", return_value=config),
            patch.object(cli.runner, "fetch_resource_pack") as fetch,
        ):
            cli.cmd_resource_pack_fetch(args)
        fetch.assert_called_once_with("OtherArt", version="2.0.0", config=config)
        self.assertEqual(config["resourcePack"]["version"], "v1.0.0")

    def test_configured_pack_uses_its_pinned_version(self):
        args = SimpleNamespace(name=None, version=None)
        config = {"resourcePack": {"mode": "pinned", "name": "PinnedArt", "version": "v1.0.0"}}
        with (
            patch.object(cli.runner, "load_config", return_value=config),
            patch.object(cli.runner, "fetch_resource_pack") as fetch,
        ):
            cli.cmd_resource_pack_fetch(args)

        fetch.assert_called_once_with("PinnedArt", version="v1.0.0", config=config)

    def test_configured_pack_name_with_stray_spaces_uses_its_pinned_version(self):
        args = SimpleNamespace(name=None, version=None)
        config = {"resourcePack": {"mode": "pinned", "name": " PinnedArt ", "version": "v1.0.0"}}
        with (
            patch.object(cli.runner, "load_config", return_value=config),
            patch.object(cli.runner, "fetch_resource_pack") as fetch,
        ):
            cli.cmd_resource_pack_fetch(args)

        fetch.assert_called_once_with("PinnedArt", version="v1.0.0", config=config)


if __name__ == "__main__":
    unittest.main()

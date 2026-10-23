# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from rtx_tools import cli


class WorldFetchCliTests(unittest.TestCase):
    def test_explicit_version_fetches_exactly_that_version(self):
        args = SimpleNamespace(world="DemoWorld", version="v0.4.0")
        config = {"world": {"name": "DemoWorld", "version": "v0.6.0"}}
        with (
            patch.object(cli.runner, "load_config", return_value=config),
            patch.object(cli.runner, "fetch_world") as fetch,
        ):
            cli.cmd_world_fetch(args)

        fetch.assert_called_once_with("DemoWorld", version="v0.4.0")

    def test_pinned_version_still_used_when_no_version_given(self):
        args = SimpleNamespace(world=None, version=None)
        config = {"world": {"name": "DemoWorld", "version": "v0.6.0"}}
        with (
            patch.object(cli.runner, "load_config", return_value=config),
            patch.object(cli.runner, "fetch_world") as fetch,
        ):
            cli.cmd_world_fetch(args)

        fetch.assert_called_once_with("DemoWorld", version="v0.6.0")

    def test_unpinned_world_requires_explicit_version(self):
        args = SimpleNamespace(world="OtherWorld", version=None)
        config = {"world": {"name": "DemoWorld", "version": "v0.6.0"}}
        with (
            patch.object(cli.runner, "load_config", return_value=config),
            patch.object(cli.runner, "fetch_world") as fetch,
            self.assertRaisesRegex(RuntimeError, r"OtherWorld.*--version"),
        ):
            cli.cmd_world_fetch(args)
        fetch.assert_not_called()


if __name__ == "__main__":
    unittest.main()

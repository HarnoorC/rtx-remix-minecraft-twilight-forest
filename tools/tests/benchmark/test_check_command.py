# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import argparse
import sys
import unittest
from unittest import mock

import pytest

from rtx_tools import cli
from rtx_tools.benchmark import util

pytestmark = pytest.mark.usefixtures("isolated_tools_config")


class CheckCommandTests(unittest.TestCase):
    def run_check(self):
        with mock.patch.object(util, "run") as run:
            result = cli.cmd_check(argparse.Namespace(fix=False, no_types=False, tests=True))
        self.assertEqual(0, result)
        return run.call_args_list

    def test_runs_mod_owned_suites_in_tools_project(self):
        calls = self.run_check()
        commands = [call.args[0] for call in calls]
        self.assertIn(["ruff", "format", "--check", "src", "tests"], commands)
        self.assertIn(["ruff", "check", "src", "tests"], commands)
        self.assertIn(["ty", "check"], commands)
        self.assertEqual(1, commands.count([sys.executable, "-m", "pytest", "-q"]))
        self.assertEqual(4, len(commands))
        self.assertTrue(all(call.kwargs["cwd"] == util.TOOLS_DIR for call in calls))


if __name__ == "__main__":
    unittest.main()

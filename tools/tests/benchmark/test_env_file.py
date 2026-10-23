# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from rtx_tools.benchmark import util


class EnvFileTests(unittest.TestCase):
    def _load(self, text: str, environ: dict[str, str]) -> dict[str, str]:
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / ".env"
            env_file.write_text(text, encoding="utf-8")
            with patch.object(util.os, "environ", environ):
                util.load_env_file(env_file)
        return environ

    def test_loads_plain_key_value_lines(self):
        environ: dict[str, str] = {}
        self._load("PM_REMOTE_DEMO_ID=abc123\n", environ)

        self.assertEqual(environ["PM_REMOTE_DEMO_ID"], "abc123")

    def test_tolerates_powershell_prefix_quotes_and_comments(self):
        environ: dict[str, str] = {}
        self._load(
            '# packman creds\n\n$env:PM_REMOTE_DEMO_ID=abc123\nPM_REMOTE_DEMO_KEY="s3cr3t=with=equals"\n',
            environ,
        )

        self.assertEqual(environ["PM_REMOTE_DEMO_ID"], "abc123")
        self.assertEqual(environ["PM_REMOTE_DEMO_KEY"], "s3cr3t=with=equals")

    def test_existing_environment_wins(self):
        environ = {"PM_REMOTE_DEMO_ID": "from-shell"}
        self._load("PM_REMOTE_DEMO_ID=from-file\n", environ)

        self.assertEqual(environ["PM_REMOTE_DEMO_ID"], "from-shell")

    def test_missing_file_is_a_noop(self):
        environ: dict[str, str] = {}
        with patch.object(util.os, "environ", environ):
            util.load_env_file(Path(tempfile.gettempdir()) / "does-not-exist-xyz" / ".env")

        self.assertEqual(environ, {})


if __name__ == "__main__":
    unittest.main()

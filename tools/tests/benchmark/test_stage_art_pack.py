# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from rtx_tools.benchmark import runner


class StageArtPackTests(unittest.TestCase):
    def test_append_art_pack_files_adds_pack_last(self):
        art = runner.ResourcePackSource(
            name="rtx-tools-art",
            file_name="rtx-tools-art",
            source_path=Path("ignored"),
        )
        self.assertEqual(
            runner.append_art_pack_files(["world-demo-pbr"], art),
            ["world-demo-pbr", "rtx-tools-art"],
        )

    def test_append_art_pack_files_none_is_noop(self):
        self.assertEqual(runner.append_art_pack_files(["world-demo-pbr"], None), ["world-demo-pbr"])

    def test_write_options_orders_vanilla_fabric_world_then_art(self):
        art = runner.ResourcePackSource(
            name="rtx-tools-art",
            file_name="rtx-tools-art",
            source_path=Path("ignored"),
        )
        with tempfile.TemporaryDirectory() as tmp, patch.object(runner.util, "RUN_DIR", Path(tmp)):
            runner.write_options({}, resource_pack_files=runner.append_art_pack_files(["world-demo-pbr"], art))
            options = (Path(tmp) / "options.txt").read_text(encoding="utf-8")

        packs = next(
            line.removeprefix("resourcePacks:") for line in options.splitlines() if line.startswith("resourcePacks:")
        )
        self.assertEqual(json.loads(packs), ["vanilla", "fabric", "file/world-demo-pbr", "file/rtx-tools-art"])


if __name__ == "__main__":
    unittest.main()

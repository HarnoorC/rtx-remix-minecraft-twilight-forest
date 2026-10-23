# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import io
import tempfile
import unittest
from contextlib import chdir, redirect_stderr
from pathlib import Path
from unittest.mock import patch

import pytest

from rtx_tools.benchmark import runner

pytestmark = pytest.mark.usefixtures("isolated_tools_config")

PINNED = {"resourcePack": {"mode": "pinned", "name": "texture", "version": "0.56.0", "remote": "demo-art"}}


class ArtPackResolveTests(unittest.TestCase):
    def test_none_mode_returns_none(self):
        self.assertIsNone(runner.resolve_art_pack({"resourcePack": {"mode": "none"}}))
        self.assertIsNone(runner.resolve_art_pack({}))

    def test_pinned_mode_names_missing_configuration(self):
        for pack, key in (
            ({"mode": "pinned"}, r"resourcePack\.name"),
            ({"mode": "pinned", "name": "DemoArt"}, r"resourcePack\.version"),
        ):
            with self.subTest(pack=pack), self.assertRaisesRegex(RuntimeError, key):
                runner.resolve_art_pack({"resourcePack": pack})

    def test_local_mode_resolves_dir_with_mcmeta(self):
        with tempfile.TemporaryDirectory() as tmp:
            pack = Path(tmp) / "art"
            pack.mkdir()
            (pack / "pack.mcmeta").write_text("{}", encoding="utf-8")

            source = runner.resolve_art_pack({"resourcePack": {"mode": "local", "localPath": str(pack)}})

        assert source is not None
        self.assertEqual(source.name, "rtx-tools-art")
        self.assertEqual(source.file_name, "rtx-tools-art")
        self.assertEqual(source.source_path, pack)

    def test_local_mode_honors_configured_stage_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            pack = Path(tmp) / "art"
            pack.mkdir()
            (pack / "pack.mcmeta").write_text("{}", encoding="utf-8")
            source = runner.resolve_art_pack(
                {"resourcePack": {"mode": "local", "localPath": str(pack), "stageName": "demo-art"}}
            )

        assert source is not None
        self.assertEqual(source.name, "demo-art")
        self.assertEqual(source.file_name, "demo-art")
        self.assertEqual(source.source_path, pack)

    def test_local_mode_takes_a_relative_path_from_the_repository_root(self):
        # rtx.bat starts the CLI in tools/, so the working directory must not decide where a relative pack is.
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            pack = project / "art"
            pack.mkdir()
            (pack / "pack.mcmeta").write_text("{}", encoding="utf-8")
            (project / "tools").mkdir()
            with patch.object(runner.util, "PROJECT_DIR", project), chdir(project / "tools"):
                source = runner.resolve_art_pack({"resourcePack": {"mode": "local", "localPath": "art"}})

        assert source is not None
        self.assertEqual(source.source_path, pack)

    def test_local_mode_missing_path_raises(self):
        with self.assertRaises(RuntimeError):
            runner.resolve_art_pack({"resourcePack": {"mode": "local", "localPath": "C:/does/not/exist"}})

    def test_local_mode_missing_relative_path_names_the_path_it_tried(self):
        # A value written for another base must show where it was looked for.
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            with patch.object(runner.util, "PROJECT_DIR", project), self.assertRaises(RuntimeError) as raised:
                runner.resolve_art_pack({"resourcePack": {"mode": "local", "localPath": "art/MyPack"}})

        message = str(raised.exception)
        self.assertIn(str(project / "art" / "MyPack"), message)
        self.assertIn("'art/MyPack'", message)
        self.assertIn("a relative path starts at the repository root", message)

    def test_local_mode_requires_a_configured_path(self):
        with self.assertRaisesRegex(RuntimeError, "localPath"):
            runner.resolve_art_pack({"resourcePack": {"mode": "local"}})

    def _resolve_with_failed_download(self, config: dict, packman_error: BaseException | None, **kwargs):
        """Resolve with Packman failing (None: it succeeds but installs nothing); return the result and stderr."""
        stderr = io.StringIO()
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.object(runner.util, "ASSETS_DIR", Path(tmp)),
            patch.object(runner, "run_packman", side_effect=packman_error),
            patch.object(runner.time, "sleep"),
            redirect_stderr(stderr),
        ):
            return runner.resolve_art_pack(config, **kwargs), stderr.getvalue()

    def test_a_failed_pinned_download_is_fatal_by_default(self):
        with self.assertRaisesRegex(runner.FixtureDownloadError, "packman pull failed"):
            self._resolve_with_failed_download(PINNED, RuntimeError("packman pull failed"))

    def test_a_tolerated_failed_download_of_the_configured_pin_warns_once_and_names_its_retry(self):
        for error in (RuntimeError("command failed (1): packman pull"), OSError("network is unreachable"), None):
            with self.subTest(error=error), patch.object(runner, "load_config", return_value=PINNED):
                source, warning = self._resolve_with_failed_download(PINNED, error, tolerate_fetch_failure=True)

            self.assertIsNone(source)
            self.assertEqual(warning.count("warning:"), 1)
            self.assertIn("without the art pack", warning)
            self.assertIn("texture@0.56.0", warning)
            self.assertIn(str(error) if error else "most likely", warning)
            self.assertIn("Retry the download with tools\\rtx.bat resourcepack fetch texture.", warning)

    def test_a_tolerated_failed_download_of_another_pack_leaves_the_retry_to_the_next_launch(self):
        fixture_pack = {"resourcePack": {**PINNED["resourcePack"], "name": "FixtureArt", "version": "2.0.0"}}
        with patch.object(runner, "load_config", return_value=PINNED):
            source, warning = self._resolve_with_failed_download(
                fixture_pack, RuntimeError("packman pull failed"), tolerate_fetch_failure=True
            )

        self.assertIsNone(source)
        self.assertIn("FixtureArt@2.0.0", warning)
        self.assertIn("The next launch retries the download.", warning)
        self.assertNotIn("resourcepack fetch", warning)

    def test_a_tolerated_fetch_failure_still_rejects_configuration_mistakes(self):
        pinned = PINNED["resourcePack"]
        for pack, message in (
            ({"mode": "local", "localPath": "C:/does/not/exist"}, "localPath"),
            ({"mode": "pinned", "name": "texture"}, r"resourcePack\.version"),
            ({"mode": "banana"}, "invalid resourcePack mode"),
            ({key: value for key, value in pinned.items() if key != "remote"}, r"resourcePack\.remote"),
            ({**pinned, "version": "latest"}, "resource pack version must look like"),
        ):
            with self.subTest(pack=pack), self.assertRaisesRegex(RuntimeError, message) as raised:
                self._resolve_with_failed_download(
                    {"resourcePack": pack}, AssertionError("packman must not run"), tolerate_fetch_failure=True
                )
            self.assertNotIsInstance(raised.exception, runner.FixtureDownloadError)

    def test_invalid_mode_raises(self):
        with self.assertRaises(RuntimeError):
            runner.resolve_art_pack({"resourcePack": {"mode": "banana"}})

    def test_locate_pack_root_mcmeta_at_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            (dest / "pack.mcmeta").write_text("{}", encoding="utf-8")
            self.assertEqual(runner.locate_pack_root(dest), dest)

    def test_locate_pack_root_single_subdir_with_mcmeta(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            sub = dest / "inner"
            sub.mkdir()
            (sub / "pack.mcmeta").write_text("{}", encoding="utf-8")
            self.assertEqual(runner.locate_pack_root(dest), sub)

    def test_locate_pack_root_single_zip(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            zip_path = dest / "pack.zip"
            zip_path.write_bytes(b"zip")
            self.assertEqual(runner.locate_pack_root(dest), zip_path)

    def test_locate_pack_root_no_match_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(RuntimeError):
                runner.locate_pack_root(Path(tmp))


if __name__ == "__main__":
    unittest.main()

# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import io
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

import pytest
from conftest import FakeLauncher, FakeProcess

from rtx_tools import cli, client, prism
from rtx_tools.benchmark import runner, screenshots, util

pytestmark = pytest.mark.usefixtures("isolated_tools_config")


class SelectionOptionalStagingTests(unittest.TestCase):
    def test_discover_world_resource_packs_none_returns_empty(self):
        self.assertEqual(runner.discover_world_resource_packs(None), {})

    def test_resolve_resource_pack_files_none_selection_needs_no_pack_by_default(self):
        self.assertEqual(runner.resolve_resource_pack_files({}, None), [])

    def test_resolve_resource_pack_files_none_selection_missing_pack_errors(self):
        config = {"resourcePacks": ["does-not-exist"]}
        with self.assertRaisesRegex(RuntimeError, "main menu"):
            runner.resolve_resource_pack_files(config, None)


class LaunchClientMainMenuTests(unittest.TestCase):
    @pytest.fixture(autouse=True)
    def _launcher(self, fake_launcher: FakeLauncher) -> None:
        self.launcher = fake_launcher

    def test_launches_without_quick_play_world(self):
        config = {}
        with (
            patch.object(runner, "load_config", return_value=config),
            patch.object(runner, "ensure_no_live_client"),
            patch.object(runner, "host_arch", return_value="win64"),
            patch.object(runner, "fetch_sdk", return_value=runner.util.PROJECT_DIR / "d3d9.dll"),
            patch.object(runner, "resolve_art_pack", return_value=None),
            patch.object(runner, "stage_resource_packs", return_value=[]) as stage,
            patch.object(runner, "write_options") as write_options,
            patch.object(runner, "write_rtx_settings") as write_rtx_settings,
            patch("pathlib.Path.mkdir"),
            patch.object(runner, "gradle_env", return_value={}),
            patch.object(runner, "park_stale_runtime_state"),
            patch.object(runner, "benchmark_rtx_config_env") as benchmark_env,
        ):
            runner.launch_client_main_menu(sdk_variant="release", quiet=True)

        # No-world: selection passed to stage_resource_packs is None.
        self.assertIsNone(stage.call_args.args[1])
        write_options.assert_called_once()
        self.assertFalse(write_options.call_args.kwargs.get("pin_display", False))
        write_rtx_settings.assert_called_once_with(config)
        self.assertEqual(self.launcher.prepared, [("win64", True)])
        [request] = self.launcher.requests
        self.assertEqual(request.arch, "win64")
        self.assertIsNone(request.quick_play_world)
        self.assertIsNone(request.preset)
        self.assertIsNone(request.jfr_path)
        self.assertTrue(request.quiet)
        self.assertEqual(request.env, {})
        benchmark_env.assert_not_called()


def test_launch_main_menu_checks_before_staging(fake_launcher: FakeLauncher, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(runner, "ensure_no_live_client", Mock())
    monkeypatch.setattr(runner, "fetch_sdk", Mock(side_effect=AssertionError("fetched the SDK before the check")))
    fake_launcher.block = client.LaunchBlocked("no account")
    with pytest.raises(client.LaunchBlocked):
        runner.launch_client_main_menu(sdk_variant="release")
    assert fake_launcher.prepared == [] and not (util.RUN_DIR / "options.txt").exists()


def test_launch_main_menu_prepares_before_writing_the_game_directory(
    fake_launcher: FakeLauncher, monkeypatch: pytest.MonkeyPatch
):
    order = Mock()
    order.prepare.side_effect = fake_launcher.prepare
    order.stage_resource_packs.return_value = []
    monkeypatch.setattr(fake_launcher, "prepare", order.prepare)
    for name in ("stage_resource_packs", "write_options", "write_rtx_settings"):
        monkeypatch.setattr(runner, name, getattr(order, name))
    monkeypatch.setattr(runner, "load_config", Mock(return_value={}))
    monkeypatch.setattr(runner, "ensure_no_live_client", Mock())
    monkeypatch.setattr(runner, "host_arch", Mock(return_value="win64"))
    monkeypatch.setattr(runner, "fetch_sdk", Mock(return_value=util.PROJECT_DIR / "d3d9.dll"))
    monkeypatch.setattr(runner, "resolve_art_pack", Mock(return_value=None))
    monkeypatch.setattr(runner, "park_stale_runtime_state", Mock())
    monkeypatch.setattr(runner, "gradle_env", Mock(return_value={}))

    runner.launch_client_main_menu(sdk_variant="release", quiet=True)

    # prepare installs into the game directory the launcher owns, so nothing is written there before it.
    names = [name for name, _, _ in order.mock_calls]
    assert names == ["prepare", "stage_resource_packs", "write_options", "write_rtx_settings"]
    assert order.prepare.call_args == call("win64", build=True)


def test_world_launch_checks_first_and_prepares_before_staging(
    fake_launcher: FakeLauncher, monkeypatch: pytest.MonkeyPatch
):
    order = Mock()
    order.check.side_effect = fake_launcher.check
    order.prepare.side_effect = fake_launcher.prepare
    order.fetch_sdk.return_value = util.PROJECT_DIR / "d3d9.dll"
    monkeypatch.setattr(fake_launcher, "check", order.check)
    monkeypatch.setattr(fake_launcher, "prepare", order.prepare)
    for name in ("ensure_no_live_client", "ensure_world_staged", "fetch_sdk", "install_fixtures"):
        monkeypatch.setattr(runner, name, getattr(order, name))
    monkeypatch.setattr(runner, "load_config", Mock(return_value={"render": {"preset": "high"}}))
    monkeypatch.setattr(runner, "resolve_world_name", Mock(return_value="DemoWorld"))
    monkeypatch.setattr(runner, "configure_benchmark_selection", Mock(return_value=SimpleNamespace(world="DemoWorld")))
    monkeypatch.setattr(runner, "host_arch", Mock(return_value="win64"))
    monkeypatch.setattr(runner, "sdk_metadata", Mock(return_value={"variant": "release", "arch": "win64"}))
    monkeypatch.setattr(runner, "write_sdk_version", Mock())
    monkeypatch.setattr(runner, "write_auto_trigger", Mock())
    monkeypatch.setattr(runner, "park_stale_runtime_state", Mock())
    monkeypatch.setattr(runner, "gradle_env", Mock(return_value={"PLAY": "1"}))

    runner.launch_client_for_selection(world="DemoWorld", mode="play", quiet=True)

    names = [name for name, _, _ in order.mock_calls]
    assert names[:2] == ["ensure_no_live_client", "check"]
    assert names.index("prepare") < names.index("install_fixtures")
    assert order.prepare.call_args == call("win64", build=True)
    [request] = fake_launcher.requests
    assert request.arch == "win64"
    assert request.quick_play_world == runner.BENCHMARK_SAVE_NAME
    assert request.preset == "high"
    assert request.jfr_path is None
    assert request.quiet
    assert request.env == {"PLAY": "1"}


class InterruptedGame(FakeProcess):
    """A running game whose wait Ctrl+C interrupts."""

    def poll(self) -> int | None:
        return None

    def wait(self, timeout: float | None = None) -> int:
        raise KeyboardInterrupt


class FailedGame(FakeProcess):
    def wait(self, timeout: float | None = None) -> int:
        return 1


def test_interactive_launch_ends_the_game_on_ctrl_c(fake_launcher: FakeLauncher, monkeypatch: pytest.MonkeyPatch):
    game = InterruptedGame()
    monkeypatch.setattr(fake_launcher, "start", Mock(return_value=game))
    terminate = Mock()
    monkeypatch.setattr(runner, "terminate_process", terminate)

    with pytest.raises(KeyboardInterrupt):
        runner.launch_interactive(client.LaunchRequest(arch="win64", env={}))

    terminate.assert_called_once_with(game, "game client")


def test_interactive_launch_reports_a_game_that_failed(fake_launcher: FakeLauncher, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(fake_launcher, "start", Mock(return_value=FailedGame()))
    fake_launcher.extra_log = "A fatal error has been detected by the Java Runtime Environment"

    with pytest.raises(RuntimeError, match="exited with code 1") as failed:
        runner.launch_interactive(client.LaunchRequest(arch="win64", env={}))

    assert str(fake_launcher.game_dir / "logs" / "fake.log") in str(failed.value)


def test_interactive_launch_without_launcher_logs_points_at_the_game_log(
    fake_launcher: FakeLauncher, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(fake_launcher, "start", Mock(return_value=FailedGame()))

    with pytest.raises(RuntimeError, match="exited with code 1") as failed:
        runner.launch_interactive(client.LaunchRequest(arch="win64", env={}))

    assert str(fake_launcher.game_dir / "logs" / "latest.log") in str(failed.value)


class DisplayPinningTests(unittest.TestCase):
    """Which path pins the display.

    Both paths call load_config(), which merges benchmark/config.json even for
    a play launch, so this cannot be expressed as a config value. These guard
    the flag that expresses it instead."""

    @pytest.fixture(autouse=True)
    def _launcher(self, fake_launcher: FakeLauncher) -> None:
        self.launcher = fake_launcher

    def test_play_launch_leaves_the_display_on_current(self):
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
            patch.object(runner, "install_fixtures") as install_fixtures,
            patch.object(runner, "write_auto_trigger"),
            patch.object(runner, "gradle_env", return_value={}),
            patch.object(runner, "park_stale_runtime_state"),
        ):
            runner.launch_client_for_selection(world="DemoWorld", mode="play")

        self.assertFalse(install_fixtures.call_args.kwargs.get("pin_display", False))
        self.assertEqual(len(self.launcher.requests), 1)

    def test_benchmark_run_pins_the_display(self):
        # Stop the run at the call under test: everything run_client_once does
        # after staging launches a real client, and mocking that whole tail
        # would break on any unrelated change to it.
        class StopAfterStaging(Exception):
            pass

        fixture = runner.util.RUN_DIR / "fixture"
        selection = runner.BenchmarkSelection(
            world="DemoWorld",
            camera="benchmark",
            world_dir=fixture,
            world_path=fixture / "world",
            cameras_dir=fixture / "cameras",
            camera_path=fixture / "cameras" / "benchmark.json",
        )
        with (
            patch.object(runner, "install_fixtures", side_effect=StopAfterStaging) as install_fixtures,
            patch("pathlib.Path.mkdir"),
            patch("pathlib.Path.glob", return_value=[]),
        ):
            with self.assertRaises(StopAfterStaging):
                runner.run_client_once({}, selection, None, runner.util.RUN_DIR / "run.log", True, "win64")

        self.assertTrue(install_fixtures.call_args.kwargs["pin_display"])


class ArtPackFetchFailureTests(unittest.TestCase):
    """A failed download of the shipped art-pack pin, through the real staging path.

    An interactive launch starts without the configured pin. An explicit
    --resource-pack <name>@<version>, a benchmark run and a screenshot refresh
    stop before the game starts, so a request is never silently dropped and
    results stay comparable."""

    @pytest.fixture(autouse=True)
    def _launcher(self, fake_launcher: FakeLauncher) -> None:
        self.launcher = fake_launcher

    def setUp(self):
        self.addCleanup(runner.set_runtime_resource_pack_override, None)
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.run_dir = root / "run"
        world_dir = root / "assets" / "worlds" / "DemoWorld"
        (world_dir / "world").mkdir(parents=True)
        (world_dir / "world" / "level.dat").write_bytes(b"")
        (world_dir / "cameras").mkdir()
        (root / "project").mkdir()
        self.selection = runner.BenchmarkSelection(
            world="DemoWorld",
            camera="benchmark",
            world_dir=world_dir,
            world_path=world_dir / "world",
            cameras_dir=world_dir / "cameras",
            camera_path=world_dir / "cameras" / "benchmark.json",
        )
        self.pin = runner.load_config()["resourcePack"]
        self.stderr = io.StringIO()
        for context in (
            patch.object(runner.util, "RUN_DIR", self.run_dir),
            patch.object(runner.util, "ASSETS_DIR", root / "assets"),
            patch.object(runner.util, "PROJECT_DIR", root / "project"),
            # Packman fails the pull, as it does without a network or a published package.
            patch.object(runner, "run_packman", side_effect=RuntimeError("command failed (1): packman pull")),
            patch.object(runner.time, "sleep"),
            patch.object(runner, "ensure_no_live_client"),
            patch.object(runner, "ensure_world_staged"),
            patch.object(runner, "configure_benchmark_selection", return_value=self.selection),
            patch.object(runner, "host_arch", return_value="win64"),
            patch.object(runner, "fetch_sdk", return_value=root / "d3d9.dll"),
            patch.object(runner, "sdk_metadata", return_value={}),
            patch.object(runner, "write_sdk_version"),
            patch.object(runner, "write_auto_trigger"),
            patch.object(runner, "gradle_env", return_value={}),
            patch.object(runner, "park_stale_runtime_state"),
            redirect_stderr(self.stderr),
        ):
            self.enterContext(context)

    def launch(self, kind: str) -> None:
        if kind == "main menu":
            runner.launch_client_main_menu(sdk_variant="release")
        else:
            runner.launch_client_for_selection(world="DemoWorld", mode="play")

    def game_started(self) -> bool:
        return bool(self.launcher.requests)

    def test_an_interactive_launch_starts_without_an_unavailable_configured_pin(self):
        for override in (None, "pinned"):
            for kind in ("main menu", "world"):
                with self.subTest(override=override, kind=kind):
                    self.launcher.requests.clear()
                    self.stderr.seek(0)
                    self.stderr.truncate()
                    runner.set_runtime_resource_pack_override(override)

                    self.launch(kind)

                    self.assertTrue(self.game_started())
                    options = (self.run_dir / "options.txt").read_text(encoding="utf-8")
                    self.assertIn('resourcePacks:["vanilla","fabric"]', options)
                    self.assertIn(
                        f"Retry the download with tools\\rtx.bat resourcepack fetch {self.pin['name']}.",
                        self.stderr.getvalue(),
                    )

    def test_an_explicit_pack_version_stays_fatal_on_an_interactive_launch(self):
        for kind in ("main menu", "world"):
            with self.subTest(kind=kind):
                runner.set_runtime_resource_pack_override(f"{self.pin['name']}@99.0.0")
                with self.assertRaisesRegex(runner.FixtureDownloadError, "packman pull"):
                    self.launch(kind)
                self.assertFalse(self.game_started())
                self.assertNotIn("without the art pack", self.stderr.getvalue())

    def test_a_benchmark_run_and_a_screenshot_refresh_stop_before_the_game(self):
        with self.assertRaisesRegex(runner.FixtureDownloadError, "packman pull"):
            runner.run_client_once(runner.load_config(), self.selection, None, self.run_dir / "run.log", True, "win64")
        with self.assertRaisesRegex(runner.FixtureDownloadError, "packman pull"):
            screenshots.capture(
                runner.load_config(), self.selection, ["shot"], sdk_variant="release", timeout_seconds=1
            )

        self.assertFalse(self.game_started())
        self.assertNotIn("without the art pack", self.stderr.getvalue())


class CmdLaunchTests(unittest.TestCase):
    def _args(self, **overrides):
        base = dict(
            world=None,
            sdk_variant="release",
            resource_pack=None,
            version=None,
            quiet=False,
        )
        base.update(overrides)
        return SimpleNamespace(**base)

    def test_no_world_launches_main_menu(self):
        with (
            patch.object(runner, "launch_client_main_menu") as main_menu,
            patch.object(runner, "launch_with_resource_pack_override") as world_launch,
            patch.object(runner, "set_runtime_resource_pack_override") as override,
        ):
            self.assertEqual(cli.cmd_launch(self._args(resource_pack="none")), 0)
        main_menu.assert_called_once_with(sdk_variant="release", quiet=False)
        world_launch.assert_not_called()
        override.assert_called_once_with("none")

    def test_world_launches_via_resource_pack_override_helper(self):
        with (
            patch.object(runner, "launch_client_main_menu") as main_menu,
            patch.object(runner, "launch_with_resource_pack_override") as world_launch,
        ):
            self.assertEqual(cli.cmd_launch(self._args(world="DemoWorld")), 0)
        world_launch.assert_called_once()
        self.assertNotIn("username", world_launch.call_args.kwargs)
        main_menu.assert_not_called()


class LaunchParserTests(unittest.TestCase):
    def test_launch_subparser_options_present(self):
        parser = cli.build_parser()
        args = parser.parse_args(
            [
                "launch",
                "--world",
                "DemoWorld",
                "--sdk-variant",
                "tracy",
                "--resource-pack",
                "none",
            ]
        )
        self.assertEqual(args.world, "DemoWorld")
        self.assertEqual(args.sdk_variant, "tracy")
        self.assertEqual(args.resource_pack, "none")
        self.assertIs(args.func, cli.cmd_launch)

    def test_world_launch_has_resource_pack(self):
        parser = cli.build_parser()
        args = parser.parse_args(["world", "launch", "--resource-pack", "pinned"])
        self.assertEqual(args.resource_pack, "pinned")


@pytest.mark.parametrize(
    "argv",
    [["launch", "--username", "Steve"], ["world", "launch", "--username", "Steve"], ["menu", "--username", "Steve"]],
)
def test_cli_rejects_username(argv: list[str], fake_launcher: FakeLauncher, capsys: pytest.CaptureFixture[str]):
    # The game plays as the launcher's signed-in account; there is no player name to choose.
    with pytest.raises(SystemExit):
        cli.main(argv)
    assert "unrecognized arguments: --username" in capsys.readouterr().err


def test_prism_signin_command(fake_launcher: FakeLauncher, capsys: pytest.CaptureFixture[str]):
    assert cli.main(["prism", "signin"]) == 0
    assert fake_launcher.sign_in_opened
    out = capsys.readouterr().out
    assert prism.SIGN_IN_OPENED_STEPS in out
    # Prism is already open: the steps go on from there rather than sending the user back to prism signin.
    assert "Accounts > Manage Accounts > Add Microsoft" in out and "close Prism" in out
    assert "prism signin" not in out


def test_prism_signin_refuses_a_launcher_without_sign_in(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    monkeypatch.setattr(client, "_active", SimpleNamespace(name="other", describe=lambda: "Another launcher"))
    assert cli.main(["prism", "signin"]) == 1
    out = capsys.readouterr().out
    assert "Nothing to sign in to: other does not launch through Prism." in out


def test_prism_signin_is_an_example():
    epilog = cli.build_parser().epilog or ""
    assert "tools\\rtx.bat prism signin" in [line.strip() for line in epilog.splitlines()]


class LaunchWithResourcePackOverrideTests(unittest.TestCase):
    def test_applies_override_then_launches_selection(self):
        with (
            patch.object(runner, "set_runtime_resource_pack_override") as override,
            patch.object(runner, "launch_client_for_selection") as launch,
        ):
            runner.launch_with_resource_pack_override(
                world="DemoWorld",
                sdk_variant="release",
                resource_pack="local:C:/packs/foo",
                version=None,
                quiet=False,
            )
        override.assert_called_once_with("local:C:/packs/foo")
        launch.assert_called_once()
        self.assertEqual(launch.call_args.kwargs["world"], "DemoWorld")

    def test_no_override_when_resource_pack_none(self):
        with (
            patch.object(runner, "set_runtime_resource_pack_override") as override,
            patch.object(runner, "launch_client_for_selection"),
        ):
            runner.launch_with_resource_pack_override(
                world=None,
                sdk_variant="release",
                resource_pack=None,
                version=None,
                quiet=False,
            )
        override.assert_not_called()


if __name__ == "__main__":
    unittest.main()

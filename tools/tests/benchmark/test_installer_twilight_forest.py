# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""How packaging/installer.ps1 installs and removes the pinned Twilight Forest jar, run under Windows PowerShell 5.1 as
packaging/install.bat runs it. The download is stubbed: it records its arguments and writes the bytes in
TWILIGHT_TEST_DOWNLOAD, or fails when that is unset, so no test reaches the network."""

import os
import subprocess
from pathlib import Path

import pytest

from rtx_tools import prism
from rtx_tools.benchmark import util

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows PowerShell runs the installer")

INSTALLER = util.PROJECT_DIR / "packaging" / "installer.ps1"
# Loads the installer's constants and functions without its entry point, as test_installer_prism_jvm.py does, then
# runs Install (Install-TwilightForest) or Remove (Remove-ModArtifacts) against -McDir for -Launcher.
HARNESS = r"""
param([string]$Installer, [string]$Loaded, [string]$McDir, [string]$Launcher, [string]$Action, [string]$Temp)
$ast = [System.Management.Automation.Language.Parser]::ParseFile($Installer, [ref]$null, [ref]$null)
$entryPoint = $ast.EndBlock.Statements[-1]
if ($entryPoint -isnot [System.Management.Automation.Language.TryStatementAst]) {
    throw 'installer.ps1 no longer ends with its entry point'
}
$start = $ast.ParamBlock.Extent.EndOffset
$body = $ast.Extent.Text.Substring($start, $entryPoint.Extent.StartOffset - $start)
[IO.File]::WriteAllText($Loaded, $body, [Text.UTF8Encoding]::new($true))
. $Loaded
$script:SessionTempDir = $Temp
function Invoke-VerifiedDownload {
    param([string]$Url, [string]$Destination, [string]$ExpectedSha256, [string]$ChecksumUrl)
    Write-Host "DOWNLOAD $Url SHA256=$ExpectedSha256 SIDECAR=$ChecksumUrl"
    if (-not $env:TWILIGHT_TEST_DOWNLOAD) { throw 'simulated download failure' }
    [IO.File]::WriteAllText($Destination, $env:TWILIGHT_TEST_DOWNLOAD)
}
switch ($Action) {
    'Install' {
        try { Install-TwilightForest -McDir $McDir -Launcher $Launcher } catch { Write-Host "FAILED $_" }
    }
    'Remove' { Remove-ModArtifacts -McDir $McDir -Launcher $Launcher }
}
"""


def run(tmp_path: Path, action: str, launcher: str, download: str | None = "pinned jar") -> str:
    harness = tmp_path / "harness.ps1"
    harness.write_text(HARNESS, encoding="ascii")
    temp = tmp_path / "session"
    temp.mkdir(exist_ok=True)
    env = dict(os.environ)
    env.pop("TWILIGHT_TEST_DOWNLOAD", None)
    if download is not None:
        env["TWILIGHT_TEST_DOWNLOAD"] = download
    command = [
        "powershell",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(harness),
        "-Installer",
        str(INSTALLER),
        "-Loaded",
        str(tmp_path / "installer-functions.ps1"),
        "-McDir",
        str(tmp_path / "mc"),
        "-Launcher",
        launcher,
        "-Action",
        action,
        "-Temp",
        str(temp),
    ]
    result = subprocess.run(command, capture_output=True, encoding="utf-8", errors="replace", check=False, env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


def mods(tmp_path: Path) -> Path:
    folder = tmp_path / "mc" / "mods"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


PINNED = prism.installer_constant("TWILIGHT_FOREST_JAR")
STALE = "twilightforest-fabric-1.21.1-4.8.700.jar"


def test_install_downloads_the_pinned_jar_against_the_pinned_hash(tmp_path: Path):
    output = run(tmp_path, "Install", "Prism")

    url = prism.installer_constant("TWILIGHT_FOREST_URL")
    sha256 = prism.installer_constant("TWILIGHT_FOREST_SHA256")
    assert f"DOWNLOAD {url} SHA256={sha256} SIDECAR=\n" in output
    assert (mods(tmp_path) / PINNED).read_text() == "pinned jar"
    assert list((tmp_path / "session").iterdir()) == []


def test_install_keeps_an_installed_pinned_jar(tmp_path: Path):
    (mods(tmp_path) / PINNED).write_text("already here")

    output = run(tmp_path, "Install", "Prism")

    assert "DOWNLOAD" not in output
    assert (mods(tmp_path) / PINNED).read_text() == "already here"


def test_prism_upgrade_replaces_other_versions(tmp_path: Path):
    (mods(tmp_path) / STALE).write_text("old")
    (mods(tmp_path) / "another-mod.jar").write_text("other")

    run(tmp_path, "Install", "Prism")

    assert sorted(path.name for path in mods(tmp_path).iterdir()) == sorted([PINNED, "another-mod.jar"])


def test_microsoft_upgrade_leaves_other_versions_and_warns(tmp_path: Path):
    (mods(tmp_path) / STALE).write_text("old")

    output = run(tmp_path, "Install", "Microsoft")

    assert (mods(tmp_path) / STALE).exists()
    assert (mods(tmp_path) / PINNED).exists()
    assert "Fabric will not start with two Twilight Forest versions" in output


def test_failed_download_keeps_the_previous_version(tmp_path: Path):
    (mods(tmp_path) / STALE).write_text("old")

    output = run(tmp_path, "Install", "Prism", download=None)

    assert "FAILED simulated download failure" in output
    assert [path.name for path in mods(tmp_path).iterdir()] == [STALE]


@pytest.mark.parametrize(
    ("launcher", "left"),
    [("Prism", ["another-mod.jar"]), ("Microsoft", ["another-mod.jar", STALE])],
)
def test_uninstall_removes_the_jars_the_installer_owns(tmp_path: Path, launcher: str, left: list[str]):
    for name in (PINNED, STALE, "another-mod.jar"):
        (mods(tmp_path) / name).write_text(name)

    run(tmp_path, "Remove", launcher)

    assert sorted(path.name for path in mods(tmp_path).iterdir()) == sorted(left)

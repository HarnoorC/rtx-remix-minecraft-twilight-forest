# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Fetch the matching Tracy tools and benchmark runtime without PowerShell."""

from __future__ import annotations

import copy
import os
import re
import shutil
import time
import urllib.error
import urllib.request
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

from .. import config as tools_config
from .. import sdk
from . import util

# The SDK vendors Tracy v0.8 (protocol 55). Its Windows tools are x86_64 and
# also run on ARM64 hosts under emulation.
TRACY_VERSION = "0.8"


def _windows_exe(path: Path) -> bool:
    if not path.is_file():
        return False
    with path.open("rb") as stream:
        return stream.read(2) == b"MZ"


def _download_file(url: str, destination: Path) -> None:
    curl = shutil.which("curl.exe")
    last_error = ""
    for attempt in range(1, 5):
        destination.unlink(missing_ok=True)
        if attempt > 1:
            time.sleep(min(10, attempt * 2))
        if curl:
            result = util.run(
                [
                    curl,
                    "--fail",
                    "--location",
                    "--silent",
                    "--show-error",
                    "--retry",
                    "5",
                    "--retry-delay",
                    "2",
                    "--connect-timeout",
                    "30",
                    "--max-time",
                    "300",
                    "--output",
                    destination,
                    url,
                ],
                check=False,
            )
            if result.returncode == 0 and destination.is_file():
                return
            last_error = f"curl.exe exited with code {result.returncode}"
            continue
        try:
            with urllib.request.urlopen(url) as response, destination.open("wb") as output:
                shutil.copyfileobj(response, output)
            return
        except urllib.error.HTTPError as exc:
            last_error = f"HTTP {exc.code} {exc.reason}".rstrip()
        except OSError as exc:
            last_error = str(exc)
    raise RuntimeError(f"download failed after 4 attempts. Last error: {last_error}")


def fetch_tools() -> None:
    """Stage pinned capture/csvexport binaries in tools/tracy-tools.

    Reuse only a matching version with nontrivial Windows executables. Raise
    RuntimeError if downloading, archive validation, or extraction fails.
    """
    tools_dir = util.TOOLS_DIR / "tracy-tools"
    capture = tools_dir / "capture" / "capture.exe"
    csvexport = tools_dir / "csvexport" / "csvexport.exe"
    version_file = tools_dir / "version.txt"
    if capture.is_file() and csvexport.is_file():
        cap_size = capture.stat().st_size
        csv_size = csvexport.stat().st_size
        installed = version_file.read_text(encoding="utf-8-sig").strip() if version_file.is_file() else ""
        if cap_size > 100_000 and csv_size > 100_000 and _windows_exe(capture) and _windows_exe(csvexport):
            if installed == TRACY_VERSION:
                print("Tracy tools already present:")
                print(f"  {capture} ({cap_size} bytes)")
                print(f"  {csvexport} ({csv_size} bytes)")
                print(f"  version: {installed}")
                return

    arch = os.environ.get("PROCESSOR_ARCHITEW6432") or os.environ.get("PROCESSOR_ARCHITECTURE", "")
    if arch.upper() != "AMD64":
        print(f"Host arch '{arch}'; using Tracy's x86_64 Windows tools under emulation.")
    archive_name = f"Tracy-{TRACY_VERSION}.7z"
    url = f"https://github.com/wolfpld/tracy/releases/download/v{TRACY_VERSION}/{archive_name}"
    archive = tools_dir / archive_name
    capture.parent.mkdir(parents=True, exist_ok=True)
    csvexport.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading Tracy v{TRACY_VERSION} from GitHub...")
    try:
        _download_file(url, archive)
    except RuntimeError as exc:
        raise RuntimeError(f"Tracy download failed: {exc}") from exc
    archive_size = archive.stat().st_size
    if archive_size < 1_000_000:
        raise RuntimeError(f"Tracy archive is suspiciously small ({archive_size} bytes); aborting.")
    with archive.open("rb") as stream:
        valid_archive = stream.read(6) == b"7z\xbc\xaf\x27\x1c"
    if not valid_archive:
        archive.unlink()
        raise RuntimeError(f"Tracy archive does not look like a {archive_name} download; aborting.")

    print("Extracting...")
    extract_dir = tools_dir / "_extract"
    if extract_dir.exists():
        shutil.rmtree(extract_dir)
    extract_dir.mkdir()
    try:
        tar = shutil.which("tar.exe")
        if not tar:
            raise RuntimeError(f"tar.exe is required to extract {archive_name} but was not found on PATH.")
        result = util.run([tar, "-xf", archive, "-C", extract_dir], check=False)
        if result.returncode != 0:
            raise RuntimeError(f"Failed to extract {archive_name} with tar.exe")
        sources = []
        for name in ("capture", "csvexport"):
            candidates = (extract_dir / f"tracy-{name}.exe", extract_dir / f"{name}.exe")
            source = next((path for path in candidates if path.is_file()), None)
            if source is None:
                raise RuntimeError(f"{name}.exe not found in downloaded Tracy archive.")
            sources.append(source)
        shutil.copy2(sources[0], capture)
        shutil.copy2(sources[1], csvexport)
    finally:
        shutil.rmtree(extract_dir)
    archive.unlink()
    version_file.write_text(TRACY_VERSION, encoding="utf-8")
    print("Tracy tools ready:")
    print(f"  tracy-capture:   {capture}")
    print(f"  tracy-csvexport: {csvexport}")


def _tracy_version(dependency: ET.Element, platform: str) -> tuple[str, str]:
    """Return the pinned release version and its debugoptimized sibling."""
    package = dependency.find("package")
    assert package is not None  # sdk.pinned_dependency guarantees a versioned package
    release_version = package.attrib["version"]
    if not re.fullmatch(rf".+-{re.escape(platform)}-release", release_version):
        raise RuntimeError(
            f"Expected remix-sdk-{platform} in packman/remix-sdk.packman.xml to end with "
            f"'-{platform}-release': {release_version}"
        )
    return release_version, release_version.removesuffix("-release") + "-debugoptimized"


def _pull_sdk(platform: str) -> None:
    dependency = sdk.pinned_dependency(platform)
    release_version, version = _tracy_version(dependency, platform)
    dep_name = dependency.attrib["name"]
    target = util.PROJECT_DIR / "remix-runtime" / platform
    sentinel = target / ".local-sdk-source"
    if sentinel.is_file():
        contents = sentinel.read_text(encoding="utf-8-sig", errors="replace").rstrip()
        raise RuntimeError(
            f"\nERROR: {dep_name} was staged from a local source:\n{contents}\n\n"
            "Refusing to overwrite. Benchmark will use local SDK overrides only when their\n"
            "d3d9.dll contains Tracy symbols. To switch back to the Packman Tracy SDK,\n"
            "remove the local override with tools\\rtx.bat sdk packman first."
        )
    if sdk.links_to(target, version) and (target / "d3d9.dll").is_file():
        print(f"Already on benchmark Tracy SDK for {platform}: {version}")
        return
    config = tools_config.load_config()
    remote = tools_config.require_setting(config, "sdk.tracyRemote")

    # Pull beside the target and swap only after the package proves complete, so
    # a failed pull leaves the current staging in place.
    temp_target = target.parent / f".packman-tracy-{dep_name}-{uuid.uuid4().hex}"
    pull = copy.deepcopy(dependency)
    pull.set("linkPath", temp_target.as_posix())
    for package in pull.findall("package"):
        if package.get("version") == release_version:
            package.set("version", version)
    try:
        print(f"Pulling benchmark Tracy SDK {dep_name} ({version}) -> {temp_target.as_posix()}")
        reason = ""
        try:
            sdk.pull_packman_dependency(pull, util.PROJECT_DIR / "packman", remote=remote)
        except RuntimeError as error:
            reason = str(error)
        if not reason and not (temp_target / "d3d9.dll").is_file():
            reason = f"Packman pull completed, but d3d9.dll is missing at {temp_target / 'd3d9.dll'}."
        if reason:
            raise RuntimeError(
                f"Benchmark Tracy SDK package is not available for {platform}.\n"
                f"Requested: rtx_remix_runtime@{version}\n"
                f"Derived from: rtx_remix_runtime@{release_version} in packman\\remix-sdk.packman.xml\n"
                f"Dependency: {dep_name}\nReason: {reason}\n\n"
                "Fix: publish the matching -debugoptimized package for the same SDK revision,\n"
                "update packman\\remix-sdk.packman.xml to a release revision that has\n"
                "debugoptimized artifacts, or stage a local debug/Tracy SDK with\n"
                "tools\\rtx.bat sdk local [PATH]. See the job log above for Packman output."
            )
        if target.exists() or target.is_junction() or target.is_symlink():
            print(f"Removing existing SDK target: {target}")
        sdk.remove_target(target)
        temp_target.rename(target)
    finally:
        sdk.remove_target(temp_target)


def fetch_sdk(platform: str) -> None:
    """Stage the pinned debugoptimized SDK for win64, arm64, or all.

    Refuse local overrides and leave existing staging intact if a pull fails or
    lacks d3d9.dll. Junction removal never changes shared Packman cache contents.
    """
    if platform not in {"win64", "arm64", "all"}:
        raise RuntimeError(f"invalid SDK platform: {platform}")
    sdk.packman_cmd()
    for arch in ("win64", "arm64") if platform == "all" else (platform,):
        _pull_sdk(arch)
    print("Benchmark Tracy SDK ready.")

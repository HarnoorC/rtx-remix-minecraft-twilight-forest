# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Runtime SDK sources, local snapshots, and Packman staging."""

from __future__ import annotations

import datetime as dt
import hashlib
import locale
import os
import re
import shutil
import stat
import struct
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from . import config as tools_config
from .benchmark import util


def normalize_arch(arch: str) -> str:
    if arch not in {"win64", "arm64"}:
        raise RuntimeError(f"invalid architecture: {arch!r}; expected win64 or arm64")
    return arch


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_local_sdk_source(source: str) -> dict[str, str]:
    keys = ("source", "staged_at_utc", "staged_by")
    key_pattern = "|".join(re.escape(key) for key in keys)
    fields = {}
    for match in re.finditer(rf"(?:^|\s)({key_pattern}):\s*(.*?)(?=(?:\s(?:{key_pattern}):)|$)", source, re.DOTALL):
        fields[match.group(1)] = " ".join(match.group(2).split()).strip()
    return fields


def sdk_source_status(arch: str) -> dict[str, Any]:
    """Describe the configured SDK source and whether its staged copy is current.

    A local SDK is a snapshot, not a live link to dxvk-remix/_output.
    Comparing the source and staged DLLs makes refreshes visible to the CLI
    and interactive launcher.
    """
    arch = normalize_arch(arch)
    sdk_dir = util.PROJECT_DIR / "remix-runtime" / arch
    dll = sdk_dir / "d3d9.dll"
    sentinel = sdk_dir / ".local-sdk-source"
    source_fields: dict[str, str] = {}
    sentinel_error = ""
    if sentinel.exists():
        try:
            source_fields = parse_local_sdk_source(sentinel.read_text(encoding="utf-8", errors="replace"))
        except OSError as exc:
            sentinel_error = str(exc)

    source_text = source_fields.get("source", "")
    source_path = util.project_path(source_text).resolve() if source_text else None
    source_dll = source_path / "d3d9.dll" if source_path else None
    source_path_exists = bool(source_path and source_path.is_dir())
    source_dll_exists = bool(source_dll and source_dll.is_file())
    dll_exists = dll.is_file()
    source_matches_staged: bool | None = None
    comparison_error = ""
    staged_hash = ""
    source_hash = ""

    if sentinel.exists() and source_dll_exists and dll_exists and source_dll is not None:
        try:
            source_hash = file_sha256(source_dll)
            staged_hash = file_sha256(dll)
            source_matches_staged = source_hash == staged_hash
        except OSError as exc:
            comparison_error = str(exc)

    if not sentinel.exists():
        state = "packman-ready" if dll_exists else "packman-missing"
    elif sentinel_error or not source_text:
        state = "local-source-unknown"
    elif not source_dll_exists:
        state = "local-source-missing"
    elif not dll_exists or source_matches_staged is False:
        state = "local-refresh-available"
    elif source_matches_staged is True:
        state = "local-current"
    else:
        state = "local-comparison-unavailable"

    return {
        "arch": arch,
        "sourceType": "local" if sentinel.exists() else "packman",
        "state": state,
        "sdkDir": str(sdk_dir),
        "dll": str(dll),
        "dllExists": dll_exists,
        "sentinel": str(sentinel),
        "sentinelError": sentinel_error,
        "sourcePath": source_text,
        "sourcePathExists": source_path_exists,
        "sourceDll": str(source_dll) if source_dll else "",
        "sourceDllExists": source_dll_exists,
        "sourceMatchesStaged": source_matches_staged,
        "needsRestage": state == "local-refresh-available",
        "canRestage": sentinel.exists() and source_dll_exists,
        "stagedAtUtc": source_fields.get("staged_at_utc", ""),
        "stagedBy": source_fields.get("staged_by", ""),
        "stagedDllSha256Short": staged_hash[:12],
        "sourceDllSha256Short": source_hash[:12],
        "comparisonError": comparison_error,
    }


def default_local_sdk_source() -> Path:
    """Return the configured local runtime output, or the sibling-checkout default."""
    config = tools_config.load_config()
    return util.project_path(str(config.get("sdk", {}).get("localPath") or "../dxvk-remix/_output"))


def stage_local_sdk(arch: str, source: object = None) -> dict[str, Any]:
    """Stage a local dxvk build, reusing the recorded source when possible."""
    arch = normalize_arch(arch)
    source_text = str(source or "").strip()
    if not source_text:
        current = sdk_source_status(arch)
        source_text = str(current.get("sourcePath") or default_local_sdk_source())
    source_path = util.project_path(source_text).resolve()
    source_dll = source_path / "d3d9.dll"
    if not source_path.is_dir():
        raise RuntimeError(
            f"Local SDK source directory not found: {source_path} ({util.RELATIVE_PATH_BASE}). "
            "Build/install dxvk-remix into _output, or pass --path explicitly."
        )
    if not source_dll.is_file():
        raise RuntimeError(f"Local SDK source does not contain d3d9.dll: {source_dll}")

    # Keep the lexical staging path here. When Packman is active it is a
    # junction, and resolving it would compare against the shared cache target
    # rather than the directory that will be replaced.
    target_dir = (util.PROJECT_DIR / "remix-runtime" / arch).absolute()
    if source_path == target_dir or source_path in target_dir.parents or target_dir in source_path.parents:
        raise RuntimeError(
            f"Local SDK source cannot overlap the staging target: {target_dir}. "
            "Pass the dxvk-remix _output directory instead."
        )

    validate_runtime_arch(source_dll, arch)
    remove_target(target_dir)
    print(f"Copying {source_path} -> {target_dir}")
    shutil.copytree(source_path, target_dir)
    sentinel = target_dir / ".local-sdk-source"
    sentinel.write_text(
        f"source: {source_path}\n"
        f"staged_at_utc: {dt.datetime.now(dt.UTC):%Y-%m-%dT%H:%M:%SZ}\n"
        f"staged_by: {os.environ.get('USERNAME', '')}\n",
        encoding="utf-8",
    )
    return sdk_source_status(arch)


def restage_local_sdk(arch: str) -> dict[str, Any]:
    """Refresh the staged SDK from the path recorded in its local sentinel."""
    arch = normalize_arch(arch)
    current = sdk_source_status(arch)
    if current["sourceType"] != "local":
        raise RuntimeError(
            f"The {arch} SDK currently uses Packman, so there is no local source to re-stage. "
            "Run 'tools\\rtx.bat sdk local --path PATH' first."
        )
    source = str(current.get("sourcePath") or "")
    if not source:
        raise RuntimeError(
            f"The local SDK sentinel does not record a source path: {current['sentinel']}. "
            "Run 'tools\\rtx.bat sdk local --path PATH' to repair it."
        )
    if not current["sourceDllExists"]:
        raise RuntimeError(
            f"The recorded local SDK source does not contain d3d9.dll: {current['sourceDll']}. "
            "Rebuild/install dxvk-remix or run 'tools\\rtx.bat sdk local --path PATH' with another output."
        )
    return stage_local_sdk(arch, source)


def configured_sdk_auto_restage(config: dict) -> bool:
    """Shared config ``sdk.autoRestage``: re-stage a changed local dxvk SDK on launch.

    On unless the config says otherwise, so a developer who rebuilds dxvk and
    launches tests the build they just made; turning it off restores the warning.
    """
    sdk = config.get("sdk")
    return bool(sdk.get("autoRestage", True)) if isinstance(sdk, dict) else True


def set_sdk_auto_restage(enabled: bool) -> None:
    """Persist machine-local SDK auto-restage state without changing defaults."""
    tools_config.update_local_config({"sdk": {"autoRestage": enabled}})


def validate_runtime_arch(dll: Path, arch: str) -> None:
    """Refuse malformed DLLs or the wrong target before touching the staged SDK."""
    expected = {"win64": 0x8664, "arm64": 0xAA64}[normalize_arch(arch)]
    with dll.open("rb") as handle:
        if handle.read(2) != b"MZ":
            raise RuntimeError(f"Invalid PE runtime DLL: {dll}")
        handle.seek(0x3C)
        offset = handle.read(4)
        if len(offset) != 4:
            raise RuntimeError(f"Invalid PE runtime DLL: {dll}")
        handle.seek(struct.unpack("<I", offset)[0])
        header = handle.read(6)
    if len(header) != 6 or header[:4] != b"PE\0\0":
        raise RuntimeError(f"Invalid PE runtime DLL: {dll}")
    actual = struct.unpack("<H", header[4:])[0]
    if actual != expected:
        names = {0x8664: "x64 (AMD64)", 0xAA64: "arm64"}
        raise RuntimeError(
            f"d3d9.dll at {dll.parent} is built for {names.get(actual, f'unknown (0x{actual:04X})')}, "
            f"but you requested --arch {arch} ({names[expected]}). "
            "Rebuild dxvk for the correct arch, or pass --path to a different build tree."
        )


def remove_target(path: Path) -> None:
    """Remove staging paths without traversing junctions or symbolic links."""
    if path.is_junction():
        path.rmdir()  # removes the junction itself, never the cache it points at
    elif path.is_symlink():
        path.unlink()
    elif path.is_dir():
        for child in path.iterdir():
            remove_target(child)
        path.rmdir()
    elif path.exists():
        path.chmod(stat.S_IWRITE)
        path.unlink()


def links_to(path: Path, version: str) -> bool:
    """Whether path is a junction or symlink into the Packman cache entry for version."""
    if not (path.is_junction() or path.is_symlink()):
        return False
    return version.casefold() in os.readlink(path).casefold()


def pinned_dependency(arch: str) -> ET.Element:
    """Read one pinned SDK dependency before any destructive staging work."""
    manifest = util.PROJECT_DIR / "packman" / "remix-sdk.packman.xml"
    name = f"remix-sdk-{normalize_arch(arch)}"
    if not manifest.is_file():
        raise RuntimeError(f"Packman manifest not found at {manifest}. Restore the tracked file.")
    root = ET.parse(manifest).getroot()
    dependency = next((dep for dep in root.findall("dependency") if dep.get("name") == name), None)
    if dependency is None:
        raise RuntimeError(f"Dependency '{name}' not found in {manifest}")
    package = dependency.find("package")
    if package is None or not package.get("version"):
        raise RuntimeError(f"Dependency '{name}' has no pinned package version in {manifest}")
    return dependency


def packman_cmd() -> Path:
    """The vendored Packman entry point, or a clear error when the checkout lacks it."""
    packman = util.PROJECT_DIR / "packman" / "packman.cmd"
    if not packman.is_file():
        raise RuntimeError(f"Packman helper is missing from the checkout: {packman}. Restore the tracked file.")
    return packman


def pull_packman_dependency(dependency: ET.Element, manifest_dir: Path, *, remote: str | None = None) -> None:
    """Pull one dependency, resolving its linkPath against the original manifest."""
    packman = packman_cmd()
    link_path = dependency.get("linkPath")
    if link_path:
        # Do not resolve a junction into its cache target: Packman owns this link.
        dependency.set("linkPath", os.path.abspath(manifest_dir / link_path).replace("\\", "/"))
    project = ET.Element("project", toolsVersion="7.6")
    project.append(dependency)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=util.PROJECT_DIR, prefix=".packman-fetch-", suffix=".tmp.xml", delete=False
    ) as handle:
        temporary_manifest = Path(handle.name)
        ET.ElementTree(project).write(handle, encoding="unicode")
    try:
        args = [str(packman), "pull", str(temporary_manifest), "-p", "windows-x86_64"]
        if remote:
            args.extend(["-r", remote])
        util.run(args, cwd=util.PROJECT_DIR, encoding=locale.getencoding())
    finally:
        temporary_manifest.unlink(missing_ok=True)


def fetch_sdk(arch: str) -> None:
    """Fetch the pinned runtime for one architecture, refusing local overrides."""
    arch = normalize_arch(arch)
    sentinel = util.PROJECT_DIR / "remix-runtime" / arch / ".local-sdk-source"
    if sentinel.exists():
        raise RuntimeError(
            f"remix-sdk-{arch} was staged from a local source:\n{sentinel.read_text(encoding='utf-8').rstrip()}\n"
            f"Refusing to overwrite. To switch back, run: tools\\rtx.bat sdk packman --arch {arch}"
        )
    dependency = pinned_dependency(arch)
    print(f"Pulling remix-sdk-{arch} -> {util.PROJECT_DIR / 'remix-runtime' / arch}")
    pull_packman_dependency(dependency, util.PROJECT_DIR / "packman")


def stage_packman_sdk(arch: str, *, force: bool = False) -> dict[str, Any]:
    """Restore the pinned runtime, discarding a local override only on request."""
    arch = normalize_arch(arch)
    dependency = pinned_dependency(arch)
    package = dependency.find("package")
    assert package is not None
    version = package.attrib["version"]
    target = util.PROJECT_DIR / "remix-runtime" / arch
    if not force and not (target / ".local-sdk-source").exists() and links_to(target, version):
        print(f"Already on packman SDK for {arch} - nothing to do.")
        return sdk_source_status(arch)
    remove_target(target)
    fetch_sdk(arch)
    return sdk_source_status(arch)

# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Probe a staged Remix runtime through the JNI bridge's own API initialization path."""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

INCOMPATIBLE_VERSION = 8
PROBE_TIMEOUT_SECONDS = 30


@dataclass(frozen=True)
class ProbeResult:
    code: int | None
    failure: str | None = None
    runtime: Path | None = None
    override: bool = False

    @property
    def incompatible(self) -> bool:
        return self.code == INCOMPATIBLE_VERSION


def _probe_in_process(bridge: Path, runtime: Path) -> int:
    library = ctypes.CDLL(str(bridge))
    probe = library.remixbridge_probe_runtime
    probe.argtypes = [ctypes.c_wchar_p]
    probe.restype = ctypes.c_int
    return int(probe(str(runtime)))


def _process_arch() -> str | None:
    from .prism import executable_arch

    return executable_arch(Path(sys.executable))


def _probe_in_subprocess(bridge: Path, runtime: Path) -> tuple[int | None, str | None]:
    command = [sys.executable, "-m", __name__, str(bridge), str(runtime)]
    try:
        with tempfile.TemporaryDirectory(prefix="rtx-remix-runtime-probe-") as cwd:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=PROBE_TIMEOUT_SECONDS,
                check=False,
                cwd=cwd,
            )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, str(exc)
    if result.returncode != 0:
        detail = result.stderr.strip() or f"probe process exited with code {result.returncode}"
        return None, detail
    try:
        return int(result.stdout.strip()), None
    except ValueError:
        return None, f"probe returned an invalid result: {result.stdout.strip()!r}"


def probe(project: Path, arch: str) -> ProbeResult | None:
    """Check the built bridge against the runtime install will use, or None when either is absent."""
    from .install import runtime_source

    bridge = project / "build" / "native" / arch / "remixbridge.dll"
    source = runtime_source(project, arch)
    runtime = source / "d3d9.dll"
    if not bridge.is_file() or not runtime.is_file():
        return None

    process_arch = _process_arch()
    if process_arch is not None and process_arch != arch:
        return ProbeResult(
            None,
            f"the tools Python process is {process_arch}, but the selected bridge is {arch}; "
            f"run the tools from a native {arch} Python/uv environment to enable this check "
            f"(current interpreter: {sys.executable})",
            runtime,
            "REMIX_BUILD" in os.environ,
        )
    code, failure = _probe_in_subprocess(bridge, runtime)
    return ProbeResult(code, failure, runtime, "REMIX_BUILD" in os.environ)


def warn(result: ProbeResult | None) -> None:
    """Describe a failed probe without deciding whether the caller should continue."""
    if result is None:
        return
    code, failure = result.code, result.failure
    if failure is not None:
        print(f"WARNING: could not check RTX Remix runtime compatibility before launch ({failure}).")
        return
    if code == 0:
        return
    if code == INCOMPATIBLE_VERSION:
        lines = [
            "WARNING: the selected RTX Remix runtime is incompatible with this checkout's Remix API "
            "(INCOMPATIBLE_VERSION).",
            "         RTX Remix will not initialize with this runtime and mod combination.",
        ]
        if result.override:
            selected = result.runtime.parent if result.runtime else "an override"
            lines.append(f"         Update or unset REMIX_BUILD, which currently selects {selected}.")
        else:
            lines += [
                "         Stage a matching local runtime, use `tools\\rtx.bat sdk packman`, or update the runtime and",
                "         wrapper API together.",
            ]
        print("\n".join(lines))
        return
    print(f"WARNING: the RTX Remix compatibility probe returned error code {code}.")


def warn_if_incompatible(project: Path, arch: str) -> ProbeResult | None:
    """Probe and report compatibility, returning the result so a launcher can choose its policy."""
    result = probe(project, arch)
    warn(result)
    return result


def _main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: python -m rtx_tools.runtime_compat <remixbridge.dll> <d3d9.dll>", file=sys.stderr)
        return 2
    try:
        code = _probe_in_process(Path(argv[0]), Path(argv[1]))
    except (AttributeError, OSError) as exc:
        print(exc, file=sys.stderr)
        return 1
    print(code)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))

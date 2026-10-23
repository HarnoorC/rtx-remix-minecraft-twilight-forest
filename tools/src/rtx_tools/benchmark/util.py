# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import locale
import os
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

# Editable installs retain the repository's shared assets and run directories.
TOOLS_DIR = Path(__file__).resolve().parents[3]
PROJECT_DIR = TOOLS_DIR.parent
BENCHMARK_DIR = Path(__file__).resolve().parent
RESULTS_DIR = TOOLS_DIR / "results"
PRISM_DATA_DIR = PROJECT_DIR / "run-prism"
# The active launcher's game directory; client.use replaces it.
RUN_DIR = PRISM_DATA_DIR / "instances" / "rtx-remix-dev" / ".minecraft"
SHARED_CONFIG_PATH = TOOLS_DIR / "config.json"
ASSETS_DIR = TOOLS_DIR / "assets"


def rel(path: Path, base: Path = RESULTS_DIR) -> str:
    return path.resolve().relative_to(base.resolve()).as_posix()


# For an error about a path that project_path resolved, so a value written for another base is recognizable.
RELATIVE_PATH_BASE = "a relative path starts at the repository root"


def project_path(value: str | os.PathLike[str]) -> Path:
    """A path given on the command line or in configuration, made absolute.

    A relative path starts at the repository root, never at the working
    directory, which rtx.bat sets to tools/ before it starts the CLI. An error
    about a missing path names the path this returns and RELATIVE_PATH_BASE."""
    path = Path(value).expanduser()
    return path if path.is_absolute() else PROJECT_DIR / path


def load_env_file(path: Path | None = None) -> None:
    """Load KEY=VALUE lines from tools/.env into os.environ.

    The git-ignored file holds machine-local environment variables, such as the
    benchmark machine-health expectations. Existing environment variables win.
    Tolerates blank lines, # comments, a PowerShell-style `$env:` key prefix, and
    single/double quotes around the value. Values are never logged."""
    path = TOOLS_DIR / ".env" if path is None else path
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key.startswith("$env:"):
            key = key[len("$env:") :]
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        if key and key not in os.environ:
            os.environ[key] = value


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def console_encoding() -> str:
    """Encoding used by native console tools, independent of Python UTF-8 mode."""
    if os.name == "nt":
        import ctypes

        code_page = ctypes.windll.kernel32.GetConsoleOutputCP() or ctypes.windll.kernel32.GetOEMCP()
        return f"cp{code_page}"
    return locale.getencoding()


def run(
    args: Iterable[str | os.PathLike[str]],
    *,
    cwd: Path = PROJECT_DIR,
    check: bool = True,
    capture: bool = False,
    env: dict[str, str] | None = None,
    timeout: float | None = None,
    encoding: str = "utf-8",
    errors: str = "strict",
) -> subprocess.CompletedProcess[str]:
    cmd = [str(a) for a in args]
    try:
        result = subprocess.run(
            cmd,
            cwd=str(cwd),
            env=env,
            text=True,
            encoding=encoding,
            errors=errors,
            stdout=subprocess.PIPE if capture else None,
            stderr=subprocess.PIPE if capture else None,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"command timed out after {timeout}s: {' '.join(cmd)}") from exc
    if check and result.returncode != 0:
        detail = ""
        if capture:
            detail = "\n" + (result.stdout or "") + (result.stderr or "")
        raise RuntimeError(f"command failed ({result.returncode}): {' '.join(cmd)}{detail}")
    return result


def open_in_browser(path: Path) -> None:
    if sys.platform.startswith("win"):
        os.startfile(str(path))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        run(["open", str(path)], check=False)
    else:
        run(["xdg-open", str(path)], check=False)


def ensure_inside(path: Path, root: Path) -> Path:
    full = path.resolve()
    root_full = root.resolve()
    if full != root_full and root_full not in full.parents:
        raise RuntimeError(f"refusing to operate outside {root_full}: {full}")
    return full

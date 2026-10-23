# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Follow and end a process this program did not start, by its PID, through a Windows process handle, and find the
short form of a path such a process may have been given."""

from __future__ import annotations

import ctypes
import functools
import math
import os
import subprocess
import time
from pathlib import Path

SYNCHRONIZE = 0x00100000
PROCESS_TERMINATE = 0x0001
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
WAIT_OBJECT_0 = 0x0
WAIT_TIMEOUT = 0x102
# The exit code of a process that could not be opened, which is normally one that had already exited: Windows keeps
# no exit code for a PID once the last handle to its process has closed.
UNKNOWN_EXIT_CODE = -1
# The longest single wait, so that Ctrl+C reaches Python while wait() blocks.
WAIT_SLICE_MS = 200


@functools.cache
def _kernel32():
    # Loaded on first use so that importing this module works anywhere.
    if os.name != "nt":
        raise OSError("PidProcess needs Windows")
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    for name, result, arguments in [
        ("OpenProcess", wintypes.HANDLE, [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]),
        ("WaitForSingleObject", wintypes.DWORD, [wintypes.HANDLE, wintypes.DWORD]),
        ("GetExitCodeProcess", wintypes.BOOL, [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]),
        ("TerminateProcess", wintypes.BOOL, [wintypes.HANDLE, wintypes.UINT]),
        ("CloseHandle", wintypes.BOOL, [wintypes.HANDLE]),
        ("GetShortPathNameW", wintypes.DWORD, [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]),
    ]:
        function = getattr(kernel32, name)
        function.restype = result
        function.argtypes = arguments
    return kernel32


def short_path(path: Path) -> Path | None:
    """The 8.3 short form of an existing `path`, which a program may have been given in place of the long form, or
    None when there is none to have. A volume without 8.3 names gives the path back unchanged."""
    if os.name != "nt":
        return None
    kernel32 = _kernel32()
    # The first call reports the buffer size, terminator included; the second the length written, without it.
    size = kernel32.GetShortPathNameW(str(path), None, 0)
    if not size:
        return None
    buffer = ctypes.create_unicode_buffer(size)
    length = kernel32.GetShortPathNameW(str(path), buffer, size)
    return Path(buffer.value) if 0 < length < size else None


class PidProcess:
    """The part of subprocess.Popen that client.GameProcess names, for a process found by its PID. The handle is opened
    at construction, so the PID cannot be reused while this object follows it. Exit codes are unsigned, as Popen's are
    on Windows; a process that cannot be opened reports UNKNOWN_EXIT_CODE."""

    def __init__(self, pid: int) -> None:
        self._pid = pid
        self._returncode: int | None = None
        self._handle = _kernel32().OpenProcess(
            SYNCHRONIZE | PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_TERMINATE, False, pid
        )
        if not self._handle:
            self._handle = None
            self._returncode = UNKNOWN_EXIT_CODE

    @property
    def pid(self) -> int:
        return self._pid

    def poll(self) -> int | None:
        return self._wait_ms(0)

    def wait(self, timeout: float | None = None) -> int:
        """The exit code, raising subprocess.TimeoutExpired if the process outlives `timeout` seconds."""
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            remaining_ms = WAIT_SLICE_MS if deadline is None else math.ceil((deadline - time.monotonic()) * 1000)
            code = self._wait_ms(max(0, min(WAIT_SLICE_MS, remaining_ms)))
            if code is not None:
                return code
            if deadline is not None and time.monotonic() >= deadline:
                raise subprocess.TimeoutExpired(f"process {self._pid}", timeout or 0.0)

    def terminate(self) -> None:
        """End the process with exit code 1, as Popen.terminate does on Windows. An exited process is left alone."""
        if self.poll() is not None:
            return
        if not _kernel32().TerminateProcess(self._handle, 1):
            error = ctypes.get_last_error()
            if self.poll() is None:
                raise ctypes.WinError(error)

    def kill(self) -> None:
        """Windows has one way to end a process, so this is terminate()."""
        self.terminate()

    def _wait_ms(self, milliseconds: int) -> int | None:
        if self._returncode is not None:
            return self._returncode
        kernel32 = _kernel32()
        result = kernel32.WaitForSingleObject(self._handle, milliseconds)
        if result == WAIT_TIMEOUT:
            return None
        if result != WAIT_OBJECT_0:
            raise ctypes.WinError(ctypes.get_last_error())
        code = ctypes.c_ulong()
        if not kernel32.GetExitCodeProcess(self._handle, ctypes.byref(code)):
            raise ctypes.WinError(ctypes.get_last_error())
        self._returncode = code.value
        self._close()
        return self._returncode

    def _close(self) -> None:
        handle = getattr(self, "_handle", None)
        if handle is not None:
            self._handle = None
            _kernel32().CloseHandle(handle)

    def __del__(self) -> None:
        self._close()

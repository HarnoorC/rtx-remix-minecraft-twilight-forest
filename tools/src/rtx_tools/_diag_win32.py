# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Win32 process and window operations for developer hang diagnostics."""

from __future__ import annotations

import ctypes
import os
from collections.abc import Iterator
from contextlib import contextmanager
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProcessInfo:
    pid: int
    path: Path
    working_set: int

    @property
    def is_java(self) -> bool:
        return self.path.stem.lower() in {"java", "javaw"}


@dataclass(frozen=True)
class WindowInfo:
    hwnd: int
    pid: int
    title: str


class _ProcessMemoryCounters(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


class Win32:
    def __init__(self) -> None:
        if os.name != "nt":
            raise RuntimeError("Hang diagnostics require Windows.")
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.ntdll = ctypes.WinDLL("ntdll", use_last_error=True)
        self.enum_callback = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        dword_pointer = ctypes.POINTER(wintypes.DWORD)
        for library, name, result, arguments in [
            (self.user32, "EnumWindows", wintypes.BOOL, [self.enum_callback, wintypes.LPARAM]),
            (self.user32, "IsWindowVisible", wintypes.BOOL, [wintypes.HWND]),
            (self.user32, "GetWindowTextW", ctypes.c_int, [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]),
            (self.user32, "GetWindowThreadProcessId", wintypes.DWORD, [wintypes.HWND, dword_pointer]),
            (self.user32, "GetShellWindow", wintypes.HWND, []),
            (self.user32, "SetForegroundWindow", wintypes.BOOL, [wintypes.HWND]),
            (self.user32, "ShowWindow", wintypes.BOOL, [wintypes.HWND, ctypes.c_int]),
            (
                self.user32,
                "SendMessageTimeoutW",
                wintypes.LPARAM,
                [
                    wintypes.HWND,
                    wintypes.UINT,
                    wintypes.WPARAM,
                    wintypes.LPARAM,
                    wintypes.UINT,
                    wintypes.UINT,
                    ctypes.POINTER(ctypes.c_size_t),
                ],
            ),
            (self.kernel32, "OpenProcess", wintypes.HANDLE, [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]),
            (self.kernel32, "CloseHandle", wintypes.BOOL, [wintypes.HANDLE]),
            (self.kernel32, "WaitForSingleObject", wintypes.DWORD, [wintypes.HANDLE, wintypes.DWORD]),
            (
                self.kernel32,
                "QueryFullProcessImageNameW",
                wintypes.BOOL,
                [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, dword_pointer],
            ),
            (self.kernel32, "K32EnumProcesses", wintypes.BOOL, [dword_pointer, wintypes.DWORD, dword_pointer]),
            (
                self.kernel32,
                "K32GetProcessMemoryInfo",
                wintypes.BOOL,
                [wintypes.HANDLE, ctypes.POINTER(_ProcessMemoryCounters), wintypes.DWORD],
            ),
            (self.ntdll, "NtSuspendProcess", wintypes.LONG, [wintypes.HANDLE]),
            (self.ntdll, "NtResumeProcess", wintypes.LONG, [wintypes.HANDLE]),
        ]:
            function = getattr(library, name)
            function.restype = result
            function.argtypes = arguments

    def visible_windows(self) -> list[WindowInfo]:
        windows = []

        @self.enum_callback
        def visit(hwnd, _parameter):
            if self.user32.IsWindowVisible(hwnd):
                title = ctypes.create_unicode_buffer(256)
                self.user32.GetWindowTextW(hwnd, title, len(title))
                pid = wintypes.DWORD()
                self.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                windows.append(WindowInfo(hwnd, pid.value, title.value))
            return True

        if not self.user32.EnumWindows(visit, 0):
            raise ctypes.WinError(ctypes.get_last_error())
        return windows

    def process_ids(self) -> list[int]:
        capacity = 1024
        while True:
            pids = (wintypes.DWORD * capacity)()
            used = wintypes.DWORD()
            if not self.kernel32.K32EnumProcesses(pids, ctypes.sizeof(pids), ctypes.byref(used)):
                raise ctypes.WinError(ctypes.get_last_error())
            if used.value < ctypes.sizeof(pids):
                return list(pids[: used.value // ctypes.sizeof(wintypes.DWORD)])
            capacity *= 2

    def process(self, pid: int) -> ProcessInfo | None:
        handle = self.kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return None
        try:
            path = ctypes.create_unicode_buffer(32768)
            length = wintypes.DWORD(len(path))
            if not self.kernel32.QueryFullProcessImageNameW(handle, 0, path, ctypes.byref(length)):
                return None
            memory = _ProcessMemoryCounters()
            memory.cb = ctypes.sizeof(memory)
            if not self.kernel32.K32GetProcessMemoryInfo(handle, ctypes.byref(memory), memory.cb):
                return None
            return ProcessInfo(pid, Path(path.value), memory.WorkingSetSize)
        finally:
            self.kernel32.CloseHandle(handle)

    def has_exited(self, pid: int) -> bool:
        handle = self.kernel32.OpenProcess(0x100000, False, pid)  # SYNCHRONIZE
        if not handle:
            error = ctypes.get_last_error()
            if error == 87:  # ERROR_INVALID_PARAMETER: the PID no longer exists.
                return True
            raise ctypes.WinError(error)
        try:
            result = self.kernel32.WaitForSingleObject(handle, 0)
            if result == 0xFFFFFFFF:
                raise ctypes.WinError(ctypes.get_last_error())
            return result == 0
        finally:
            self.kernel32.CloseHandle(handle)

    def shell_window(self) -> int:
        return self.user32.GetShellWindow() or 0

    def foreground(self, hwnd: int) -> None:
        self.user32.SetForegroundWindow(hwnd)

    def show_window(self, hwnd: int, command: int) -> None:
        self.user32.ShowWindow(hwnd, command)

    def responding(self, hwnd: int) -> bool:
        result = ctypes.c_size_t()
        # Match Process.Responding: WM_NULL, SMTO_ABORTIFHUNG, and a five-second timeout.
        return bool(self.user32.SendMessageTimeoutW(hwnd, 0, 0, 0, 2, 5000, ctypes.byref(result)))

    @contextmanager
    def suspended(self, pid: int) -> Iterator[bool]:
        """Hold the target for a dump, always resuming it before releasing the handle."""
        handle = self.kernel32.OpenProcess(0x1F0FFF, False, pid)
        if not handle:
            yield False
            return
        try:
            status = self.ntdll.NtSuspendProcess(handle)
            if status < 0:
                raise RuntimeError(f"NtSuspendProcess failed for PID {pid}: NTSTATUS 0x{status & 0xFFFFFFFF:08X}")
            try:
                yield True
            finally:
                status = self.ntdll.NtResumeProcess(handle)
                if status < 0:
                    raise RuntimeError(f"NtResumeProcess failed for PID {pid}: NTSTATUS 0x{status & 0xFFFFFFFF:08X}")
        finally:
            self.kernel32.CloseHandle(handle)

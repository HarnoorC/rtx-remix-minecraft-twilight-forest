# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Small Windows console UI, using the same console key codes in Terminal and conhost."""

from __future__ import annotations

import ctypes
import os
import shutil
import sys
from ctypes import wintypes
from types import TracebackType


def choice_viewport(count: int, selected: int, capacity: int) -> tuple[int, int]:
    capacity = max(1, capacity)
    if count <= capacity:
        return 0, count
    start = max(0, min(selected - (capacity - 1) // 2, count - capacity))
    return start, capacity


def move_selection(key: str, selected: int, count: int, capacity: int) -> int:
    page = max(1, capacity - 1)
    match key:
        case "up":
            return (selected - 1) % count
        case "down":
            return (selected + 1) % count
        case "pageup":
            return max(0, selected - page)
        case "pagedown":
            return min(count - 1, selected + page)
        case "home":
            return 0
        case "end":
            return count - 1
    return selected


class Console:
    def __enter__(self) -> Console:
        if os.name != "nt" or not sys.stdin.isatty() or not sys.stdout.isatty():
            raise RuntimeError("The menu needs an interactive Windows console. Use rtx menu --mode ... for flag mode.")
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel.GetStdHandle.argtypes = [wintypes.DWORD]
        self.kernel.GetStdHandle.restype = wintypes.HANDLE
        self.kernel.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        self.kernel.GetConsoleMode.restype = wintypes.BOOL
        self.kernel.SetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        self.kernel.SetConsoleMode.restype = wintypes.BOOL
        self.handle = self.kernel.GetStdHandle(-11)
        self.original_mode = wintypes.DWORD()
        if not self.kernel.GetConsoleMode(self.handle, ctypes.byref(self.original_mode)):
            raise ctypes.WinError(ctypes.get_last_error())
        # Windows 10+ conhost and Windows Terminal both support VT output once enabled.
        if not self.kernel.SetConsoleMode(self.handle, self.original_mode.value | 0x0005):
            raise ctypes.WinError(ctypes.get_last_error())
        print("\x1b[?1049h\x1b[?25l", end="", flush=True)
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, traceback: TracebackType | None
    ) -> None:
        print("\x1b[0m\x1b[?25h\x1b[?1049l", end="", flush=True)
        self.kernel.SetConsoleMode(self.handle, self.original_mode.value)

    def clear(self) -> None:
        print("\x1b[2J\x1b[H", end="", flush=True)

    def read_key(self) -> str:
        import msvcrt

        key = msvcrt.getwch()
        if key in {"\x00", "\xe0"}:
            return {
                "H": "up",
                "P": "down",
                "I": "pageup",
                "Q": "pagedown",
                "G": "home",
                "O": "end",
            }.get(msvcrt.getwch(), "")
        if key == "\x03":
            raise KeyboardInterrupt
        return {"\r": "enter", "\x1b": "escape"}.get(key, key)

    def prompt(self, label: str) -> str:
        print("\x1b[?25h", end="", flush=True)
        try:
            return input(f"{label}: ")
        finally:
            print("\x1b[?25l", end="", flush=True)

    def pause(self, message: str) -> None:
        print(f"\n{message}\nPress any key to return...")
        self.read_key()

    def choose(self, title: str, labels: list[str], *, rows: list[str] | None = None, quit_key: bool = False) -> int:
        selected = 0
        header = [*title.splitlines(), *(rows or []), ""]
        while True:
            width, height = shutil.get_terminal_size((80, 25))
            start, length = choice_viewport(len(labels), selected, height - len(header) - 4)
            lines = [(line, "36" if index == 0 else "37") for index, line in enumerate(header)]
            lines.append((f"    ... {start} more above" if start else "", "90"))
            for index in range(start, start + length):
                marker = ">" if index == selected else " "
                lines.append((f"  {marker} {index + 1}) {labels[index]}", "30;46" if index == selected else "37"))
            below = len(labels) - start - length
            lines.append((f"    ... {below} more below" if below else "", "90"))
            lines.append(("Up/Down, PgUp/PgDn, Home/End: move   Enter: choose   Esc: back", "90"))
            self.clear()
            for text, color in lines:
                print(f"\x1b[{color}m{text[: max(1, width - 1)]}\x1b[0m")
            sys.stdout.flush()
            key = self.read_key()
            if key == "enter":
                return selected
            if key == "escape" or (quit_key and key.lower() == "q"):
                return -1
            if key in "123456789" and len(key) == 1 and int(key) <= len(labels):
                return int(key) - 1
            selected = move_selection(key, selected, len(labels), length)

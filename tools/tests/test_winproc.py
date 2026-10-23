# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import os
import subprocess
import sys

import pytest

from rtx_tools import winproc

pytestmark = pytest.mark.skipif(os.name != "nt", reason="opens Windows process handles")


def python(code: str) -> subprocess.Popen:
    return subprocess.Popen([sys.executable, "-c", code])


def test_follows_a_process_it_did_not_start_to_its_exit_code():
    child = python("raise SystemExit(3)")
    try:
        process = winproc.PidProcess(child.pid)
        assert process.pid == child.pid
        assert process.wait(timeout=30) == 3
        assert process.poll() == 3
    finally:
        child.wait()


def test_times_out_then_terminates_a_running_process():
    child = python("import time; time.sleep(60)")
    try:
        process = winproc.PidProcess(child.pid)
        assert process.poll() is None
        with pytest.raises(subprocess.TimeoutExpired):
            process.wait(timeout=0.05)
        process.terminate()
        assert process.wait(timeout=30) == 1
        # Ending a process that has already exited is not an error.
        process.kill()
    finally:
        child.kill()
        child.wait()


def test_short_path_names_the_same_directory(tmp_path):
    directory = tmp_path / "a directory with a long name"
    directory.mkdir()
    # The 8.3 form where the volume makes them, else the path unchanged.
    short = winproc.short_path(directory)
    assert short is not None and os.path.samefile(short, directory)
    assert winproc.short_path(tmp_path / "missing") is None


def test_a_process_that_cannot_be_opened_reports_an_unknown_exit_code():
    # No process has this ID: Windows hands out small multiples of four.
    process = winproc.PidProcess(0x7FFFFFFC)
    assert process.poll() == winproc.UNKNOWN_EXIT_CODE == -1
    assert process.wait(timeout=0) == winproc.UNKNOWN_EXIT_CODE
    process.terminate()

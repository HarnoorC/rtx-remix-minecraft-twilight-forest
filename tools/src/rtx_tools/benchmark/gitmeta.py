# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from . import util


def _git(*args: str, check: bool = True) -> str:
    result = util.run(["git", *args], capture=True, check=check)
    return (result.stdout or "").strip()


def branch_from_ci_env(env: Mapping[str, str], git_branch: str) -> tuple[str, str]:
    for key in (
        "CI_MERGE_REQUEST_SOURCE_BRANCH_NAME",
        "CI_COMMIT_BRANCH",
        "CI_COMMIT_REF_NAME",
    ):
        value = (env.get(key) or "").strip()
        if value and value != "HEAD":
            return value, key
    return git_branch, "git"


def ci_ref_metadata(env: Mapping[str, str], *, branch_source: str, checkout_branch: str) -> dict[str, str]:
    keys = [
        "CI_COMMIT_REF_NAME",
        "CI_COMMIT_REF_SLUG",
        "CI_COMMIT_BRANCH",
        "CI_COMMIT_TAG",
        "CI_MERGE_REQUEST_IID",
        "CI_MERGE_REQUEST_SOURCE_BRANCH_NAME",
        "CI_MERGE_REQUEST_TARGET_BRANCH_NAME",
        "CI_PIPELINE_SOURCE",
    ]
    data = {
        "branchSource": branch_source,
        "checkoutBranch": checkout_branch,
    }
    for key in keys:
        value = (env.get(key) or "").strip()
        if value:
            data[key] = value
    return data


def current_git() -> dict:
    checkout_branch = _git("rev-parse", "--abbrev-ref", "HEAD")
    branch, branch_source = branch_from_ci_env(os.environ, checkout_branch)
    commit = _git("rev-parse", "HEAD")
    commit_short = _git("rev-parse", "--short", "HEAD")
    title = _git("log", "-1", "--pretty=%s")
    status_text = _git("status", "--porcelain=v1", "--untracked-files=all")
    dirty_files = []
    for line in status_text.splitlines():
        if not line:
            continue
        dirty_files.append(
            {
                "status": line[:2],
                "path": line[3:] if len(line) > 3 else "",
            }
        )
    return {
        "branch": branch,
        "branchSource": branch_source,
        "checkoutBranch": checkout_branch,
        "commit": commit,
        "commitShort": commit_short,
        "commitTitle": title,
        "ci": ci_ref_metadata(os.environ, branch_source=branch_source, checkout_branch=checkout_branch),
        "dirty": bool(dirty_files),
        "dirtyFiles": dirty_files,
    }


def write_dirty_patch(path: Path) -> bool:
    result = util.run(
        ["git", "diff", "--binary", "HEAD"],
        capture=True,
        check=False,
        errors="replace",
    )
    text = result.stdout or ""
    if not text.strip():
        return False
    path.write_text(text, encoding="utf-8", errors="replace")
    return True

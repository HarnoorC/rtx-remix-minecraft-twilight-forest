# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import unittest

from rtx_tools.benchmark import gitmeta


class GitMetaTests(unittest.TestCase):
    def test_branch_from_ci_env_prefers_merge_request_source_branch(self):
        branch, source = gitmeta.branch_from_ci_env(
            {
                "CI_MERGE_REQUEST_SOURCE_BRANCH_NAME": "feature/benchmark-output",
                "CI_COMMIT_BRANCH": "",
                "CI_COMMIT_REF_NAME": "refs/merge-requests/42/head",
            },
            "HEAD",
        )

        self.assertEqual(branch, "feature/benchmark-output")
        self.assertEqual(source, "CI_MERGE_REQUEST_SOURCE_BRANCH_NAME")

    def test_branch_from_ci_env_uses_branch_pipeline_name(self):
        branch, source = gitmeta.branch_from_ci_env(
            {
                "CI_COMMIT_BRANCH": "main",
                "CI_COMMIT_REF_NAME": "main",
            },
            "HEAD",
        )

        self.assertEqual(branch, "main")
        self.assertEqual(source, "CI_COMMIT_BRANCH")

    def test_branch_from_ci_env_falls_back_to_git_branch(self):
        branch, source = gitmeta.branch_from_ci_env({}, "feature/local")

        self.assertEqual(branch, "feature/local")
        self.assertEqual(source, "git")


if __name__ == "__main__":
    unittest.main()

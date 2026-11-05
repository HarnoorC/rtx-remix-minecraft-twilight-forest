# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import json
import re
import unittest
from pathlib import Path

from rtx_tools.benchmark import util

REPO_ROOT = util.PROJECT_DIR


def gradle_mod_version() -> str:
    for line in (REPO_ROOT / "gradle.properties").read_text(encoding="utf-8").splitlines():
        if line.startswith("mod_version="):
            return line.split("=", 1)[1].strip()
    raise AssertionError("gradle.properties has no mod_version")


def gradle_dependency_version(group: str, artifact: str) -> str:
    text = (REPO_ROOT / "build.gradle").read_text(encoding="utf-8")
    match = re.search(rf'"{re.escape(group)}:{re.escape(artifact)}:([^\"]+)"', text)
    if not match:
        raise AssertionError(f"build.gradle has no {group}:{artifact} dependency")
    version = match.group(1)
    variable = re.fullmatch(r"\$\{(\w+)\}", version)
    if variable:
        version = gradle_literal(variable.group(1))
    return version


def gradle_literal(name: str) -> str:
    text = (REPO_ROOT / "build.gradle").read_text(encoding="utf-8")
    assignment = re.search(rf'\bdef\s+{re.escape(name)}\s*=\s*"([^"]+)"', text)
    if not assignment:
        raise AssertionError(f"build.gradle has no literal assignment for {name}")
    return assignment.group(1)


def powershell_literal(path: Path, variable: str) -> str:
    text = path.read_text(encoding="utf-8")
    match = re.search(rf"\${re.escape(variable)}\s*=\s*'([^']+)'", text)
    if not match:
        raise AssertionError(f"{path} has no ${variable} string assignment")
    return match.group(1)


class VersionConsistencyTests(unittest.TestCase):
    def test_fabric_test_loader_matches_runtime_loader(self):
        self.assertEqual(
            gradle_dependency_version("net.fabricmc", "fabric-loader"),
            gradle_dependency_version("net.fabricmc", "fabric-loader-junit"),
        )

    def test_twilight_forest_pins_match_between_gradle_and_installer(self):
        installer = REPO_ROOT / "packaging" / "installer.ps1"
        version = gradle_literal("twilightForestVersion")
        url = gradle_literal("twilightForestUrl")

        self.assertEqual(version, powershell_literal(installer, "script:TWILIGHT_FOREST_VERSION"))
        self.assertEqual(url, powershell_literal(installer, "script:TWILIGHT_FOREST_URL"))
        self.assertEqual(
            gradle_literal("twilightForestSha256"),
            powershell_literal(installer, "script:TWILIGHT_FOREST_SHA256"),
        )
        self.assertRegex(gradle_literal("twilightForestSha256"), r"^[0-9a-f]{64}$")
        jar = powershell_literal(installer, "script:TWILIGHT_FOREST_JAR")
        self.assertEqual(url.rsplit("/", 1)[1], jar)
        minecraft = gradle_dependency_version("com.mojang", "minecraft")
        self.assertEqual(f"twilightforest-fabric-{minecraft}-{version}.jar", jar)

    def test_packaging_version_defaults_match_gradle(self):
        expected = gradle_mod_version()
        self.assertEqual(
            expected,
            powershell_literal(REPO_ROOT / "packaging" / "installer.ps1", "script:APP_VERSION"),
        )

    def test_runtime_dependency_versions_match_gradle(self):
        expected = {
            "minecraft": gradle_dependency_version("com.mojang", "minecraft"),
            "fabric_loader": gradle_dependency_version("net.fabricmc", "fabric-loader"),
            "fabric_api": gradle_dependency_version("net.fabricmc.fabric-api", "fabric-api"),
        }
        installer = REPO_ROOT / "packaging" / "installer.ps1"

        for path, variables in (
            (
                installer,
                {
                    "minecraft": "script:MC_VERSION",
                    "fabric_loader": "script:FABRIC_LOADER_VER",
                    "fabric_api": "script:FABRIC_API_VERSION",
                },
            ),
        ):
            with self.subTest(path=path):
                for component, variable in variables.items():
                    self.assertEqual(expected[component], powershell_literal(path, variable))

    def test_runtime_code_does_not_hardcode_mod_version(self):
        benchmark_controller = (
            REPO_ROOT
            / "src"
            / "main"
            / "java"
            / "com"
            / "nvidia"
            / "rtxremix"
            / "minecraft"
            / "benchmark"
            / "BenchmarkController.java"
        ).read_text(encoding="utf-8")
        mod_entrypoint = (
            REPO_ROOT / "src" / "main" / "java" / "com" / "nvidia" / "rtxremix" / "minecraft" / "RtxRemixMod.java"
        ).read_text(encoding="utf-8")
        self.assertNotRegex(benchmark_controller, r'modVersion",\s*"\d+\.\d+\.\d+"')
        self.assertNotRegex(mod_entrypoint, r"Renderer v\d+\.\d+\.\d+")

    def test_fabric_metadata_matches_repository_contract(self):
        metadata = json.loads(
            (REPO_ROOT / "src" / "main" / "resources" / "fabric.mod.json").read_text(encoding="utf-8")
        )
        minecraft_version = gradle_dependency_version("com.mojang", "minecraft")
        fabric_loader_version = gradle_dependency_version("net.fabricmc", "fabric-loader")
        fabric_api_version = gradle_dependency_version("net.fabricmc.fabric-api", "fabric-api")

        self.assertEqual("Apache-2.0", metadata["license"])
        self.assertEqual(minecraft_version, metadata["depends"]["minecraft"])
        self.assertEqual(f">={fabric_loader_version}", metadata["depends"]["fabricloader"])
        self.assertEqual(f">={fabric_api_version}", metadata["depends"]["fabric-api"])
        self.assertNotIn("fabric-api", metadata.get("suggests", {}))
        self.assertEqual(f">={gradle_literal('twilightForestVersion')}", metadata["recommends"]["twilightforest"])

        icon = metadata.get("icon")
        if icon:
            self.assertTrue((REPO_ROOT / "src" / "main" / "resources" / icon).is_file())

        sources = metadata.get("contact", {}).get("sources", "")
        self.assertNotIn("rtxremix-java", sources)

    def test_readme_license_matches_repository_license(self):
        license_text = (REPO_ROOT / "LICENSE").read_text(encoding="utf-8")
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("Apache License", license_text)
        self.assertIn("Apache-2.0", readme)
        self.assertNotRegex(readme, r"(?m)^MIT\s+[\u2014-]\s+See LICENSE file$")


if __name__ == "__main__":
    unittest.main()

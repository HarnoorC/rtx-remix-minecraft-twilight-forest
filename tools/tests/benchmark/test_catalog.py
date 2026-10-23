# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import datetime as dt
import tempfile
import unittest
from pathlib import Path

from rtx_tools import cli
from rtx_tools.benchmark import catalog, util
from rtx_tools.cli import parse_age


class CatalogTests(unittest.TestCase):
    def test_catalog_uses_timestamp_order_for_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_run(root, "20260501_100000", avg_ms=20.0)
            self._write_run(root, "20260501_110000", avg_ms=10.0)

            doc = catalog.build_catalog(root)

            self.assertEqual(doc["defaultA"], "20260501_100000")
            self.assertEqual(doc["defaultB"], "20260501_110000")
            self.assertEqual(doc["runs"][1]["summary"]["avgFps"], 100.0)

    def test_failed_run_is_visible_but_not_selected_as_default_comparison(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_run(root, "20260501_100000", avg_ms=20.0)
            self._write_run(root, "20260501_110000", avg_ms=10.0)
            failed = root / "20260501_120000"
            self._write_run(root, failed.name, avg_ms=5.0)
            manifest = util.read_json(failed / "manifest.json")
            manifest["outcome"] = {"status": "failed"}
            util.write_json(failed / "manifest.json", manifest)

            doc = catalog.build_catalog(root)

        self.assertEqual(
            [run["id"] for run in doc["runs"]],
            [
                "20260501_100000",
                "20260501_110000",
                "20260501_120000",
            ],
        )
        self.assertEqual(doc["defaultA"], "20260501_100000")
        self.assertEqual(doc["defaultB"], "20260501_110000")

    def test_legacy_eligible_for_comparison_field_still_excludes_run(self):
        # Older manifests carry an explicit eligibleForComparison flag; the
        # current writer emits only status, but existing result dirs on the
        # runners must keep being honored.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_run(root, "20260501_100000", avg_ms=20.0)
            legacy = root / "20260501_110000"
            self._write_run(root, legacy.name, avg_ms=10.0)
            manifest = util.read_json(legacy / "manifest.json")
            manifest["outcome"] = {"status": "passed", "eligibleForComparison": False}
            util.write_json(legacy / "manifest.json", manifest)

            doc = catalog.build_catalog(root)

        self.assertEqual(doc["defaultB"], "20260501_100000")

    def test_write_dashboard_writes_static_entrypoints(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_run(root, "20260501_100000", avg_ms=16.0)

            catalog.write_dashboard(root)

            self.assertTrue((root / "index.html").exists())
            self.assertIn("window.BENCHMARK_CATALOG", (root / "catalog.js").read_text(encoding="utf-8"))

    def test_catalog_attaches_per_run_summaries_to_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_run(root, "20260501_100000", avg_ms=16.0)

            doc = catalog.build_catalog(root)
            artifact = doc["runs"][0]["artifacts"]["runs"][0]

            self.assertEqual(artifact["summary"]["run"], 1)
            self.assertEqual(artifact["summary"]["avgFps"], 50.0)
            self.assertEqual(artifact["summary"]["onePctLowFps"], 25.0)

    def test_summary_carries_tracy_run_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_run(
                root, "20260501_100000", avg_ms=16.0, tracy_valid=False, tracy_valid_runs=2, tracy_total_runs=3
            )

            doc = catalog.build_catalog(root)
            summary = doc["runs"][0]["summary"]

            self.assertFalse(summary["tracyValid"])
            self.assertEqual(summary["tracyValidRunCount"], 2)
            self.assertEqual(summary["tracyTotalRunCount"], 3)

    def test_summary_carries_excluded_run_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_run(root, "20260501_100000", avg_ms=16.0, excluded_run_count=1, runs_aggregated=2)

            doc = catalog.build_catalog(root)
            summary = doc["runs"][0]["summary"]

            self.assertEqual(summary["excludedRunCount"], 1)
            self.assertEqual(summary["runsAggregated"], 2)

    def test_summary_carries_scene_counters_and_the_widest_sections(self):
        sections = {f"S{i}": {"avgMs": float(i)} for i in range(20)}
        counters = {
            "Chunk.Sections": {"avg": 1200.0},
            "Chunk.RetainedPages": {"avg": 340.0},
            "Chunk.CaptureQueue": {"avg": 2.0},
            "Chunk.MissingSections": {"avg": 0.0},
            "Chunk.LightsDrawn": {"avg": 64.0},
            "Chunk.LightsBeyondReach": {"avg": 12.0},
            "Chunk.FloodIncrementalUs": {"avg": 8.0},
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_run(
                root, "20260501_100000", avg_ms=16.0, frame_extra={"sections": sections, "counters": counters}
            )

            summary = catalog.build_catalog(root)["runs"][0]["summary"]

        self.assertEqual(
            summary["scene"],
            {
                "sections": 1200.0,
                "drawnPages": 340.0,
                "captureQueue": 2.0,
                "missingSections": 0.0,
                "lightsDrawn": 64.0,
                "lightsBeyondReach": 12.0,
                "floodIncrementalUs": 8.0,
            },
        )
        self.assertEqual(list(summary["sections"]), [f"S{i}" for i in range(19, 3, -1)])

    def test_batch_mean_se_needs_two_blocks_and_uses_block_means(self):
        self.assertEqual(catalog._batch_mean_se([1.0] * 99, block=50), 0.0)

        samples = [12.8] * 50 + [13.2] * 50 + [12.8] * 50 + [13.2] * 50

        # Block means alternate 12.8 / 13.2 around 13.0: variance 0.16 / 3 over four blocks.
        self.assertAlmostEqual(catalog._batch_mean_se(samples, block=50), (0.16 / 3 / 4) ** 0.5, places=9)

    def test_frame_resolution_ignores_runs_the_aggregate_excluded(self):
        # A stall run stays in perRun for transparency but is left out of the
        # headline mean. Folding it into the between-run spread would widen the
        # band around a mean it never fed and hide a real regression behind it.
        doc = {
            "frame": {"avgMs": 13.1, "excludedRunCount": 1, "excludedRuns": [{"run": 2, "maxMs": 6000.0}]},
            "perRun": [
                {"meta": {"run": 1}, "frame": {"avgMs": 13.0}},
                {"meta": {"run": 2}, "frame": {"avgMs": 15.4, "maxMs": 6000.0}},
                {"meta": {"run": 3}, "frame": {"avgMs": 13.2}},
            ],
        }

        resolution = catalog.frame_resolution(doc)

        self.assertEqual(resolution["runs"], 2)
        self.assertEqual(resolution["basis"], "between-run")
        # Standard error of [13.0, 13.2] is 0.1 ms.
        self.assertEqual(resolution["ci95Pct"], round(100.0 * 1.96 * 0.1 / 13.1, 3))

    def test_frame_resolution_batch_means_use_the_surviving_run(self):
        healthy_frames = ([12_800_000] * 50 + [13_200_000] * 50) * 2
        doc = {
            "frame": {"avgMs": 13.0, "excludedRunCount": 1, "excludedRuns": [{"run": 1, "maxMs": 6000.0}]},
            "perRun": [
                {"meta": {"run": 1}, "frame": {"avgMs": 40.0, "maxMs": 6000.0}, "perFrame": [6_000_000_000] * 200},
                {"meta": {"run": 2}, "frame": {"avgMs": 13.0}, "perFrame": healthy_frames},
            ],
        }

        resolution = catalog.frame_resolution(doc)

        self.assertEqual(resolution["basis"], "batch-means")
        self.assertEqual(resolution["runs"], 1)
        self.assertTrue(resolution["lowerBound"])
        self.assertEqual(resolution["ci95Pct"], round(100.0 * 1.96 * (0.16 / 3 / 4) ** 0.5 / 13.0, 3))

    def test_frame_resolution_keeps_every_run_when_all_are_degenerate(self):
        doc = {
            "frame": {"avgMs": 20.0, "allRunsDegenerate": True, "excludedRuns": [{"run": 1}, {"run": 2}]},
            "perRun": [
                {"meta": {"run": 1}, "frame": {"avgMs": 19.0}},
                {"meta": {"run": 2}, "frame": {"avgMs": 21.0}},
            ],
        }

        self.assertEqual(catalog.frame_resolution(doc)["runs"], 2)

    def test_parse_age_units(self):
        self.assertEqual(parse_age("14d").days, 14)
        self.assertEqual(parse_age("2w").days, 14)
        self.assertEqual(parse_age("12h").seconds, 12 * 60 * 60)

    def test_prune_keep_without_age_keeps_newest_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_run(root, "20260501_100000", avg_ms=16.0)
            self._write_run(root, "20260501_110000", avg_ms=18.0)
            self._write_run(root, "20260501_120000", avg_ms=20.0)

            victims = cli._prune_victims(
                catalog.result_dirs(root),
                older_than=None,
                keep=1,
                now=dt.datetime(2026, 5, 1, 13, 0, tzinfo=dt.UTC),
            )

            self.assertEqual([path.name for path in victims], ["20260501_100000", "20260501_110000"])

    def test_prunable_result_dirs_include_legacy_timestamp_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_run(root, "20260501_100000", avg_ms=16.0)
            (root / "20260501_110000").mkdir()
            (root / "_scratch").mkdir()

            dirs = cli._prunable_result_dirs(root)

            self.assertEqual([path.name for path in dirs], ["20260501_100000", "20260501_110000"])

    def test_import_run_dir_merges_tags_and_renames_duplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "src"
            dst_root = root / "results"
            self._write_run(src, "20260501_100000", avg_ms=16.0)

            first = catalog.import_run_dir(src / "20260501_100000", dst_root, tags=["branch:main", "target"])
            second = catalog.import_run_dir(src / "20260501_100000", dst_root, tags=["comparison"])

            first_manifest = util.read_json(first / "manifest.json")
            second_manifest = util.read_json(second / "manifest.json")
            self.assertEqual(first_manifest["tags"], ["branch:main", "target"])
            self.assertEqual(second_manifest["id"], "20260501_100000_2")
            self.assertEqual(second_manifest["originalId"], "20260501_100000")
            self.assertEqual(second_manifest["tags"], ["comparison"])

    def test_delete_run_removes_local_result_and_refreshes_dashboard(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_run(root, "20260501_100000", avg_ms=16.0)
            self._write_run(root, "20260501_110000", avg_ms=18.0)

            deleted = catalog.delete_run("20260501_100", root)

            self.assertEqual(deleted, root / "20260501_100000")
            self.assertFalse((root / "20260501_100000").exists())
            self.assertTrue((root / "20260501_110000").exists())
            catalog_text = (root / "catalog.js").read_text(encoding="utf-8")
            self.assertNotIn("20260501_100000", catalog_text)
            self.assertIn("20260501_110000", catalog_text)

    def test_annotate_run_updates_manifest_and_dashboard(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_run(root, "20260501_100000", avg_ms=16.0)

            updated = catalog.annotate_run("20260501_100", root, note="local comparison", tags=["local", "compare"])

            self.assertEqual(updated, root / "20260501_100000")
            manifest = util.read_json(updated / "manifest.json")
            self.assertEqual(manifest["notes"], "local comparison")
            self.assertEqual(manifest["tags"], ["local", "compare"])
            catalog_text = (root / "catalog.js").read_text(encoding="utf-8")
            self.assertIn("local comparison", catalog_text)
            self.assertIn("compare", catalog_text)

    def _write_run(
        self,
        root: Path,
        run_id: str,
        avg_ms: float,
        *,
        tracy_valid: bool = True,
        tracy_valid_runs: int = 0,
        tracy_total_runs: int = 0,
        excluded_run_count: int = 0,
        runs_aggregated: int = 1,
        frame_extra: dict | None = None,
    ):
        run_dir = root / run_id
        run_dir.mkdir(parents=True)
        frame = {"avgMs": avg_ms, "p99Ms": avg_ms * 2.0, "cvPct": 1.0}
        if excluded_run_count:
            frame["excludedRunCount"] = excluded_run_count
            frame["runsAggregated"] = runs_aggregated
            frame["runsTotal"] = runs_aggregated + excluded_run_count
        if frame_extra:
            frame.update(frame_extra)
        util.write_json(
            run_dir / "manifest.json",
            {
                "id": run_id,
                "timestamp": {"utc": f"2026-05-01T{run_id[-6:-4]}:{run_id[-4:-2]}:{run_id[-2:]}+00:00"},
                "git": {"branch": "test", "commitShort": "abc1234"},
                "summary": {},
                "artifacts": {
                    "aggregate": "aggregate.json",
                    "runs": [{"run": 1, "tracy": "run_1/profile.tracy", "profileData": "run_1/profile-data.json"}],
                },
            },
        )
        util.write_json(
            run_dir / "aggregate.json",
            {
                "frame": frame,
                "tracy": {
                    "health": {
                        "valid": tracy_valid,
                        "validRunCount": tracy_valid_runs,
                        "totalRunCount": tracy_total_runs,
                    }
                },
                "jfr": {"valid": True},
                "perRun": [{"meta": {"run": 1}, "frame": {"avgMs": 20.0, "p99Ms": 40.0, "cvPct": 2.0}}],
            },
        )


if __name__ == "__main__":
    unittest.main()

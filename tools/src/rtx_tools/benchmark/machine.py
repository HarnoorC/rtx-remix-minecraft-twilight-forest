# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import datetime as dt
import getpass
import json
import locale
import os
import platform
import re
import socket
from collections.abc import Mapping
from typing import Any, cast

from . import gpu_telemetry, util

NVIDIA_VENDOR_ID = "VEN_10DE"
POWER_SCHEME_PATTERN = re.compile(r"Power Scheme GUID:\s*([0-9a-fA-F-]{36})\s*\((?P<name>[^)]*)\)")
DEFAULT_MIN_GPU_P0_SHARE_PCT = 90.0
DEFAULT_MAX_GPU_SLOWDOWN_SHARE_PCT = 5.0
GPU_QUERY_FIELDS = [
    "Name",
    "AdapterCompatibility",
    "DriverVersion",
    "AdapterRAM",
    "VideoProcessor",
    "PNPDeviceID",
    "Status",
    "CurrentHorizontalResolution",
    "CurrentVerticalResolution",
]


def _ps_json(command: str) -> Any:
    result = util.run(
        ["powershell", "-NoProfile", "-Command", command],
        capture=True,
        check=False,
        encoding=util.console_encoding(),
    )
    if result.returncode != 0 or not (result.stdout or "").strip():
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


def _java_version() -> str:
    result = util.run(["java", "-version"], capture=True, check=False, encoding=locale.getencoding(), errors="replace")
    text = ((result.stderr or "") + (result.stdout or "")).splitlines()
    return text[0] if text else ""


def _env(env: Mapping[str, str], key: str) -> str:
    return (env.get(key) or "").strip()


def _gitlab_url(project_url: str, kind: str, value: str) -> str:
    return f"{project_url}/-/{kind}/{value}" if project_url and value else ""


def _int_value(value: object) -> int:
    if value is None or value == "":
        return 0
    try:
        if isinstance(value, bool | int | float):
            return int(value)
        if isinstance(value, str):
            return int(value.strip() or 0)
    except TypeError, ValueError:
        return 0
    return 0


def _gpu_text(gpu: Mapping[str, Any]) -> str:
    return " ".join(
        str(gpu.get(key) or "") for key in ("Name", "AdapterCompatibility", "VideoProcessor", "PNPDeviceID")
    ).lower()


def _gpu_score(gpu: Mapping[str, Any]) -> tuple[int, list[str]]:
    text = _gpu_text(gpu)
    score = 0
    reasons = []
    if "nvidia" in text or NVIDIA_VENDOR_ID.lower() in text:
        score += 10000
        reasons.append("nvidia")
    if "microsoft basic" in text or "remote display" in text or "virtual" in text:
        score -= 5000
        reasons.append("virtual-or-basic")
    if str(gpu.get("Status") or "").lower() == "ok":
        score += 100
        reasons.append("status-ok")
    if _int_value(gpu.get("CurrentHorizontalResolution")) and _int_value(gpu.get("CurrentVerticalResolution")):
        score += 50
        reasons.append("active-display")
    ram_mib = _int_value(gpu.get("AdapterRAM")) // (1024 * 1024)
    if ram_mib:
        score += min(ram_mib, 8192) // 64
        reasons.append(f"adapter-ram-{ram_mib}MiB")
    return score, reasons


def select_gpu(gpus: list[Mapping[str, Any]]) -> dict:
    if not gpus:
        return {}
    candidates = []
    for index, gpu in enumerate(gpus):
        score, reasons = _gpu_score(gpu)
        candidates.append((score, -index, index, dict(gpu), reasons))
    score, _, index, selected, reasons = max(candidates)
    selected["selectionIndex"] = index
    selected["selectionScore"] = score
    selected["selectionReason"] = ", ".join(reasons) if reasons else "first-adapter"
    return selected


def benchmark_gpu_from_system(system: Mapping[str, Any], selected_gpu: Mapping[str, Any] | None = None) -> dict:
    name = str(system.get("gpu") or "").strip()
    if not name or name.lower() == "unknown":
        return {}
    selected_gpu = selected_gpu or {}
    gpu = dict(selected_gpu)
    gpu["Name"] = name
    gpu["AdapterCompatibility"] = str(system.get("gpuVendor") or gpu.get("AdapterCompatibility") or "").strip()
    gpu["GL_RENDERER"] = name
    if system.get("gpuVendor"):
        gpu["GL_VENDOR"] = system["gpuVendor"]
    if system.get("glVersion"):
        gpu["GL_VERSION"] = system["glVersion"]
    gpu["selectionReason"] = "benchmark GL_RENDERER"
    return gpu


def parse_power_scheme(text: str) -> dict:
    """Active plan name and GUID from `powercfg /getactivescheme` output."""
    match = POWER_SCHEME_PATTERN.search(text or "")
    if not match:
        return {}
    return {"activeScheme": match.group("name").strip(), "schemeGuid": match.group(1).lower()}


def collect_power_plan() -> dict:
    result = util.run(
        ["powercfg", "/getactivescheme"], capture=True, check=False, encoding=util.console_encoding(), errors="replace"
    )
    if result.returncode != 0:
        return {}
    return parse_power_scheme(result.stdout or "")


def uptime_seconds(last_boot_utc: str, now: dt.datetime | None = None) -> int | None:
    text = (last_boot_utc or "").strip()
    if not text:
        return None
    try:
        boot = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if boot.tzinfo is None:
        boot = boot.replace(tzinfo=dt.UTC)
    now = now or dt.datetime.now(dt.UTC)
    return max(0, int((now - boot).total_seconds()))


def runner_expectations(env: Mapping[str, str] = os.environ) -> dict:
    """Optional machine expectations supplied by the invoking environment."""
    spec = {}
    if power_plan := _env(env, "RTXREMIX_EXPECT_POWER_PLAN"):
        spec["powerPlan"] = power_plan
    if logical_processors := _env(env, "RTXREMIX_EXPECT_LOGICAL_PROCESSORS"):
        try:
            count = int(logical_processors)
            if count <= 0:
                raise ValueError
        except ValueError as exc:
            raise ValueError("RTXREMIX_EXPECT_LOGICAL_PROCESSORS must be a positive integer") from exc
        spec["logicalProcessors"] = count
    return spec


def _mapping(value: object) -> Mapping[str, Any]:
    return cast(Mapping[str, Any], value) if isinstance(value, Mapping) else {}


def off_spec_reasons(machine_info: Mapping[str, Any], spec: Mapping[str, Any] | None) -> list[str]:
    """Ways this box differs from the supplied expectations.

    Without expectations there are no checks, and a fact that was not collected
    (older manifests, no nvidia-smi) never counts against the box. The GPU
    rules only look at recording-phase samples: an idle card in P8 before the
    world loads is normal.
    """
    if not spec:
        return []
    reasons: list[str] = []
    power = _mapping(machine_info.get("power"))
    expected_plan = str(spec.get("powerPlan") or "").strip()
    actual_plan = str(power.get("activeScheme") or "").strip()
    accepted = {actual_plan.casefold(), str(power.get("schemeGuid") or "").casefold()}
    if expected_plan and actual_plan and expected_plan.casefold() not in accepted:
        reasons.append(f"power plan is {actual_plan}, expected {expected_plan}")
    expected_cpus = _int_value(spec.get("logicalProcessors"))
    actual_cpus = _int_value(machine_info.get("logicalCores"))
    if expected_cpus and actual_cpus and actual_cpus != expected_cpus:
        reasons.append(f"{actual_cpus} logical CPUs, expected {expected_cpus}")
    telemetry = _mapping(machine_info.get("gpuTelemetry"))
    if _int_value(telemetry.get("recordingSamples")) > 0:
        min_p0 = float(spec.get("minGpuP0SharePct", DEFAULT_MIN_GPU_P0_SHARE_PCT))
        p0_pct = float((telemetry.get("pstateShare") or {}).get("P0") or 0.0) * 100.0
        if p0_pct < min_p0:
            reasons.append(f"GPU spent {p0_pct:.0f}% of the recording in P0, expected at least {min_p0:.0f}%")
        max_slowdown = float(spec.get("maxGpuSlowdownSharePct", DEFAULT_MAX_GPU_SLOWDOWN_SHARE_PCT))
        shares = telemetry.get("eventReasonShare") or {}
        for name in gpu_telemetry.SLOWDOWN_REASONS:
            share_pct = float(shares.get(name) or 0.0) * 100.0
            if share_pct > max_slowdown:
                reasons.append(f"GPU reported {name} in {share_pct:.0f}% of recording samples")
    return reasons


def collect_ci(env: Mapping[str, str] = os.environ) -> dict:
    """Record manifest provenance without API access or private host assumptions.

    Derived GitLab links stay with this metadata so public dashboards retain
    navigable provenance. Artifact downloads and report posting live elsewhere.
    """
    project_url = _env(env, "CI_PROJECT_URL")
    pipeline_id = _env(env, "CI_PIPELINE_ID")
    job_id = _env(env, "CI_JOB_ID")
    mr_iid = _env(env, "CI_MERGE_REQUEST_IID")
    return {
        "isCi": bool(_env(env, "CI")),
        "serverUrl": _env(env, "CI_SERVER_URL"),
        "projectId": _env(env, "CI_PROJECT_ID"),
        "projectPath": _env(env, "CI_PROJECT_PATH"),
        "projectUrl": project_url,
        "pipelineId": pipeline_id,
        "pipelineIid": _env(env, "CI_PIPELINE_IID"),
        "pipelineSource": _env(env, "CI_PIPELINE_SOURCE"),
        "pipelineUrl": _env(env, "CI_PIPELINE_URL") or _gitlab_url(project_url, "pipelines", pipeline_id),
        "jobId": job_id,
        "jobName": _env(env, "CI_JOB_NAME"),
        "jobStage": _env(env, "CI_JOB_STAGE"),
        "jobUrl": _env(env, "CI_JOB_URL") or _gitlab_url(project_url, "jobs", job_id),
        "commitSha": _env(env, "CI_COMMIT_SHA"),
        "commitShortSha": _env(env, "CI_COMMIT_SHORT_SHA"),
        "commitRefName": _env(env, "CI_COMMIT_REF_NAME"),
        "commitRefSlug": _env(env, "CI_COMMIT_REF_SLUG"),
        "commitBranch": _env(env, "CI_COMMIT_BRANCH"),
        "commitTag": _env(env, "CI_COMMIT_TAG"),
        "mergeRequestId": _env(env, "CI_MERGE_REQUEST_ID"),
        "mergeRequestIid": mr_iid,
        "mergeRequestUrl": _gitlab_url(project_url, "merge_requests", mr_iid),
        "mergeRequestTitle": _env(env, "CI_MERGE_REQUEST_TITLE"),
        "mergeRequestSourceBranch": _env(env, "CI_MERGE_REQUEST_SOURCE_BRANCH_NAME"),
        "mergeRequestTargetBranch": _env(env, "CI_MERGE_REQUEST_TARGET_BRANCH_NAME"),
        "mergeRequestSourceProjectPath": _env(env, "CI_MERGE_REQUEST_SOURCE_PROJECT_PATH"),
        "mergeRequestTargetProjectPath": _env(env, "CI_MERGE_REQUEST_TARGET_PROJECT_PATH"),
        "runnerId": _env(env, "CI_RUNNER_ID"),
        "runnerDescription": _env(env, "CI_RUNNER_DESCRIPTION"),
        "runnerTags": _env(env, "CI_RUNNER_TAGS"),
    }


def collect_machine() -> dict:
    os_info = _ps_json(
        "Get-CimInstance Win32_OperatingSystem | "
        "Select-Object Caption,Version,BuildNumber,OSArchitecture,TotalVisibleMemorySize,"
        "@{n='LastBootUpTimeUtc';"
        "e={$_.LastBootUpTime.ToUniversalTime().ToString('yyyy-MM-dd\\THH:mm:ss') + '+00:00'}} | "
        "ConvertTo-Json -Compress"
    )
    last_boot = str(os_info.get("LastBootUpTimeUtc") or "") if isinstance(os_info, dict) else ""
    cpu_info = _ps_json(
        "Get-CimInstance Win32_Processor | Select-Object -First 1 "
        "Name,NumberOfCores,NumberOfLogicalProcessors | ConvertTo-Json -Compress"
    )
    gpu_info = _ps_json(
        f"Get-CimInstance Win32_VideoController | Select-Object {','.join(GPU_QUERY_FIELDS)} | ConvertTo-Json -Compress"
    )
    if isinstance(gpu_info, dict):
        gpus = [cast(Mapping[str, Any], gpu_info)]
    elif isinstance(gpu_info, list):
        gpus = [cast(Mapping[str, Any], item) for item in gpu_info if isinstance(item, dict)]
    else:
        gpus = []
    selected_gpu = select_gpu(gpus)

    ci = collect_ci()
    return {
        "hostname": socket.gethostname(),
        "user": getpass.getuser(),
        "platform": platform.platform(),
        "arch": platform.machine(),
        "processor": platform.processor(),
        "logicalCores": os.cpu_count(),
        "os": os_info,
        "uptimeSeconds": uptime_seconds(last_boot),
        "power": collect_power_plan(),
        "cpu": cpu_info,
        "gpus": gpus,
        "selectedGpu": selected_gpu,
        "java": {
            "version": _java_version(),
            "javaHome": os.environ.get("JAVA_HOME", ""),
        },
        "ci": ci,
    }

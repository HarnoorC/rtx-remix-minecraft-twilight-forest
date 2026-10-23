# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Shared JFR parsing utilities.

Uses the JDK ``jfr`` CLI tool to extract events as JSON, then provides
clean data structures for downstream analysis scripts.

This module is the foundation for every tool in the rtx_tools.profiler package.
Import it and use its helpers -- never shell out to ``jfr`` directly.
"""

import json
import locale
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# JFR tool discovery
# ---------------------------------------------------------------------------

_jfr_tool = None


def find_jfr_tool():
    """Locate the JDK ``jfr`` CLI executable."""
    global _jfr_tool
    if _jfr_tool:
        return _jfr_tool

    jfr = shutil.which("jfr")
    if jfr:
        _jfr_tool = jfr
        return jfr

    java_home = os.environ.get("JAVA_HOME")
    if java_home:
        candidate = os.path.join(java_home, "bin", "jfr.exe" if os.name == "nt" else "jfr")
        if os.path.isfile(candidate):
            _jfr_tool = candidate
            return candidate

    if os.name == "nt":
        for base in (Path("C:/Program Files/Java"), Path("C:/Program Files (x86)/Java")):
            if base.is_dir():
                for d in sorted(base.glob("jdk-*"), reverse=True):
                    candidate = d / "bin" / "jfr.exe"
                    if candidate.is_file():
                        _jfr_tool = str(candidate)
                        return str(candidate)

    raise FileNotFoundError("Could not find 'jfr' CLI tool. Set JAVA_HOME or add JDK bin/ to PATH.")


# ---------------------------------------------------------------------------
# Raw JFR tool wrappers
# ---------------------------------------------------------------------------


def jfr_summary_text(jfr_path):
    """Run ``jfr summary`` and return the raw text output."""
    tool = find_jfr_tool()
    r = subprocess.run(
        [tool, "summary", str(jfr_path)],
        capture_output=True,
        text=True,
        encoding=locale.getencoding(),
        errors="replace",
        timeout=30,
    )
    if r.returncode not in (0, -1):
        raise RuntimeError(f"jfr summary failed (rc={r.returncode}): {r.stderr}")
    return r.stdout + r.stderr


_event_cache: dict[tuple, list] = {}


def jfr_events(jfr_path, event_types=None):
    """
    Run ``jfr print --json`` and return the list of event dicts.

    Results are cached by (path, event_types) so repeated calls in the same
    process are free.

    Args:
        jfr_path: Path to the .jfr file.
        event_types: Optional list of event type strings to filter
                     (e.g. ``["jdk.ExecutionSample"]``).

    Returns:
        List of event dicts, each with ``type`` and ``values`` keys.
    """
    key = (str(jfr_path), tuple(sorted(event_types)) if event_types else ())
    if key in _event_cache:
        return _event_cache[key]

    tool = find_jfr_tool()
    cmd = [tool, "print", "--json"]
    if event_types:
        cmd.extend(["--events", ",".join(event_types)])
    cmd.append(str(jfr_path))

    print(f"  [jfr] loading {', '.join(event_types) if event_types else 'all events'}...", file=sys.stderr)
    r = subprocess.run(cmd, capture_output=True, timeout=300)
    if r.returncode not in (0, -1):
        stderr = r.stderr.decode(locale.getencoding(), errors="replace").replace("\r\n", "\n").replace("\r", "\n")
        raise RuntimeError(f"jfr print failed (rc={r.returncode}): {stderr}")

    data = json.loads(r.stdout.decode("utf-8"))
    events = data.get("recording", {}).get("events", [])
    _event_cache[key] = events
    return events


# ---------------------------------------------------------------------------
# Event accessors
# ---------------------------------------------------------------------------


def thread_name(event):
    """Extract the Java thread name from an event."""
    vals = event.get("values", {})
    for key in ("sampledThread", "eventThread"):
        t = vals.get(key)
        if isinstance(t, dict):
            return t.get("javaName") or t.get("osName") or "unknown"
    return "unknown"


def thread_id(event):
    """Extract the OS thread id from an event."""
    vals = event.get("values", {})
    for key in ("sampledThread", "eventThread"):
        t = vals.get(key)
        if isinstance(t, dict):
            return t.get("osThreadId", 0)
    return 0


def event_timestamp_ms(event):
    """Extract event startTime as epoch milliseconds."""
    ts = event.get("values", {}).get("startTime", "")
    return parse_timestamp(ts)


def event_duration_ms(event):
    """Extract event duration in milliseconds (0 for instant events)."""
    d = event.get("values", {}).get("duration")
    if d is None:
        return 0.0
    return parse_iso_duration(d)


def stack_frames(event, simple=True):
    """
    Extract stack frames as a list of readable strings (top-of-stack first).

    Args:
        event: An event dict from ``jfr_events()``.
        simple: If True, use short class names. If False, use fully qualified.

    Returns:
        List of strings like ``"RemixRenderer.onFrameEnd:392"``.
    """
    st = event.get("values", {}).get("stackTrace")
    if not st:
        return []
    return [frame_str(f, simple=simple) for f in st.get("frames", [])]


def stack_frames_raw(event):
    """Return the raw frame dicts from an event's stack trace."""
    st = event.get("values", {}).get("stackTrace")
    if not st:
        return []
    return st.get("frames", [])


# ---------------------------------------------------------------------------
# Frame formatting
# ---------------------------------------------------------------------------

_LAMBDA_RE = re.compile(r"\$\$Lambda[+/].*")
_INNER_ANON_RE = re.compile(r"\$\d+$")


def _resolve_type_name(raw_type):
    """Extract the class name string from a JFR method type field."""
    if isinstance(raw_type, dict):
        return raw_type.get("name", "?")
    if isinstance(raw_type, str):
        return raw_type
    return "?"


def _normalize_type(name, simple):
    """Normalize a JFR class name (uses ``/`` separators) to a readable form."""
    name = name.replace("/", ".")
    name = _LAMBDA_RE.sub("$$Lambda", name)
    if simple:
        name = name.rsplit(".", 1)[-1]
        parts = name.split("$")
        if len(parts) > 2:
            name = "$".join(parts[:2])
    return name


def frame_str(frame, simple=True):
    """Format a stack frame dict as ``Class.method:line``."""
    method = frame.get("method", {})
    type_name = _normalize_type(_resolve_type_name(method.get("type", "?")), simple)
    method_name = method.get("name", "?")
    line = frame.get("lineNumber", -1)

    s = f"{type_name}.{method_name}"
    if line > 0:
        s += f":{line}"
    return s


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def parse_iso_duration(s):
    """Parse an ISO 8601 duration string to milliseconds.

    Examples: ``'PT1.234S'`` -> ``1234.0``, ``'PT0.000015600S'`` -> ``0.0156``
    """
    if not s or not isinstance(s, str):
        return 0.0
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:([\d.]+)S)?", s)
    if not m:
        return 0.0
    h = int(m.group(1) or 0)
    mn = int(m.group(2) or 0)
    sec = float(m.group(3) or 0)
    return (h * 3600 + mn * 60 + sec) * 1000.0


def parse_timestamp(ts):
    """Parse a JFR ISO-8601 timestamp to epoch milliseconds."""
    if not ts or not isinstance(ts, str):
        return 0.0
    clean = re.sub(r"(\.\d{6})\d*", r"\1", ts)
    clean = clean.replace("+00:00", "+0000").replace("Z", "+0000")
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            dt = datetime.strptime(clean, fmt)
            return dt.timestamp() * 1000.0
        except ValueError:
            continue
    return 0.0


def parse_summary_events(summary_text):
    """
    Parse the ``jfr summary`` text output to extract event type counts.

    Returns:
        List of ``(event_type, count, size_bytes)`` tuples, sorted by count desc.
    """
    results = []
    in_events = False
    for line in summary_text.splitlines():
        if "Event Type" in line and "Count" in line:
            in_events = True
            continue
        if in_events and line.strip().startswith("="):
            continue
        if in_events and line.strip():
            parts = line.rsplit(None, 2)
            if len(parts) >= 3:
                try:
                    name = parts[0].strip()
                    count = int(parts[1].strip())
                    size = int(parts[2].strip())
                    results.append((name, count, size))
                except ValueError, IndexError:
                    continue
    results.sort(key=lambda x: x[1], reverse=True)
    return results


def parse_summary_meta(summary_text):
    """Extract recording metadata from ``jfr summary`` text."""
    meta = {}
    for line in summary_text.splitlines():
        if ":" in line:
            key, _, val = line.strip().partition(":")
            key = key.strip().lower()
            val = val.strip()
            if key in ("version", "chunks", "start", "duration"):
                meta[key] = val
    return meta


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def fmt_count(n):
    """Format a number with thousands separators."""
    return f"{n:,}"


def fmt_pct(value, total):
    """Format as a percentage string."""
    if total == 0:
        return "  0.0%"
    return f"{value / total * 100:5.1f}%"


def fmt_bytes(n):
    """Format byte count as human-readable."""
    for unit in ("B", "KB", "MB", "GB"):
        if abs(n) < 1024:
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024
    return f"{n:.1f} TB"


def fmt_ms(ms):
    """Format milliseconds as human-readable. None means the figure does not apply."""
    if ms is None:
        return "n/a"
    if ms < 0.01:
        return f"{ms * 1000:.1f}us"
    if ms < 1:
        return f"{ms * 1000:.0f}us"
    if ms < 1000:
        return f"{ms:.1f}ms"
    if ms < 60_000:
        return f"{ms / 1000:.2f}s"
    return f"{ms / 60_000:.1f}min"


def _delta_markers():
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        "▲▼".encode(encoding)
        return "▲", "▼"
    except UnicodeEncodeError:
        return "^", "v"
    except LookupError:
        return "^", "v"


def fmt_delta(before, after):
    """Format a before/after comparison as a delta string.

    Returns strings like ``"+12.3%"``, ``"-45.6%"``, or ``"  0.0%"``
    with directional arrows for quick scanning.
    """
    if before == 0:
        if after == 0:
            return "     0%"
        return "   +inf"
    pct = (after - before) / before * 100
    up, down = _delta_markers()
    if pct > 0:
        return f"+{pct:5.1f}% {up}"
    if pct < 0:
        return f"{pct:5.1f}% {down}"
    return "  0.0%  "


def get_sampling_period_ms(jfr_path):
    """
    Determine the ExecutionSample sampling period from ActiveSetting events.

    Falls back to 10ms default.
    """
    try:
        settings = jfr_events(jfr_path, ["jdk.ActiveSetting"])
        for ev in settings:
            vals = ev.get("values", {})
            name = vals.get("name", "")
            setting_for = vals.get("settingFor")
            if name == "period" and setting_for:
                ev_name = ""
                if isinstance(setting_for, dict):
                    ev_name = setting_for.get("type", "")
                elif isinstance(setting_for, str):
                    ev_name = setting_for
                if "ExecutionSample" in ev_name:
                    val = vals.get("value", "")
                    m = re.match(r"(\d+)\s*(ms|s|us|ns)", val)
                    if m:
                        num = float(m.group(1))
                        unit = m.group(2)
                        multipliers = {"ns": 0.000001, "us": 0.001, "ms": 1.0, "s": 1000.0}
                        return num * multipliers.get(unit, 1.0)
    except Exception:
        pass
    return 10.0


# ---------------------------------------------------------------------------
# Thread filtering
# ---------------------------------------------------------------------------


def compile_thread_filter(pattern):
    """Compile a thread name filter pattern into a regex."""
    if not pattern:
        return None
    return re.compile(pattern, re.IGNORECASE)


def matches_thread(event, thread_re):
    """Check if an event's thread matches the filter regex."""
    if thread_re is None:
        return True
    name = thread_name(event)
    return thread_re.search(name) is not None


# ---------------------------------------------------------------------------
# Time-window filtering
# ---------------------------------------------------------------------------


def parse_time_arg(time_str, reference_events=None):
    """Parse a ``--after`` / ``--before`` time argument to epoch milliseconds.

    Accepted formats:
        ``HH:MM``          -- clock time (date inferred from first event)
        ``HH:MM:SS``       -- clock time with seconds
        ``HH:MM:SS.fff``   -- clock time with sub-second
        Full ISO-8601      -- used directly

    Args:
        time_str: The user-supplied time string.
        reference_events: Event list used to infer the recording date when
            only a clock time is supplied.

    Returns:
        Epoch milliseconds, or ``None`` if parsing fails.
    """
    if not time_str:
        return None

    if "T" in time_str:
        ms = parse_timestamp(time_str)
        return ms if ms > 0 else None

    ref_dt = None
    if reference_events:
        for ev in reference_events:
            ts = event_timestamp_ms(ev)
            if ts > 0:
                ref_dt = datetime.fromtimestamp(ts / 1000.0).astimezone()
                break

    parts = time_str.replace(".", ":").split(":")
    try:
        h = int(parts[0])
        m = int(parts[1]) if len(parts) > 1 else 0
        s = int(parts[2]) if len(parts) > 2 else 0
        us = int(parts[3]) * 1000 if len(parts) > 3 else 0
    except ValueError, IndexError:
        return None

    if ref_dt:
        dt = ref_dt.replace(hour=h, minute=m, second=s, microsecond=us)
    else:
        dt = datetime.now().replace(hour=h, minute=m, second=s, microsecond=us)
        dt = dt.astimezone()

    return dt.timestamp() * 1000.0


def filter_by_time(events, after_ms=None, before_ms=None):
    """Filter events to those within [after_ms, before_ms]."""
    if after_ms is None and before_ms is None:
        return events
    result = []
    for ev in events:
        ts = event_timestamp_ms(ev)
        if ts <= 0:
            continue
        if after_ms and ts < after_ms:
            continue
        if before_ms and ts > before_ms:
            continue
        result.append(ev)
    return result


# ---------------------------------------------------------------------------
# JSON output helper
# ---------------------------------------------------------------------------


def json_output(data, file=None):
    """Write *data* as pretty-printed JSON to *file* (default: stdout)."""
    json.dump(data, file or sys.stdout, indent=2, default=str)
    print(file=file or sys.stdout)


# ---------------------------------------------------------------------------
# Common argparse setup
# ---------------------------------------------------------------------------


def add_common_args(parser):
    """Add the standard set of flags shared across all tools."""
    parser.add_argument("jfr_file", help="Path to the .jfr recording file")
    parser.add_argument(
        "--thread",
        "-t",
        default=None,
        help="Filter threads by regex pattern (e.g. 'main', 'Worker-Main-\\d+')",
    )
    parser.add_argument(
        "--fqn",
        action="store_true",
        help="Use fully qualified class names instead of simple names",
    )
    parser.add_argument(
        "--top",
        "-n",
        type=int,
        default=30,
        help="Number of top entries to show (default: 30)",
    )
    parser.add_argument(
        "--after",
        default=None,
        help="Only include events after this time (HH:MM, HH:MM:SS, or ISO-8601)",
    )
    parser.add_argument(
        "--before",
        default=None,
        help="Only include events before this time (HH:MM, HH:MM:SS, or ISO-8601)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON for machine parsing",
    )


def apply_common_filters(events, args):
    """Apply thread and time-window filters from common args.

    Returns:
        Filtered event list.
    """
    thread_re = compile_thread_filter(getattr(args, "thread", None))
    events = [ev for ev in events if matches_thread(ev, thread_re)]

    after_ms = parse_time_arg(getattr(args, "after", None), reference_events=events)
    before_ms = parse_time_arg(getattr(args, "before", None), reference_events=events)
    events = filter_by_time(events, after_ms, before_ms)

    return events


def print_header(title):
    """Print a section header bar."""
    width = min(len(title), 100)
    print(f"\n{'=' * width}")
    print(title)
    print("=" * width)

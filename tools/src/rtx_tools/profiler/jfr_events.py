#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
JFR Raw Event Explorer -- list event types, dump events, filter freely.

The Swiss army knife when no specialized tool covers your question.
List what event types exist, dump a specific type as structured text
or JSON, and filter by time, thread, or field values.

Usage:
    python -m rtx_tools.profiler.jfr_events profile.jfr --list-types
    python -m rtx_tools.profiler.jfr_events profile.jfr --type jdk.GCHeapSummary
    python -m rtx_tools.profiler.jfr_events profile.jfr --type jdk.GCHeapSummary --json
    python -m rtx_tools.profiler.jfr_events profile.jfr --type jdk.ExecutionSample -t "^main$" -n 10
"""

import argparse
import sys

from .jfr_parse import (
    compile_thread_filter,
    event_duration_ms,
    event_timestamp_ms,
    filter_by_time,
    fmt_bytes,
    fmt_count,
    fmt_ms,
    jfr_events,
    jfr_summary_text,
    json_output,
    matches_thread,
    parse_summary_events,
    parse_time_arg,
    print_header,
    thread_name,
)


def list_types(jfr):
    summary = jfr_summary_text(jfr)
    events_list = parse_summary_events(summary)
    total = sum(c for _, c, _ in events_list)

    print_header(f"Event Types ({len(events_list)} types, {fmt_count(total)} events)")
    nw = max((len(n) for n, _, _ in events_list), default=30)
    print(f"\n  {'Event Type':<{nw}}  {'Count':>10}  {'Size':>10}")
    print(f"  {'':-<{nw}}  {'':->10}  {'':->10}")
    for name, count, size in events_list:
        print(f"  {name:<{nw}}  {fmt_count(count):>10}  {fmt_bytes(size):>10}")
    print()


def dump_events(jfr, event_type, args):
    events = jfr_events(jfr, [event_type])

    thread_re = compile_thread_filter(args.thread)
    events = [ev for ev in events if matches_thread(ev, thread_re)]

    after_ms = parse_time_arg(args.after, reference_events=events)
    before_ms = parse_time_arg(args.before, reference_events=events)
    events = filter_by_time(events, after_ms, before_ms)

    if args.field_filter:
        key, _, val = args.field_filter.partition("=")
        events = [ev for ev in events if str(ev.get("values", {}).get(key, "")).lower() == val.lower()]

    top_n = args.top or len(events)
    events = events[:top_n]

    if not events:
        print(f"No events of type '{event_type}' match filters.", file=sys.stderr)
        sys.exit(1)

    if args.json:
        json_output([ev.get("values", {}) for ev in events])
        return

    print_header(f"{event_type} ({len(events)} events shown)")
    for i, ev in enumerate(events):
        vals = ev.get("values", {})
        ts = event_timestamp_ms(ev)
        dur = event_duration_ms(ev)
        tn = thread_name(ev)

        ts_str = f"  [{i + 1}] " + (f"@{fmt_ms(ts % 86400000)} " if ts else "")
        if dur:
            ts_str += f"dur={fmt_ms(dur)} "
        ts_str += f"thread={tn}"
        print(ts_str)

        for k, v in vals.items():
            if k in ("startTime", "duration", "sampledThread", "eventThread", "stackTrace"):
                continue
            if isinstance(v, dict):
                v = v.get("name", v.get("type", str(v)))
            print(f"    {k}: {v}")
        print()


def run(args):
    if args.list_types:
        list_types(args.jfr_file)
        return

    if not args.type:
        print("Specify --list-types to see available types, or --type <name> to dump events.", file=sys.stderr)
        sys.exit(2)

    dump_events(args.jfr_file, args.type, args)


def main():
    parser = argparse.ArgumentParser(
        description="Raw JFR event explorer.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  python -m rtx_tools.profiler.jfr_events profile.jfr --list-types
  python -m rtx_tools.profiler.jfr_events profile.jfr --type jdk.GCHeapSummary
  python -m rtx_tools.profiler.jfr_events profile.jfr --type jdk.GCHeapSummary --json
  python -m rtx_tools.profiler.jfr_events profile.jfr --type jdk.ThreadCPULoad -t "^main$" -n 5
  python -m rtx_tools.profiler.jfr_events profile.jfr --type jdk.FileRead --field path=/tmp/foo""",
    )
    parser.add_argument("jfr_file", help="Path to the .jfr recording file")
    parser.add_argument("--list-types", action="store_true", help="List all event types with counts")
    parser.add_argument("--type", default=None, help="Event type to dump (e.g. jdk.GCHeapSummary)")
    parser.add_argument("--thread", "-t", default=None, help="Filter threads by regex")
    parser.add_argument(
        "--field", dest="field_filter", default=None, help="Filter by field value (e.g. 'cause=System.gc()')"
    )
    parser.add_argument("--top", "-n", type=int, default=None, help="Limit number of events shown")
    parser.add_argument("--after", default=None, help="Only events after this time")
    parser.add_argument("--before", default=None, help="Only events before this time")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    run(parser.parse_args())


if __name__ == "__main__":
    main()

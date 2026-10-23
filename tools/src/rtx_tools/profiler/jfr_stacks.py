#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
JFR Stack Trace Analysis -- call trees, collapsed stacks, bottom-up views.

Three output formats:
  tree       Merged call tree with sample counts (top-down, from root)
  collapsed  Folded stacks compatible with flamegraph tools
  bottom-up  Reversed aggregation starting from the hottest leaf methods

Usage:
    python -m rtx_tools.profiler.jfr_stacks profile.jfr -t "^main$"
    python -m rtx_tools.profiler.jfr_stacks profile.jfr -t "^main$" --format collapsed
    python -m rtx_tools.profiler.jfr_stacks profile.jfr -t "Worker" --format bottom-up --depth 5
    python -m rtx_tools.profiler.jfr_stacks profile.jfr --after 15:30 --before 15:35
"""

import argparse
import sys
from collections import defaultdict

from .jfr_parse import (
    apply_common_filters,
    fmt_count,
    fmt_ms,
    fmt_pct,
    get_sampling_period_ms,
    jfr_events,
    print_header,
    stack_frames,
    thread_name,
)

# ---------------------------------------------------------------------------
# Call tree (top-down, merged)
# ---------------------------------------------------------------------------


class TreeNode:
    __slots__ = ("name", "self_count", "total_count", "children")

    def __init__(self, name):
        self.name = name
        self.self_count = 0
        self.total_count = 0
        self.children = {}

    def add_stack(self, frames):
        self.total_count += 1
        if not frames:
            self.self_count += 1
            return
        child_name = frames[0]
        child = self.children.get(child_name)
        if child is None:
            child = TreeNode(child_name)
            self.children[child_name] = child
        child.add_stack(frames[1:])

    def print_tree(self, total_root, period_ms, depth_limit, min_pct, indent=0, prefix=""):
        pct = self.total_count / total_root * 100 if total_root else 0
        if pct < min_pct and indent > 0:
            return
        est = fmt_ms(self.total_count * period_ms)
        self_marker = ""
        if self.self_count > 0 and self.self_count == self.total_count:
            self_marker = "  [SELF]"
        elif self.self_count > 0:
            self_marker = f"  [+{self.self_count} self]"

        if indent == 0:
            label = f"[root: {fmt_count(self.total_count)} samples, ~{est}]"
        else:
            label = f"{prefix}{pct:5.1f}% [{fmt_count(self.total_count):>6}] ~{est:>8}  {self.name}{self_marker}"
        print(label)

        if depth_limit is not None and indent >= depth_limit:
            if self.children:
                deeper = sum(c.total_count for c in self.children.values())
                print(
                    f"{prefix}  ... {len(self.children)} children ({fmt_count(deeper)} samples, use --depth to expand)"
                )
            return

        for child in sorted(self.children.values(), key=lambda c: c.total_count, reverse=True):
            child.print_tree(total_root, period_ms, depth_limit, min_pct, indent=indent + 1, prefix=prefix + "  ")


def print_call_tree(events, simple, period_ms, depth_limit, min_pct):
    root = TreeNode("<root>")
    for ev in events:
        frames = stack_frames(ev, simple=simple)
        frames.reverse()
        root.add_stack(frames)
    root.print_tree(root.total_count, period_ms, depth_limit, min_pct)


# ---------------------------------------------------------------------------
# Collapsed stacks (flamegraph-compatible)
# ---------------------------------------------------------------------------


def print_collapsed(events, simple, include_thread):
    stacks = defaultdict(int)
    for ev in events:
        frames = stack_frames(ev, simple=simple)
        frames.reverse()
        key_parts = []
        if include_thread:
            key_parts.append(thread_name(ev))
        key_parts.extend(frames)
        stacks[";".join(key_parts)] += 1

    for stack, count in sorted(stacks.items(), key=lambda x: x[1], reverse=True):
        print(f"{stack} {count}")


# ---------------------------------------------------------------------------
# Bottom-up
# ---------------------------------------------------------------------------


def print_bottom_up(events, simple, period_ms, top_n, depth_limit):
    leaf_counts = defaultdict(int)
    leaf_callers = defaultdict(lambda: defaultdict(int))

    for ev in events:
        frames = stack_frames(ev, simple=simple)
        if not frames:
            continue
        leaf = frames[0]
        leaf_counts[leaf] += 1
        callers = frames[1 : depth_limit + 1] if depth_limit else frames[1:]
        for i, caller in enumerate(callers):
            leaf_callers[leaf][(i, caller)] += 1

    total = sum(leaf_counts.values())
    sorted_leaves = sorted(leaf_counts.items(), key=lambda x: x[1], reverse=True)

    for rank, (leaf, count) in enumerate(sorted_leaves[:top_n], 1):
        est = fmt_ms(count * period_ms)
        print(f"\n  #{rank}  {leaf}  [{fmt_count(count)} samples, {fmt_pct(count, total)}, ~{est}]")
        callers = leaf_callers[leaf]
        if callers:
            by_depth = defaultdict(lambda: defaultdict(int))
            for (depth, caller), cnt in callers.items():
                by_depth[depth][caller] += cnt
            for d in sorted(by_depth.keys()):
                for caller, cnt in sorted(by_depth[d].items(), key=lambda x: x[1], reverse=True):
                    pct_of_leaf = cnt / count * 100
                    indent = "    " + "  " * d
                    print(f"{indent}<- {caller}  [{fmt_count(cnt)}, {pct_of_leaf:.0f}%]")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def run(args):
    jfr = args.jfr_file
    simple = not args.fqn

    event_types = ["jdk.ExecutionSample", "jdk.NativeMethodSample"]
    events = jfr_events(jfr, event_types)
    events = apply_common_filters(events, args)

    if args.filter:
        events = [ev for ev in events if any(args.filter.lower() in f.lower() for f in stack_frames(ev, simple=simple))]

    thread_label = args.thread or "all threads"
    total = len(events)
    period = get_sampling_period_ms(jfr)

    if total == 0:
        print(
            f"No samples found for thread '{thread_label}'" + (f" with filter '{args.filter}'" if args.filter else ""),
            file=sys.stderr,
        )
        sys.exit(1)

    header = f"Stacks [{args.format}] | {thread_label} | {fmt_count(total)} samples | ~{fmt_ms(period)} period"
    if args.filter:
        header += f" | filter: '{args.filter}'"

    if args.format == "collapsed":
        print(f"# {header}")
        print_collapsed(events, simple, include_thread=(args.thread is None))
    elif args.format == "bottom-up":
        print_header(header)
        print_bottom_up(events, simple, period, args.top, args.depth)
        print()
    else:
        print_header(header)
        print_call_tree(events, simple, period, args.depth, args.min_pct)
        print()


def main():
    parser = argparse.ArgumentParser(
        description="Stack trace analysis from JFR recordings.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Formats:
  tree       Merged top-down call tree with sample counts (default)
  collapsed  Folded stacks, one line per unique stack (flamegraph input)
  bottom-up  Starts from hottest leaf methods, showing callers

Examples:
  python -m rtx_tools.profiler.jfr_stacks profile.jfr -t "^main$"
  python -m rtx_tools.profiler.jfr_stacks profile.jfr --format bottom-up --depth 5
  python -m rtx_tools.profiler.jfr_stacks profile.jfr --format collapsed > stacks.folded""",
    )
    parser.add_argument("jfr_file", help="Path to the .jfr recording file")
    parser.add_argument("--thread", "-t", default=None, help="Filter threads by regex")
    parser.add_argument(
        "--format",
        "-f",
        choices=["tree", "collapsed", "bottom-up"],
        default="tree",
        help="Output format (default: tree)",
    )
    parser.add_argument("--filter", default=None, help="Only show stacks containing this substring")
    parser.add_argument("--depth", "-d", type=int, default=None, help="Maximum tree/caller depth")
    parser.add_argument("--min-pct", type=float, default=0.5, help="Hide tree nodes below this %% (default: 0.5)")
    parser.add_argument("--fqn", action="store_true", help="Fully qualified class names")
    parser.add_argument("--top", "-n", type=int, default=20, help="Top N for bottom-up (default: 20)")
    parser.add_argument("--after", default=None, help="Only events after this time")
    parser.add_argument("--before", default=None, help="Only events before this time")
    parser.add_argument("--json", action="store_true", help="(collapsed format only) no effect on tree")
    run(parser.parse_args())


if __name__ == "__main__":
    main()

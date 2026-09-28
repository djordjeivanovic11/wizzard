#!/usr/bin/env python3
"""madsLoop — a minimal coding-agent harness.

Usage:
    python madsLoop.py -p "<problem statement>" [--log] <workdir>

The agent runs a model-in-a-loop: it proposes tool calls, this harness
executes them inside <workdir>, and feeds the results back. When the agent
is done, its fix exists as unstaged changes in <workdir>.

--log writes a run trace to ./madsLoop_logs/ in the *current working
directory* as JSONL (one event per line; see docs/schema in the assignment).
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.agent import run_agent  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(prog="madsLoop")
    ap.add_argument("-p", "--problem", required=True,
                    help="problem statement / issue text for the agent")
    ap.add_argument("--log", action="store_true",
                    help="write the run trace to ./madsLoop_logs/")
    ap.add_argument("workdir", help="path to the repo checkout the agent works on")
    args = ap.parse_args()

    workdir = os.path.abspath(args.workdir)
    if not os.path.isdir(workdir):
        print(f"madsLoop: workdir {workdir} does not exist", file=sys.stderr)
        return 2
    if not os.environ.get("CS2680_API_KEY"):
        print("madsLoop: CS2680_API_KEY is not set", file=sys.stderr)
        return 2

    return run_agent(problem=args.problem, workdir=workdir, log=args.log)


if __name__ == "__main__":
    sys.exit(main())

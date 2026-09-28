#!/bin/bash
# docker_env.sh — container setup, runs inside the task container before
# madsLoop.py. The harness needs Python 3.10+ (run_task.sh selects the
# interpreter) and the `openai` package; run_task.sh also ensures openai on
# the selected interpreter, so this is intentionally minimal.
pip install -q "openai>=1.0" 2>/dev/null || pip3 install -q "openai>=1.0" || true

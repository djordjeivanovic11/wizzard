# madsLoop — a minimal coding-agent harness

`madsLoop` is a tool-use agent loop for SWE-bench-style tasks: the model
(`qwen3.6-35b-a3b` via the course proxy) proposes tool calls, the harness
executes them inside the task repo, and results are fed back until the model
calls `done`.

## Layout

```
madsLoop.py            # CLI entry point: -p "<problem>" [--log] <workdir>
docker_env.sh          # container setup (installs openai)
src/
  agent.py             # the loop: retries, nudges, done-pushback, context masking
  tools.py             # tool schemas + executors (bash/read/edit/write/repro/done)
  prompts.py           # system + initial-user prompts
  logs.py              # JSONL event logger -> ./madsLoop_logs/run_*.jsonl
evaluation_scripts/    # provided harness (run_task.sh lightly modified)
mytest/                # four self-built tasks (see 2.6)
```

## What it does differently from the handout

- **Full task text**: `run_task.sh` feeds the agent `problem_statement` plus
  the `requirements` and `interface` fields, not just the problem statement.
- **`repro_check` tool**: registers a reproduction command, runs it in /tmp,
  and re-runs every registered check when the model calls `done` — a check
  that still fails blocks finishing (bounded, max 2 pushbacks total).
- **done-pushback**: `done` with an empty `git status` is rejected and the
  agent is asked to either make the fix or confirm the task is impossible.
- **No-tool-call nudges**: a reply with no tool calls gets up to two
  "act through tools" nudges before the run ends as `no_tool_calls` —
  qwen3.6-35b-a3b often writes a long analysis paragraph mid-run.
- **Truncation nudges**: `finish_reason=length` with no tool call means the
  reasoning chain ate the whole `max_tokens`; the run gets up to three
  "reply with a single tool call now" nudges, and `max_tokens` is raised to
  32768 so the visible answer gets room after reasoning.
- **Context masking**: tool outputs are truncated head+tail at ingestion;
  outputs older than the last 16 tool messages are elided in place, and a
  ~100k estimated-token budget triggers harder elision — message pairing is
  preserved so the history is always valid.
- **`write_file` + `edit_file`**: exact-match edits must be unique;
  ambiguous/not-found errors explain what went wrong so the model can
  self-correct. `write_file` covers new files so `edit_file` stays strict.
- **API resilience**: all calls retry with exponential backoff and are logged
  as `api_retry`; a truncated (`finish_reason=length`) or malformed tool call
  becomes a tool error the model can recover from, not a crash.

## Running

```bash
export CS2680_API_KEY=...
bash evaluation_scripts/run_task.sh 0     # one task
bash evaluation_scripts/run_all.sh        # all provided tasks + eval
```

`MADSLOOP_MAX_ITERS` (default 80) caps iterations; `MADSLOOP_MAX_TOKENS`
(default 32768) sizes the completion budget; `MADSLOOP_PATCH_OUT` overrides
the patch output path (useful for parallel runs); `MADSLOOP_BASELINE=1`
restores the handout-faithful design (no nudges, no `repro_check`, `done`
never pushed back) and is used to produce the `solved_after_change` evidence.

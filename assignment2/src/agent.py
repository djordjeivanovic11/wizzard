"""The agentic loop: model call -> execute tool calls -> feed back -> repeat.

Conversation state lives in `messages`: system prompt, initial user message,
then alternating assistant turns (with their tool_calls) and one tool message
per call, paired by tool_call_id. The model is stateless, so every request
resends the whole history — mask_context() keeps it from growing forever.
"""

import json
import os
import subprocess
import sys
import time
import traceback

from openai import OpenAI

from .logs import JsonlLogger
from .prompts import system_prompt, user_prompt
from .tools import TOOLS, ReproRegistry, execute_tool, truncate

MODEL = os.environ.get("MADSLOOP_MODEL", "qwen3.6-35b-a3b")
BASE_URL = os.environ.get("CS2680_BASE_URL", "https://api.cs2680.com/v1")
# MADSLOOP_BASELINE=1 restores the handout-faithful design (Parts 0/1 as
# written): no no-tool-call nudges, no repro_check tool, `done` is never
# pushed back. Used to demonstrate the before/after for mytest/
# solved_after_change.json — the graded path is the default.
BASELINE = os.environ.get("MADSLOOP_BASELINE", "") in ("1", "true", "yes")

MAX_ITERATIONS = int(os.environ.get("MADSLOOP_MAX_ITERS") or "80")
MAX_TOKENS = int(os.environ.get("MADSLOOP_MAX_TOKENS") or "32768")
MAX_API_RETRIES = 10
KEEP_FULL_TOOL_MSGS = 16   # older tool outputs get elided
EST_TOKEN_BUDGET = 100_000  # rough 4-chars-per-token estimate ceiling


def _est_tokens(messages) -> int:
    return sum(len(str(m.get("content") or "")) +
               sum(len(t.get("function", {}).get("arguments", "")) + 50
                   for t in (m.get("tool_calls") or []))
               for m in messages) // 4


def mask_context(messages) -> None:
    """Shrink old tool outputs in place so the resent history stays bounded.

    The pairing (assistant.tool_calls <-> tool messages) is preserved — only
    `content` shrinks. Recent outputs are kept verbatim; older ones collapse
    to head+tail, and under budget pressure to a stub.
    """
    tool_idx = [i for i, m in enumerate(messages) if m.get("role") == "tool"]
    keep_from = max(tool_idx, default=-1) - KEEP_FULL_TOOL_MSGS * 4
    for i in tool_idx:
        c = messages[i].get("content") or ""
        if i <= keep_from and len(c) > 700:
            messages[i]["content"] = c[:350] + "\n…[older output elided]…\n" + c[-250:]
    # hard budget: elide harder until the estimate fits
    while _est_tokens(messages) > EST_TOKEN_BUDGET and tool_idx:
        for i in tool_idx[:-4]:
            c = messages[i].get("content") or ""
            if len(c) > 300:
                messages[i]["content"] = c[:200] + "\n…[elided]…"
        for i, m in enumerate(messages):
            if m.get("role") == "assistant" and isinstance(m.get("content"), str) \
                    and len(m["content"]) > 2000:
                m["content"] = m["content"][:1500] + "\n…[elided]…"
        if _est_tokens(messages) > EST_TOKEN_BUDGET * 2:
            break  # safety valve


def _tc_dict(tc) -> dict:
    return {"id": tc.id, "type": "function",
            "function": {"name": tc.function.name,
                         "arguments": tc.function.arguments or ""}}


def _chat(client, messages, tools, iteration, logger):
    """One API call with exponential-backoff retries. Logs api_request /
    api_retry events."""
    delay = 2.0
    last_err = None
    for _attempt in range(MAX_API_RETRIES):
        try:
            resp = client.chat.completions.create(
                model=MODEL, messages=messages, tools=tools,
                temperature=0.2, max_tokens=MAX_TOKENS, timeout=300)
            u = resp.usage
            logger.emit("api_request", iteration=iteration,
                        prompt_tokens=getattr(u, "prompt_tokens", None),
                        completion_tokens=getattr(u, "completion_tokens", None),
                        total_tokens=getattr(u, "total_tokens", None))
            return resp
        except Exception as e:
            last_err = e
            logger.emit("api_retry", iteration=iteration,
                        error=f"{type(e).__name__}: {e}"[:500], backoff_s=delay)
            time.sleep(delay)
            delay = min(delay * 2, 60)
    raise RuntimeError(f"API failed after {MAX_API_RETRIES} retries: {last_err}")


def _workdir_has_changes(workdir: str) -> bool:
    try:
        out = subprocess.run(["git", "-C", workdir, "status", "--porcelain"],
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                             text=True, timeout=20)
        return bool(out.stdout.strip())
    except Exception:
        return True  # can't tell -> don't push back


def run_agent(problem: str, workdir: str, log: bool) -> int:
    logger = JsonlLogger(log, os.getcwd())
    repro = ReproRegistry()
    logger.emit("run_start", model_id=MODEL, workdir=workdir)

    try:
        listing = subprocess.run(["ls", "-A", workdir], stdout=subprocess.PIPE,
                                 text=True, timeout=10).stdout
    except Exception:
        listing = "(could not list workdir)"
    listing = "\n".join(listing.split("\n")[:80])

    client = OpenAI(base_url=BASE_URL, api_key=os.environ["CS2680_API_KEY"],
                    max_retries=0)  # we do our own retries to log them
    tools = [t for t in TOOLS
             if not (BASELINE and t["function"]["name"] == "repro_check")]
    if BASELINE:
        print("[madsLoop] BASELINE mode: handout-faithful tools/loop",
              file=sys.stderr)
    messages = [
        {"role": "system", "content": system_prompt(workdir)},
        {"role": "user", "content": user_prompt(problem, workdir, listing)},
    ]

    iteration = 0
    no_tool_nudges = 0
    trunc_nudges = 0
    done_pushbacks = 0
    reason = "limit"
    try:
        while iteration < MAX_ITERATIONS:
            iteration += 1
            resp = _chat(client, messages, tools, iteration, logger)
            if not resp.choices:
                raise RuntimeError("API returned no choices")
            finish = resp.choices[0].finish_reason
            msg = resp.choices[0].message
            tool_calls = list(msg.tool_calls or [])
            messages.append({
                "role": "assistant",
                "content": msg.content or "",
                **({"tool_calls": [_tc_dict(tc) for tc in tool_calls]}
                   if tool_calls else {}),
            })
            print(f"[iter {iteration}] finish={finish} "
                  f"tools={[tc.function.name for tc in tool_calls]} "
                  f"content_len={len(msg.content or '')}", file=sys.stderr)
            if msg.content and not tool_calls:
                print(f"[iter {iteration}] text: "
                      f"{(msg.content or '')[:300]!r}", file=sys.stderr)

            if not tool_calls:
                if not BASELINE and finish == "length" and trunc_nudges < 3:
                    trunc_nudges += 1
                    messages.append({"role": "user", "content": (
                        "Your reply was cut off at the token limit before any "
                        "tool call was made. Keep your reasoning SHORT and "
                        "respond with exactly one tool call now — the single "
                        "most useful next step.")})
                    continue
                if not BASELINE and no_tool_nudges < 2:
                    no_tool_nudges += 1
                    messages.append({"role": "user", "content": (
                        "You must act through tool calls, not plain text. "
                        "Keep going: run commands, edit files, and call "
                        "`done` only when the fix is complete and verified.")})
                    continue
                reason = "no_tool_calls"
                break
            no_tool_nudges = 0

            finished = False
            for tc in tool_calls:
                name = tc.function.name or ""
                raw_args = tc.function.arguments or ""
                logger.emit("tool_call", iteration=iteration,
                            tool_name=name,
                            arguments=_safe_json(raw_args))

                if name == "done":
                    summary = "(no summary)"
                    try:
                        summary = json.loads(raw_args).get("summary", summary)
                    except Exception:
                        pass
                    ok, result = (True, f"done: {summary}") if BASELINE else \
                        _handle_done(workdir, repro, summary, done_pushbacks)
                    logger.emit("tool_result", iteration=iteration,
                                tool_name="done", result=result, is_error=False)
                    messages.append({"role": "tool", "tool_call_id": tc.id,
                                     "content": result})
                    if ok:
                        finished = True
                    else:
                        done_pushbacks += 1
                    continue

                result, is_error = execute_tool(name, raw_args, workdir, repro)
                logger.emit("tool_result", iteration=iteration, tool_name=name,
                            result=result, is_error=is_error)
                messages.append({"role": "tool", "tool_call_id": tc.id,
                                 "content": result})
            if finished:
                reason = "done"
                break
            mask_context(messages)
    except Exception:
        traceback.print_exc()
        reason = "error"
    finally:
        logger.emit("run_end", reason=reason, num_iterations=iteration)
        logger.close()
    return 0 if reason in ("done", "no_tool_calls", "limit") else 1


def _safe_json(raw: str):
    try:
        return json.loads(raw)
    except Exception:
        return {"_raw": raw}


def _handle_done(workdir, repro: ReproRegistry, summary: str,
                 pushbacks_so_far: int):
    """Decide whether `done` is accepted. Push back at most twice: once for an
    empty diff, and when registered repro checks fail."""
    if pushbacks_so_far >= 2:
        return True, f"done: {summary}"
    if not _workdir_has_changes(workdir):
        return False, ("pushback: `git status` shows no changes in the repo — "
                       "there is nothing to submit. If the task is truly "
                       "impossible, call done again with an explanation; "
                       "otherwise make the fix first.")
    if repro.checks:
        results = repro.rerun_all()
        if any("FAILED" in r for r in results):
            return False, ("pushback: a registered repro_check still fails:\n"
                           + "\n".join(results)[-4000:]
                           + "\nFix it, or update/remove the check if it was "
                             "wrong, then call done again.")
    return True, f"done: {summary}"

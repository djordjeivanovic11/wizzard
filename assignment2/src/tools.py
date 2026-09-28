"""Tool definitions and executors.

Every executor returns (result_text, is_error). The result_text is what goes
into the tool message — and is logged in `tool_result.result` verbatim, after
truncation, so the log reflects exactly what the model saw.
"""

import json
import os
import subprocess

MAX_OUTPUT_CHARS = 30000   # per tool result, head+tail kept
MAX_READ_LINES = 2000
DEFAULT_READ_LINES = 400
BASH_DEFAULT_TIMEOUT = 180
BASH_MAX_TIMEOUT = 900


def truncate(text: str, limit: int = MAX_OUTPUT_CHARS) -> str:
    """Keep the head and tail of a long output; drop the middle."""
    if len(text) <= limit:
        return text
    head = int(limit * 0.45)
    tail = limit - head
    return (text[:head]
            + f"\n\n... [{len(text) - head - tail} bytes omitted] ...\n\n"
            + text[-tail:])


def _resolve(workdir: str, path: str):
    """Resolve a model-supplied path against workdir; refuse escapes."""
    p = path if os.path.isabs(path) else os.path.join(workdir, path)
    real = os.path.realpath(p)
    root = os.path.realpath(workdir)
    if real != root and not real.startswith(root + os.sep):
        return None, f"error: path {path!r} is outside the repository {workdir}"
    return real, None


def _bash(args: dict, workdir: str):
    command = args.get("command")
    if not isinstance(command, str) or not command.strip():
        return "error: 'command' must be a non-empty string", True
    try:
        timeout = int(args.get("timeout_s", BASH_DEFAULT_TIMEOUT))
    except (TypeError, ValueError):
        timeout = BASH_DEFAULT_TIMEOUT
    timeout = max(5, min(timeout, BASH_MAX_TIMEOUT))
    try:
        proc = subprocess.run(
            ["bash", "-c", command],
            cwd=workdir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
    except subprocess.TimeoutExpired:
        return f"error: command timed out after {timeout}s (killed)", True
    except Exception as e:  # e.g. no bash in image
        return f"error: failed to run command: {e}", True
    out = proc.stdout
    if proc.stderr:
        out += ("\n" if out and not out.endswith("\n") else "") \
            + "[stderr]\n" + proc.stderr
    if proc.returncode != 0:
        out += f"\n[exit code {proc.returncode}]"
    if not out.strip():
        out = f"[exit code {proc.returncode}] (no output)"
    return truncate(out), False


def _read_file(args: dict, workdir: str):
    path = args.get("path")
    if not isinstance(path, str) or not path.strip():
        return "error: 'path' must be a non-empty string", True
    real, err = _resolve(workdir, path)
    if err:
        return err, True
    if not os.path.exists(real):
        return f"error: no such file or directory: {path}", True
    if os.path.isdir(real):
        try:
            entries = sorted(os.listdir(real))
        except OSError as e:
            return f"error: cannot list {path}: {e}", True
        lines = [e + "/" if os.path.isdir(os.path.join(real, e)) else e
                 for e in entries]
        return truncate("\n".join(lines) or "(empty directory)"), False
    try:
        with open(real, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except OSError as e:
        return f"error: cannot read {path}: {e}", True
    lines = content.split("\n")
    total = len(lines)
    try:
        offset = max(1, int(args.get("offset", 1)))
    except (TypeError, ValueError):
        offset = 1
    try:
        limit = int(args.get("limit", DEFAULT_READ_LINES))
    except (TypeError, ValueError):
        limit = DEFAULT_READ_LINES
    limit = max(1, min(limit, MAX_READ_LINES))
    sel = lines[offset - 1: offset - 1 + limit]
    body = "\n".join(f"{offset + i:>6}\t{l}" for i, l in enumerate(sel))
    note = ""
    if offset + len(sel) - 1 < total:
        note = (f"\n[{total} lines total; showing {offset}-"
                f"{offset + len(sel) - 1}. Use offset/limit for more.]")
    elif offset > 1:
        note = f"\n[{total} lines total; end reached]"
    if not sel:
        return f"(file exists, 0 lines)" if total <= 1 else \
            f"error: offset {offset} beyond end of file ({total} lines)", total <= 1
    return truncate(body + note), False


def _edit_file(args: dict, workdir: str):
    path = args.get("path")
    old = args.get("old_string")
    new = args.get("new_string")
    for k, v in (("path", path), ("old_string", old), ("new_string", new)):
        if not isinstance(v, str):
            return f"error: '{k}' must be a string", True
    if old == "":
        return "error: old_string is empty — use write_file to create/overwrite files", True
    if old == new:
        return "error: old_string and new_string are identical", True
    real, err = _resolve(workdir, path)
    if err:
        return err, True
    if not os.path.isfile(real):
        return f"error: {path} does not exist or is not a file (use write_file to create it)", True
    try:
        with open(real, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except OSError as e:
        return f"error: cannot read {path}: {e}", True
    count = content.count(old)
    if count == 0:
        return (f"error: old_string not found in {path}. "
                "Re-read the exact text with read_file (whitespace must match)."), True
    if count > 1:
        return (f"error: old_string occurs {count} times in {path}. "
                "Include more surrounding context to make it unique."), True
    new_content = content.replace(old, new, 1)
    try:
        with open(real, "w", encoding="utf-8") as f:
            f.write(new_content)
    except OSError as e:
        return f"error: cannot write {path}: {e}", True
    # Show the edited region back so the model sees the result immediately.
    upto = new_content[: new_content.index(new) + len(new)]
    line_no = upto.count("\n") + 1
    ctx = new_content.split("\n")
    lo, hi = max(0, line_no - 6), min(len(ctx), line_no + 5)
    snippet = "\n".join(f"{lo + i + 1:>6}\t{l}" for i, l in enumerate(ctx[lo:hi]))
    return f"ok: edited {path}\n{snippet}", False


def _write_file(args: dict, workdir: str):
    path = args.get("path")
    content = args.get("content")
    if not isinstance(path, str) or not path.strip():
        return "error: 'path' must be a non-empty string", True
    if not isinstance(content, str):
        return "error: 'content' must be a string", True
    real, err = _resolve(workdir, path)
    if err:
        return err, True
    try:
        os.makedirs(os.path.dirname(real), exist_ok=True)
        existed = os.path.exists(real)
        with open(real, "w", encoding="utf-8") as f:
            f.write(content)
    except OSError as e:
        return f"error: cannot write {path}: {e}", True
    verb = "overwrote" if existed else "created"
    return f"ok: {verb} {path} ({len(content)} bytes)", False


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": "Run a shell command inside the repository (grep, find, ls, running tests, python, etc.). Output is truncated if very long — prefer narrow, targeted commands.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "the shell command to run"},
                    "timeout_s": {"type": "integer", "description": "seconds before the command is killed (default 180, max 900)"},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file with line numbers (for exact edits later), or list a directory. Path is relative to the repo root (or absolute inside it).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "offset": {"type": "integer", "description": "1-based first line to show (default 1)"},
                    "limit": {"type": "integer", "description": "max lines to show (default 400)"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Replace an exact string in a file. old_string must match exactly once — include enough surrounding context (indentation matters). Read the file first to get exact text.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "old_string": {"type": "string", "description": "exact text to replace; must occur exactly once"},
                    "new_string": {"type": "string", "description": "replacement text"},
                },
                "required": ["path", "old_string", "new_string"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create a new file or overwrite a whole file with the given content. Prefer edit_file for changing existing files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "repro_check",
            "description": "Register and run a reproduction check: a shell command that demonstrates the bug (e.g. `python /tmp/repro.py`) or validates the fix. Checks run in /tmp now, and are re-run once when you call `done` — a check that still fails blocks finishing. Register a check BEFORE editing to confirm it fails, and keep it updated.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "shell command whose exit code is the check (0 = pass)"},
                    "name": {"type": "string", "description": "short label for the check"},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "done",
            "description": "Declare the task finished. Only call when the fix is complete and verified, or the task is impossible.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string", "description": "what you changed and how you verified it"},
                },
                "required": ["summary"],
            },
        },
    },
]


class ReproRegistry:
    """Reproduction checks registered via the repro_check tool; re-run at done."""

    def __init__(self):
        self.checks = []  # list of {"name": str, "command": str}

    def add_and_run(self, command: str, name: str):
        self.checks.append({"name": name or command[:60], "command": command})
        return run_check(command)

    def rerun_all(self):
        out = []
        for c in self.checks:
            res, _ = run_check(c["command"])
            out.append(f"--- {c['name']}\n{res}")
        return out


def run_check(command: str):
    """Run a check command in /tmp; returns (text, exit_ok)."""
    try:
        proc = subprocess.run(["bash", "-c", command], cwd="/tmp",
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              text=True, timeout=120)
    except subprocess.TimeoutExpired:
        return "error: check timed out after 120s", False
    except Exception as e:
        return f"error: check failed to run: {e}", False
    out = proc.stdout
    if proc.stderr:
        out += ("\n" if out and not out.endswith("\n") else "") \
            + "[stderr]\n" + proc.stderr
    status = f"[check {'PASSED' if proc.returncode == 0 else 'FAILED'} exit={proc.returncode}]"
    return truncate((out + "\n" + status).strip()), proc.returncode == 0


def execute_tool(name: str, arguments, workdir: str, repro: ReproRegistry):
    """Run one tool call. Returns (result_text, is_error). `done` is handled
    by the caller (the agent loop) and never reaches here."""
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments) if arguments.strip() else {}
        except json.JSONDecodeError as e:
            return f"error: malformed arguments JSON: {e}", True
    if not isinstance(arguments, dict):
        return "error: arguments must be a JSON object", True
    try:
        if name == "bash":
            return _bash(arguments, workdir)
        if name == "read_file":
            return _read_file(arguments, workdir)
        if name == "edit_file":
            return _edit_file(arguments, workdir)
        if name == "write_file":
            return _write_file(arguments, workdir)
        if name == "repro_check":
            cmd = arguments.get("command")
            if not isinstance(cmd, str) or not cmd.strip():
                return "error: 'command' must be a non-empty string", True
            text, ok = repro.add_and_run(cmd, str(arguments.get("name", "")))
            return text, not ok
        return (f"error: unknown tool {name!r}. Available: "
                "bash, read_file, edit_file, write_file, repro_check, done"), True
    except Exception as e:  # never let a tool crash the run
        return f"error: {type(e).__name__}: {e}", True

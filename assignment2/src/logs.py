"""JSONL run-trace logger.

One file per run under ./madsLoop_logs/ in the current working directory,
one JSON object per event, in order. Every line carries `timestamp`
(ISO-8601) and `event`; the remaining fields follow the assignment schema:

    run_start    model_id, workdir
    api_request  iteration, prompt_tokens, completion_tokens, total_tokens
    api_retry    iteration, error, backoff_s
    tool_call    iteration, tool_name, arguments
    tool_result  iteration, tool_name, result (truncated exactly as fed to
                 the model), is_error
    run_end      reason, num_iterations
"""

import json
import os
import time
from datetime import datetime, timezone


class JsonlLogger:
    def __init__(self, enabled: bool, log_dir_root: str):
        self._fh = None
        self.path = None
        if enabled:
            d = os.path.join(log_dir_root, "madsLoop_logs")
            os.makedirs(d, exist_ok=True)
            self.path = os.path.join(
                d, f"run_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}_{int(time.time() * 1000) % 100000}.jsonl")
            self._fh = open(self.path, "a", buffering=1, encoding="utf-8")

    @property
    def enabled(self) -> bool:
        return self._fh is not None

    def emit(self, event: str, **fields) -> None:
        if self._fh is None:
            return
        rec = {"timestamp": datetime.now(timezone.utc).isoformat(),
               "event": event}
        rec.update(fields)
        self._fh.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")

    def close(self) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None

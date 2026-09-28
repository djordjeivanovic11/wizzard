# Assignment 2 write-up — madsLoop

<!--
  NOTE (delete me): SKELETON + DATA. The write-up must be entirely your own
  words — replace every [WRITE] block and rewrite any fact lines in your own
  voice, then build:
      pandoc writeup.md -o writeup.pdf        (or paste into your editor)
  Hard limit: one page.
-->

## 1. Which given tasks are unsolvable, and why

<!-- Evidence collected this run (verify before you write):

  * instance_protonmail__webclients-944adbfe06644be0789f59b78395bdd8567d8547
    — EVAL-DATA BUG: selected_test_files_to_run includes
    "tests/observeApiError.test.ts", which does not exist in the repo (the
    real file is packages/metrics/tests/observeApiError.test.ts and is what
    before_repo_set_cmd checks out). Every fail_to_pass id is prefixed with
    the nonexistent path ("tests/observeApiError.test.ts | ..."), and the
    eval's run of the selected files prints "No tests found, exiting with
    code 1" — no patch can make a never-collected test pass.
    Evidence: pro_eval/instance_protonmail*/workspace/stdout.log tail.
    Agent run: produced a 1820-byte patch (model_patch_instance_protonmail*);
    eval scored false with all 9 fail_to_pass MISSING.

  * Candidates whose provided tasks the agent repeatedly failed — decide
    yourself whether the task or the agent is at fault:
    - instance_gravitational__teleport-...89f0432a (Go): agent patch exists
      (1504 B) but fail_to_pass `TestReadAtMost` still fails.
    - instance_ansible__ansible-83909bfa... (test_api_no_auth_but_required)
    - instance_ansible__ansible-a26c325b... (test_open_url; agent passed 3/4)
    - instance_qutebrowser__qutebrowser-21b426b6... (2/3 ftp pass)
    - instance_qutebrowser__qutebrowser-c580ebf0... (11 ftp tests still fail:
      test_widen_hostnames/test_bench_widen_hostnames — the patch widens
      hostnames but misses edge-case semantics)
    - Final state: every failed task now has a real non-empty patch, each
      missing 1-2 tests (near-misses, not empty runs).

  * Resolved: ansible-f327, flipt-2eac, qute-de4a1, openlibrary-4a5d = 4/10.

  Remember: "Get a PASS for unsolvable tasks will lose points" — only claim a
  task unsolvable when the TASK itself is broken (like protonmail), not when
  the agent merely failed.
-->

[WRITE — e.g. `instance_protonmail__webclients-944adbf…`: the eval can never
collect `tests/observeApiError.test.ts` because ...]

## 2. What I did differently from the handout

<!-- True departures in the submitted code — keep what you can defend, in your
     own words:

     - run_task.sh feeds requirements + interface fields, not only
       problem_statement (the graded spec lives there).
     - a no-tool-call reply is nudged up to twice instead of ending the run
       (the model writes analysis text mid-run; without it the run ends with
       an empty patch — observed on ansible-f327's first attempt).
     - a truncated reply (finish_reason=length) gets up to three short
       "one tool call now" nudges (the model is a reasoning model; its chain
       ate the whole max_tokens on long runs — observed on qutebrowser-c580).
     - max_tokens raised 16384 -> 32768 for the same reason.
     - a repro_check tool runs the agent's registered reproduction commands
       in /tmp and re-runs them at done-time (catches "fixed but regressed").
     - done is verified: an empty `git status` or a failing repro pushes back
       up to twice (the model otherwise quits early or claims victory).
     - tool outputs are truncated at ingest (30k chars, head+tail) and older
       ones elided in place (context stays bounded, pairing preserved).
     - write_file for new files; edit_file reports descriptive errors on
       zero/multiple matches (a 35B model needs the feedback).
     - harness interpreter is auto-selected >=3.10 (uv bootstrap fallback) so
       modern syntax works on ancient image pythons; the agent's bash tool
       still uses the image python.
-->

- [WRITE]

## 3. The two solved_after_change tasks

<!-- For each: what failed at first (the MADSLOOP_BASELINE=1 run), what you
     changed, how the change turns failure into pass.

     Data (submitted set):
     - mytest_moreit_seekable: BASELINE run ended no_tool_calls, bash/read
       only -> empty patch.  Improved run produced a seekable maxlen=0 fix
       that verify.sh scores RESOLVED (see results/*.before/after.log).
     - mytest_packaging_tokend: improved run resolves
       (results/mytest_packaging_tokend.after.log).  NOTE: the BASELINE run
       was cut off by the course API budget before finishing, so the
       "failed at first" side of the story rests on your word — if budget
       returns, rerun `MADSLOOP_BASELINE=1` on it once for your own
       confidence before writing.
     - Runner-up candidates already proven unsuitable: unbounded, asciiskip,
       tags_empty, bucket_phantom, falsyexc — the BASELINE already solves
       them. fold + hardcut are the submitted unsolved pair: fold's improved
       patch fails on a pass_to_pass regression (the \\r\\n boundary folds
       twice instead of once) — madsLoop_logs/mytest_packaging_fold has the
       real failed patch; hardcut's runs ended no_tool_calls with zero
       edits (two independent attempts).
-->

**task 1 (mytest_moreit_seekable)** — [WRITE]

**task 2 (mytest_packaging_tokend)** — [WRITE]

## 4. The two unsolved tasks

<!--
     - mytest_packaging_fold: both baseline and improved produced real
       patches that fail. Improved patch fixes every fail_to_pass but
       regresses pass_to_pass test_headers_fold_every_line_boundary[\\r\\n]:
       the agent folded each boundary char separately (re.sub per-char)
       instead of treating \\r\\n as ONE boundary — verify log:
       results/mytest_packaging_fold.after.log is gold (RESOLVED);
       the agent patch's own failure log lives in
       madsLoop_logs/mytest_packaging_fold/ and /tmp evidence.
     - mytest_slugify_hardcut: agent ended with no_tool_calls twice
       (baseline 17 iters, second attempt 9 iters) producing no edits —
       the fix is a small post-replacement-delimiter guard but the model
       never committed to an edit. Gold patch resolves
       (results/mytest_slugify_hardcut.after.log).
-->

**task 1 (mytest_packaging_fold)** — [WRITE]

**task 2 (mytest_slugify_hardcut)** — [WRITE]

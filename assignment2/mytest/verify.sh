#!/bin/bash
# verify.sh — score a patch on a mytest task, mirroring the official
# SWE-bench Pro rule: start a fresh container from the task image, run
# before_repo_set_cmd (which also restores the graded test files), apply the
# patch, run selected_test_files_to_run, and print RESOLVED only if every
# fail_to_pass test passes and no pass_to_pass test regresses.
#
#   bash mytest/verify.sh <instance_id> [diff_file]
#
# diff_file is a path inside the repo root (e.g. model_patch_<iid>.diff or
# mytest/tasks/<iid>/gold.diff). Omit it for the base_commit baseline.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${MADSLOOP_REPO:-$PWD}" && pwd)"
IID="${1:?usage: verify.sh <instance_id> [diff_file]}"
DIFF="${2:-}"

IMAGE=$(python3 -c "
import json
for f in ('solved_after_change.json', 'unsolved.json'):
    t = json.load(open('$SCRIPT_DIR/' + f))
    if '$IID' in t:
        print(t['$IID']['docker_image']); break
else:
    raise SystemExit('unknown instance_id $IID')
")

INNER_PATCH=""
if [[ -n "$DIFF" ]]; then
  [[ -f "$REPO_ROOT/$DIFF" ]] || { echo "error: no diff at $REPO_ROOT/$DIFF" >&2; exit 1; }
  INNER_PATCH="/madsLoop/$DIFF"
fi

docker run --rm \
  --entrypoint bash \
  -v "$REPO_ROOT:/madsLoop" \
  -e MADT_IID="$IID" -e MADT_PATCH="$INNER_PATCH" \
  "$IMAGE" -c '
set -e
cd /app
# restore base + graded test files
python3 - <<PY
import json, subprocess
t = json.load(open("/madsLoop/mytest/task_test.json"))["$MADT_IID"]
subprocess.run(["bash", "-c", t["before_repo_set_cmd"]], check=True)
PY
if [ -n "$MADT_PATCH" ]; then
  git apply "$MADT_PATCH" || { echo "PATCH DID NOT APPLY"; exit 3; }
fi
python3 - <<PY
import json, subprocess, sys, xml.etree.ElementTree as ET
t = json.load(open("/madsLoop/mytest/task_test.json"))["$MADT_IID"]
files = t["selected_test_files_to_run"]
subprocess.run(["python", "-m", "pytest", "-q", "--tb=short",
                "--junitxml=/tmp/report.xml", *files], check=False)
passed, failed = set(), set()
tree = ET.parse("/tmp/report.xml")
for tc in tree.iter("testcase"):
    cls, name = tc.get("classname"), tc.get("name")
    f = cls.rsplit(".", 1)
    if len(f) == 2 and not f[1][0].islower():
        node = f[0].replace(".", "/") + ".py::" + f[1] + "::" + name
    else:
        node = cls.replace(".", "/") + ".py::" + name
    (failed if list(tc) else passed).add(node)
ftp, ptp = set(t["fail_to_pass"]), set(t["pass_to_pass"])
missing = (ftp | ptp) - passed - failed
bad_ftp = sorted(x for x in ftp if x not in passed)
bad_ptp = sorted(x for x in ptp if x not in passed)
for n in sorted(passed & (ftp | ptp)):
    print("PASS", n)
for n in sorted(failed & (ftp | ptp)):
    print("FAIL", n)
for n in sorted(missing):
    print("MISSING (did not run):", n)
if not bad_ftp and not bad_ptp and not missing:
    print("RESOLVED")
else:
    print("unresolved:")
    for n in bad_ftp: print("  fail_to_pass still failing:", n)
    for n in bad_ptp: print("  pass_to_pass regressed:", n)
    for n in missing: print("  never ran:", n)
    sys.exit(2)
PY'

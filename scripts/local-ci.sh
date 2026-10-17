#!/usr/bin/env bash
# Local replica of .github/workflows/ci.yml.
#
# Runs every CI step in the same order and prints PASS/FAIL per step.
# Stops at the first failed step. The exit code is the exit code of the gate.
#
# Usage:
#   conda activate <env with python 3.11>
#   scripts/local-ci.sh
#
# The test job installs the package into the active environment
# (pip install -e ".[dev]"), the same as CI. Use a scratch conda env.
#
# Unlike CI, the test step is BLOCKING here: CI marks the test job
# continue-on-error, which hides failures. Set RALPHX_CI_TESTS_NONBLOCKING=1
# to copy the CI behavior exactly.

set -u
cd "$(dirname "$0")/.."

fail() {
    echo "FAIL: $1"
    exit 1
}

step() {
    local name="$1"
    shift
    echo "=== STEP: $name"
    "$@"
    local rc=$?
    if [ $rc -eq 0 ]; then
        echo "PASS: $name"
    else
        fail "$name (exit $rc)"
    fi
}

build_frontend() {
    (cd frontend && npm ci && npm run build)
}

copy_frontend() {
    rm -rf ralphx/static && mkdir -p ralphx/static && cp -r frontend/dist/* ralphx/static/
}

build_package() {
    rm -rf dist && python -m build
}

verify_package() {
    local venv
    venv="$(mktemp -d)/verify-env"
    python -m venv "$venv" || return 1
    "$venv/bin/pip" install -q dist/*.whl || return 1
    (cd /tmp && "$venv/bin/python" -c "
from pathlib import Path
import ralphx
static = Path(ralphx.__file__).parent / 'static'
index = static / 'index.html'
assets = static / 'assets'
assert index.exists(), f'Missing {index}'
assert assets.exists() and assets.is_dir(), f'Missing assets directory {assets}'
print(f'Verified: {index}')
print(f'Verified: {assets}')
") || return 1
    echo "Package includes frontend static files"
}

install_dev() {
    pip install -q -e ".[dev]"
}

run_tests() {
    if [ "${RALPHX_CI_TESTS_NONBLOCKING:-0}" = "1" ]; then
        pytest tests/ -v || echo "Tests have known failures - see TODO"
    else
        pytest tests/ -v
    fi
}

# Job: build
step "build: Build frontend" build_frontend
step "build: Copy frontend to package" copy_frontend
step "build: Install build tools" pip install -q build
step "build: Build package" build_package
step "build: Verify package contents" verify_package

# Job: test
step "test: Install dependencies" install_dev
step "test: Run tests" run_tests

echo "ALL STEPS PASSED"

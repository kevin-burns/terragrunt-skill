#!/usr/bin/env bash
#
# Deterministic CI entrypoint for terragrunt-skill.
# Syntax checks, unit tests, and the pre-1.0 guard. Nothing here touches a cloud.
#
# THIS SCRIPT WAS BROKEN FROM ITS FIRST COMMIT. Until 2026-08-19 it declared three paths that
# had never existed in this repository -- scripts/validate_terragrunt.sh (the script is
# validate.sh), test/test_validate_terragrunt.sh, and test/test_detect_custom_resources.py --
# and there has never been a test/ directory. It exited 127 on step 1 of 5. It shipped in the
# founding commit 3af01f3 on 2026-06-11 and nothing ever ran it, so nothing ever noticed.
# Tracked as claude-skills-3io.
#
# Two consequences shaped the rewrite:
#   * Every declared path is now checked for existence FIRST, and a missing one is named. A
#     bare 127 tells you nothing about which file moved.
#   * The two phantom regression tests are gone rather than left as steps pointing at files
#     nobody has. That left validate.sh and detect_custom_resources.py with NO regression test
#     of their own -- a real gap, recorded rather than papered over, and CLOSED on 2026-08-20
#     by tests/test_validate_sh.py and tests/test_detect_custom_resources.py
#     (claude-skills-gm0). Writing them found validate.sh gating on Terragrunt 0.93, a pre-1.0
#     floor inside a skill whose first hard policy bans pre-1.0 forms.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_DIR
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
readonly SKILL_DIR

VALIDATOR_SCRIPT="$SKILL_DIR/scripts/validate.sh"
DETECTOR_SCRIPT="$SKILL_DIR/scripts/detect_custom_resources.py"
PREFLIGHT_SCRIPT="$SKILL_DIR/scripts/preflight.py"
SCAN_SCRIPT="$SKILL_DIR/scripts/scan_pre10.py"
BANNER_SCRIPT="$SKILL_DIR/scripts/make_banner.py"
TESTS_DIR="$SKILL_DIR/tests"
SELF_SCRIPT="$SCRIPT_DIR/$(basename "${BASH_SOURCE[0]}")"

usage() {
    cat <<'EOF'
Usage: run_ci_checks.sh [OPTIONS]

Deterministic CI checks for terragrunt-skill.

Options:
  --require-shellcheck   Fail when shellcheck is unavailable.
  --skip-shellcheck      Skip the shellcheck stage.
  -h, --help             Show this help message.

Environment:
  CI=true|1              Defaults to --require-shellcheck unless overridden.
EOF
}

is_true() {
    local value="${1:-}"
    [[ "$value" == "true" || "$value" == "1" ]]
}

# Resolve uv rather than falling back to a bare python3: the test run needs pytest, and a
# non-interactive shell often drops ~/.local/bin and the Homebrew bin from PATH.
resolve_uv() {
    command -v uv 2>/dev/null && return 0
    local candidate
    for candidate in "$HOME/.local/bin/uv" "$HOME/.cargo/bin/uv" /opt/homebrew/bin/uv /usr/local/bin/uv; do
        [[ -x "$candidate" ]] && { echo "$candidate"; return 0; }
    done
    return 1
}

# The check that this script did not have, and the reason it failed uselessly for 69 days.
assert_paths_exist() {
    local missing=0 path
    for path in "$@"; do
        if [[ ! -e "$path" ]]; then
            echo "MISSING: $path" >&2
            missing=1
        fi
    done
    if [[ "$missing" -eq 1 ]]; then
        echo "" >&2
        echo "A declared path does not exist. Fix the path in this script, or restore the file." >&2
        echo "Do NOT delete the step -- a check that silently skips is how this script came to" >&2
        echo "sit broken in the repository for 69 days without anyone noticing." >&2
        exit 1
    fi
}

main() {
    local require_shellcheck=0
    local skip_shellcheck=0
    local shellcheck_overridden=0

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --require-shellcheck) require_shellcheck=1; skip_shellcheck=0; shellcheck_overridden=1 ;;
            --skip-shellcheck)    skip_shellcheck=1; require_shellcheck=0; shellcheck_overridden=1 ;;
            -h|--help)            usage; exit 0 ;;
            *)  echo "Error: unknown option '$1'" >&2; usage; exit 1 ;;
        esac
        shift
    done

    if [[ "$shellcheck_overridden" -eq 0 ]] && is_true "${CI:-}"; then
        require_shellcheck=1
    fi
    if [[ "$skip_shellcheck" -eq 1 && "$require_shellcheck" -eq 1 ]]; then
        echo "Error: --skip-shellcheck and --require-shellcheck cannot be combined." >&2
        exit 1
    fi

    export LC_ALL=C
    export LANG=C
    export TZ=UTC

    echo "[0/6] declared paths exist"
    assert_paths_exist "$VALIDATOR_SCRIPT" "$DETECTOR_SCRIPT" "$PREFLIGHT_SCRIPT" \
                       "$SCAN_SCRIPT" "$BANNER_SCRIPT" "$TESTS_DIR" "$SELF_SCRIPT"

    echo "[1/6] bash syntax"
    bash -n "$VALIDATOR_SCRIPT" "$SELF_SCRIPT"

    echo "[2/6] python syntax"
    python3 -m py_compile "$DETECTOR_SCRIPT" "$PREFLIGHT_SCRIPT" "$SCAN_SCRIPT" "$BANNER_SCRIPT"

    echo "[3/6] unit tests"
    local uv_bin
    if uv_bin="$(resolve_uv)"; then
        "$uv_bin" run --with pytest pytest "$TESTS_DIR" -q
    elif python3 -c 'import pytest' 2>/dev/null; then
        echo "  (uv not found; using the ambient python3 -m pytest)"
        python3 -m pytest "$TESTS_DIR" -q
    else
        echo "Error: neither uv nor an importable pytest is available; cannot run tests." >&2
        echo "       Install uv, or pip install pytest. Do not skip this step." >&2
        exit 1
    fi

    # The regression guard for claude-skills-c3x and claude-skills-cun. Both were pre-1.0 forms
    # taught as current inside files harvested from a source that predates Terragrunt v1.0.0.
    # Without this step they can come back silently.
    echo "[4/6] pre-1.0 guard"
    python3 "$SCAN_SCRIPT"

    echo "[5/6] shellcheck"
    if [[ "$skip_shellcheck" -eq 1 ]]; then
        echo "ShellCheck: SKIP (--skip-shellcheck)"
    elif command -v shellcheck >/dev/null 2>&1; then
        shellcheck "$VALIDATOR_SCRIPT" "$SELF_SCRIPT"
        echo "ShellCheck: PASS"
    elif [[ "$require_shellcheck" -eq 1 ]]; then
        echo "ShellCheck: required but not installed" >&2
        exit 1
    else
        echo "ShellCheck: SKIP (not installed; use --require-shellcheck to enforce)"
    fi

    # The banner carries a terragrunt version, which is a pin baked into an image -- exactly
    # the shape this skill was hardened against, and worse than prose because a picture cannot
    # be grepped. This WARNS rather than fails: a check that breaks the build the day
    # Terragrunt ships a patch is a check that gets commented out. Skips cleanly with no
    # terragrunt, because there is then no version to compare against and inventing one is the
    # failure being guarded.
    echo "[6/6] banner freshness"
    if command -v terragrunt >/dev/null 2>&1; then
        python3 "$BANNER_SCRIPT" --check
    else
        echo "Banner: SKIP (terragrunt not installed; nothing to read a version from)"
    fi

    echo "PASS: terragrunt-skill CI checks"
}

main "$@"

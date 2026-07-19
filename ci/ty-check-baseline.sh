#!/usr/bin/env bash
set -euo pipefail

# ty no-regression guard for mcp_agent_mail_secure.
#
# Compares current ty diagnostics against a reviewed baseline.
# Fails if any NEW diagnostic appears that is not in the baseline.
# Removing existing diagnostics (fixing type debt) is always allowed.
#
# Baseline refresh: run `ci/ty-check-baseline.sh --refresh` after
# fixing type errors, review the diff, commit.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASELINE="$SCRIPT_DIR/ty-baseline.txt"

if [[ "${1:-}" == "--refresh" ]]; then
    TY_OUT=$(uvx ty check 2>&1 || true)
    echo "$TY_OUT" | awk '
    /^error\[/ { code = $0; sub(/\]:.*/, "]", code); expect_loc = 1; next }
    expect_loc && /^[[:space:]]*-->/ {
        loc = $0; sub(/^[[:space:]]*--> /, "", loc)
        if (loc !~ /^\.venv\//) print loc " " code
        expect_loc = 0
    }
    /^info:/ || /^$/ { expect_loc = 0 }
    ' | sort > "$BASELINE"
    echo "Baseline refreshed: $(wc -l < "$BASELINE") diagnostics in $BASELINE"
    exit 0
fi

if [[ ! -f "$BASELINE" ]]; then
    echo "ERROR: baseline file not found at $BASELINE"
    echo "Run: ci/ty-check-baseline.sh --refresh"
    exit 1
fi

CURRENT=$(mktemp)
trap 'rm -f "$CURRENT"' EXIT

TY_OUTPUT=$(uvx ty check 2>&1 || true)
echo "$TY_OUTPUT" | awk '
/^error\[/ { code = $0; sub(/\]:.*/, "]", code); expect_loc = 1; next }
expect_loc && /^[[:space:]]*-->/ {
    loc = $0; sub(/^[[:space:]]*--> /, "", loc)
    if (loc !~ /^\.venv\//) print loc " " code
    expect_loc = 0
}
/^info:/ || /^$/ { expect_loc = 0 }
' | sort > "$CURRENT"

BASELINE_COUNT=$(wc -l < "$BASELINE" | tr -d ' ')
CURRENT_COUNT=$(wc -l < "$CURRENT" | tr -d ' ')

NEW_DIAGNOSTICS=$(comm -13 "$BASELINE" "$CURRENT")

if [[ -n "$NEW_DIAGNOSTICS" ]]; then
    NEW_COUNT=$(echo "$NEW_DIAGNOSTICS" | wc -l | tr -d ' ')
    echo "FAIL: $NEW_COUNT new ty diagnostic(s) not in baseline"
    echo ""
    echo "New diagnostics:"
    echo "$NEW_DIAGNOSTICS"
    echo ""
    echo "Baseline: $BASELINE_COUNT | Current: $CURRENT_COUNT | New: $NEW_COUNT"
    echo ""
    echo "To accept these as known debt (after review):"
    echo "  ci/ty-check-baseline.sh --refresh"
    exit 1
fi

REMOVED_COUNT=$(comm -23 "$BASELINE" "$CURRENT" | wc -l | tr -d ' ')
echo "OK: no new ty diagnostics (baseline=$BASELINE_COUNT, current=$CURRENT_COUNT, removed=$REMOVED_COUNT)"

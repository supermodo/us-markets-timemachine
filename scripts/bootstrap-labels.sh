#!/usr/bin/env bash
# One-time GitHub label bootstrap for us-markets-timemachine.
#
# The daily worker opens issues for anomalies with three labels per issue:
# `worker-anomaly`, `status:<x>`, `kind:<y>` (see src/timemachine/notify.py).
# `gh issue create` rejects unknown labels with exit 1, so the labels must
# exist on the repo BEFORE the first anomaly fires — otherwise the worker
# fail-softs silently and you get a Telegram message but no GitHub issue.
#
# Idempotent: re-running with labels already present is a no-op per label.
#
# Usage:
#     scripts/bootstrap-labels.sh                  # gh's default repo
#     scripts/bootstrap-labels.sh OWNER/REPO       # explicit target

set -euo pipefail

REPO_ARG=()
if [[ -n "${1:-}" ]]; then
    REPO_ARG=(--repo "$1")
fi

if ! gh auth status >/dev/null 2>&1; then
    echo "error: gh CLI is not installed or not authenticated." >&2
    echo "       run 'gh auth login' first." >&2
    exit 1
fi

create_label () {
    local name="$1" color="$2" desc="$3"
    if gh label create "$name" --color "$color" --description "$desc" "${REPO_ARG[@]}" >/dev/null 2>&1; then
        echo "+ created: $name"
        return 0
    fi
    # `gh label create` returns 1 both when the label exists and on real
    # failures (auth, network, etc.). Disambiguate with `gh label list`.
    if gh label list "${REPO_ARG[@]}" --json name --jq ".[] | select(.name == \"$name\")" 2>/dev/null | grep -q .; then
        echo "= exists:  $name"
    else
        echo "x failed:  $name (see 'gh label create --help')" >&2
        return 1
    fi
}

create_label "worker-anomaly"      "d73a4a" "Auto-opened by the daily worker"
create_label "status:invalid"      "b60205" "File fetched but failed validation"
create_label "status:missing"      "b60205" "Expected file did not appear upstream"
create_label "status:schema_drift" "fbca04" "File present but header/shape changed"
create_label "status:discovered"   "0e8a16" "Unknown file or directory seen upstream"
create_label "kind:capture"        "1d76db" "Anomaly in a captured (directly-fetched) file"
create_label "kind:mirror"         "1d76db" "Anomaly in a mirrored archive file"
create_label "kind:discovery"      "1d76db" "Anomaly from the discovery phase"

echo
echo "Done. Verify with: gh label list ${REPO_ARG[*]:-}"

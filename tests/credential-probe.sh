#!/usr/bin/env bash
# tests/credential-probe.sh EXPECT
#   Searches everything a caller's command could read, in the job it runs in: its own env,
#   every /proc/<pid>/environ it can read (its parent's included), ~/.docker, $RUNNER_TEMP,
#   and the checkout's .git/config. It looks for the OIDC token-request variables, AWS
#   credential variables, the planted canary, and a GitHub token in .git/config.
#   EXPECT=found: the old layout (the control); exit 0 only if something is found.
#   EXPECT=none:  the verify job's layout; exit 0 only if nothing is found.
# ACTIONS_RUNTIME_TOKEN (artifact upload/download, in every job) is reported, not judged.
set -uo pipefail
expect="${1:?usage: credential-probe.sh found|none}"
pat='ACTIONS_ID_TOKEN_REQUEST_(TOKEN|URL)=|AWS_(SECRET_ACCESS_KEY|SESSION_TOKEN|ACCESS_KEY_ID)=|SBE_CANARY_7f3a'
hits=0
report() { echo "  hit: $1"; hits=$((hits + 1)); }
env | grep -Eq "$pat" && report "own environment"
for f in /proc/[0-9]*/environ; do
  [ -r "$f" ] || continue
  tr '\0' '\n' < "$f" 2>/dev/null | grep -Eq "$pat" && report "$f (pid $(basename "$(dirname "$f")"), parent is $PPID)"
done
for d in "$HOME/.docker" "${RUNNER_TEMP:-/nonexistent}"; do
  [ -d "$d" ] && grep -rEqs "$pat|\"auth\"[[:space:]]*:" "$d" && report "$d"
done
[ -f .git/config ] && grep -Eqi 'extraheader|x-access-token' .git/config && report ".git/config holds a token"
rt=0; for f in /proc/[0-9]*/environ; do [ -r "$f" ] && tr '\0' '\n' < "$f" 2>/dev/null | grep -q '^ACTIONS_RUNTIME_TOKEN=' && rt=$((rt + 1)); done
echo "  (ACTIONS_RUNTIME_TOKEN readable in $rt process environment(s): artifact access, present in every job)"
echo "hits: $hits"
case "$expect" in
  found) [ "$hits" -gt 0 ] || { echo "::error::the control found nothing: the probe cannot see the leak it exists to show"; exit 1; } ;;
  none)  [ "$hits" -eq 0 ] || { echo "::error::a credential is readable from the verify job's layout"; exit 1; } ;;
  *) echo "usage: credential-probe.sh found|none"; exit 2 ;;
esac

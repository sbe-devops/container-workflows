#!/usr/bin/env bash
# tests/input-injection.sh — caller inputs are data, measured on the steps' own bytes.
#
# PROOF (corp 1a99223): image_tag and friends were pasted into run: with ${{ }}, so a valid
# tag like `v1$(…)` ran shell in the job holding the push role. This extracts the real
# steps from the workflows (to files, run by path) and feeds them payloads:
#   I1 docker-release "Check caller inputs" refuses every payload tag, and runs none of it;
#   I2 docker-promote "Check caller inputs" does the same;
#   I3 docker-release "Resolve final image tag" refuses a payload in the extracted version;
#   I4 a plain tag passes all three (the control that they can pass).
#   I5 both checks refuse an ecr_repository_url that isn't an ECR repository URL (it reaches
#      security-actions' sign/attest, which still paste it into run:); real ones pass.
#   I0 CONTROL: the same "Resolve final image tag" as it stood on main @ 0652165, with the
#      expression substituted the way GitHub does, EXECUTES the payload. (Skipped with a
#      notice if that commit isn't in this clone.)
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$here/.."
work="$(mktemp -d "${RUNNER_TEMP:-${TMPDIR:-/tmp}}/inj.XXXXXX")"
trap 'rm -rf -- "$work"' EXIT
fail=0

step() {  # step <workflow> <job> <step name> <out file>
  python3 - "$1" "$2" "$3" "$4" <<'PY'
import sys, yaml
wf, job, name, out = sys.argv[1:]
d = yaml.safe_load(open(wf))
s = [s for s in d["jobs"][job]["steps"] if s.get("name") == name]
assert len(s) == 1, f"{wf}: no single step {name!r} in job {job!r}"
open(out, "w").write(s[0]["run"])
PY
}
step "$root/.github/workflows/docker-release.yml" build "Check caller inputs" "$work/dr-check.sh" || exit 2
step "$root/.github/workflows/docker-promote.yml" promote "Check caller inputs" "$work/dp-check.sh" || exit 2
step "$root/.github/workflows/docker-release.yml" build "Resolve final image tag" "$work/dr-final.sh" || exit 2

# shellcheck disable=SC2016 # the payloads must NOT expand here; that's the point
payloads=('v1$(touch PWNED)' 'v1`touch PWNED`' 'v1;touch PWNED' 'v1 && touch PWNED' '-v1' $'v1\ntouch PWNED' "$(printf 'v%.0s' {1..129})")
cd "$work" || exit 2
export ECR_REPOSITORY_URL=112401921630.dkr.ecr.us-east-1.amazonaws.com/csi-golang/golang1-26
for p in "${payloads[@]}"; do
  for s in dr-check dp-check; do
    rm -f PWNED
    if IMAGE_TAG="$p" bash "$s.sh" >/dev/null 2>&1; then echo "  🔴 $s accepted ${p:0:24}…"; fail=1
    elif [ -e PWNED ]; then echo "  🔴 $s RAN the payload ${p:0:24}…"; fail=1
    else echo "  ✅ $s refused ${p:0:24}"; fi
  done
  rm -f PWNED out
  if SEMVER="$p" IMAGE_TAG=v1.0.0 GITHUB_OUTPUT=out bash dr-final.sh >/dev/null 2>&1 || [ -e PWNED ]; then
    echo "  🔴 dr-final accepted or ran semver ${p:0:24}"; fail=1
  else echo "  ✅ dr-final refused semver ${p:0:24}"; fi
done
for s in dr-check dp-check; do
  if IMAGE_TAG=v1.2.3 bash "$s.sh" >/dev/null 2>&1; then echo "  ✅ $s passes v1.2.3 (control)"; else echo "  🔴 $s refused v1.2.3"; fail=1; fi
done
rm -f out
if SEMVER=3.11.15 IMAGE_TAG=v26.5.0 GITHUB_OUTPUT=out bash dr-final.sh >/dev/null 2>&1 && grep -qx 'image_tag=3.11.15-v26.5.0' out; then
  echo "  ✅ dr-final resolves 3.11.15-v26.5.0 (control)"; else echo "  🔴 dr-final did not resolve 3.11.15-v26.5.0"; fail=1; fi

# shellcheck disable=SC2016 # payloads, deliberately unexpanded
for u in '112401921630.dkr.ecr.us-east-1.amazonaws.com/x$(touch PWNED)' '112401921630.dkr.ecr.us-east-1.amazonaws.com/x;touch PWNED' \
         'evil.example.com/x' '112401921630.dkr.ecr.us-east-1.amazonaws.com/x y' ''; do
  for s in dr-check dp-check; do
    rm -f PWNED
    if ECR_REPOSITORY_URL="$u" IMAGE_TAG=v1.2.3 bash "$s.sh" >/dev/null 2>&1 || [ -e PWNED ]; then echo "  🔴 $s accepted or ran repository ${u:0:40}"; fail=1
    else echo "  ✅ $s refused repository ${u:0:48}"; fi
  done
done
for u in 112401921630.dkr.ecr.us-east-1.amazonaws.com/mcp-engine-qbo-intuit 112401921630.dkr.ecr.us-east-1.amazonaws.com/csi-amazonlinux/amazonlinux-minimal; do
  for s in dr-check dp-check; do
    if ECR_REPOSITORY_URL="$u" IMAGE_TAG=v1.2.3 bash "$s.sh" >/dev/null 2>&1; then echo "  ✅ $s passes ${u#*/} (control)"; else echo "  🔴 $s refused ${u#*/}"; fail=1; fi
  done
done

# I0: the old step, substituted as GitHub substitutes ${{ }}, runs the payload.
if git -C "$root" cat-file -e 0652165:.github/workflows/docker-release.yml 2>/dev/null; then
  git -C "$root" show 0652165:.github/workflows/docker-release.yml > old.yml
  step old.yml build "Resolve final image tag" old-final.tpl
  python3 - <<'PY'
t = open("old-final.tpl").read()
t = t.replace("${{ steps.runtime_version.outputs.semver }}", "").replace("${{ inputs.image_tag }}", "v1$(touch PWNED)")
open("old-final.sh", "w").write(t)
PY
  rm -f PWNED; GITHUB_OUTPUT=out bash old-final.sh >/dev/null 2>&1
  if [ -e PWNED ]; then echo "  ✅ CONTROL: main @ 0652165's step ran the payload (the defect is real)"
  else echo "  🔴 CONTROL: the old step did not run the payload; this test proves nothing"; fail=1; fi
else
  echo "  (control skipped: 0652165 not in this clone)"
fi
[ $fail -eq 0 ] || { echo "🔴 input-injection: FAILED"; exit 1; }
echo "input-injection: passed"

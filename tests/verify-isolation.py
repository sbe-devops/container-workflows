#!/usr/bin/env python3
"""docker-release.yml: the caller's verify_command runs where no credential is.

PROOF on #22: a child process reads its parent's /proc/<pid>/environ, so stripping variables
from the command's own environment hides nothing while the job holds the AWS session and the
OIDC token-request pair. The fix is structural, and this checks the structure:
  V1 the `verify` job's permissions are exactly {contents: read} (no id-token);
  V2 it has no AWS step, no registry login, and its checkout persists no token;
  V3 no other job's step runs inputs.verify_command;
  V4 `push` needs `verify`, and the build job's push steps are off when verify_command is set;
  V5 `push` binds to the tested manifest before signing.
Then each property is broken in a copy, and each break must be caught.

Run: python3 tests/verify-isolation.py
"""
import copy
import sys
from pathlib import Path

import yaml

WF = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "docker-release.yml"
FORBIDDEN_USES = ("aws-actions/", "docker/login-action")


def steps(job):
    return job.get("steps") or []


def problems(doc):
    jobs = doc.get("jobs") or {}
    out = []
    v = jobs.get("verify")
    if not v:
        return ["no `verify` job"]
    if v.get("permissions") != {"contents": "read"}:
        out.append(f"V1 verify permissions are {v.get('permissions')!r}, not exactly contents: read")
    for s in steps(v):
        u = str(s.get("uses", ""))
        if u.startswith(FORBIDDEN_USES):
            out.append(f"V2 verify uses {u}")
        if u.startswith("actions/checkout@") and (s.get("with") or {}).get("persist-credentials") is not False:
            out.append("V2 verify's checkout persists its token")
        if "ecr" in str(s.get("run", "")).lower() and "login" in str(s.get("run", "")).lower():
            out.append("V2 verify logs in to a registry")
    for name, job in jobs.items():
        if name == "verify":
            continue
        for s in steps(job):
            if "inputs.verify_command" in str((s.get("env") or {})) or "VERIFY_COMMAND" in str(s.get("run", "")):
                out.append(f"V3 job {name!r} step {s.get('name')!r} runs the verify command")
    p = jobs.get("push") or {}
    if "verify" not in (p.get("needs") or []):
        out.append("V4 push does not need verify")
    for s in steps(jobs.get("build") or {}):
        if s.get("id") == "push" and "inputs.verify_command == ''" not in str(s.get("if", "")):
            out.append("V4 the build job pushes even with a verify_command")
    names = [s.get("name") for s in steps(p)]
    if "The pushed image is the tested image" not in names or "Sign image" not in names \
            or names.index("The pushed image is the tested image") > names.index("Sign image"):
        out.append("V5 push does not bind to the tested manifest before signing")
    return out


def main():
    doc = yaml.safe_load(WF.read_text())
    bad = problems(doc)
    if bad:
        print("\n".join("  🔴 " + b for b in bad))
        return 1
    print("  ✅ V1-V5 hold on docker-release.yml")

    def m_idtoken(d): d["jobs"]["verify"]["permissions"]["id-token"] = "write"
    def m_aws(d): d["jobs"]["verify"]["steps"].insert(0, {"uses": "aws-actions/configure-aws-credentials@x"})
    def m_persist(d):
        for s in d["jobs"]["verify"]["steps"]:
            if str(s.get("uses", "")).startswith("actions/checkout@"):
                s["with"] = {}
    def m_inbuild(d): d["jobs"]["build"]["steps"].append({"name": "x", "env": {"C": "${{ inputs.verify_command }}"}, "run": 'bash -c "$VERIFY_COMMAND"'})
    def m_needs(d): d["jobs"]["push"]["needs"] = ["build"]
    def m_buildpush(d):
        for s in d["jobs"]["build"]["steps"]:
            if s.get("id") == "push":
                s["if"] = "inputs.push"
    def m_bindafter(d):
        st = d["jobs"]["push"]["steps"]
        i = next(k for k, s in enumerate(st) if s.get("name") == "The pushed image is the tested image")
        st.append(st.pop(i))
    fail = 0
    for label, f in [("verify gets id-token", m_idtoken), ("verify gets an AWS step", m_aws),
                     ("verify checkout persists its token", m_persist), ("build runs the command", m_inbuild),
                     ("push stops needing verify", m_needs), ("build pushes despite verify", m_buildpush),
                     ("bind moved after sign", m_bindafter)]:
        d = copy.deepcopy(doc)
        f(d)
        if problems(d):
            print(f"  ✅ mutant caught: {label}")
        else:
            print(f"  🔴 mutant SURVIVED: {label}")
            fail = 1
    return fail


if __name__ == "__main__":
    sys.exit(main())

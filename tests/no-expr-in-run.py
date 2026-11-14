#!/usr/bin/env python3
"""No `${{ }}` expression inside any `run:` block, in any workflow in this repo.

An expression in `run:` is substituted into the script's SOURCE before bash sees it, so a
caller-controlled value (an input, an event field, a step or job output) becomes code: a
valid tag such as `v1$(curl …)` runs in the job that holds the push role (PROOF, corp
1a99223). Every value reaches a script through `env:` and is used as "$VAR".

This is stricter than "no inputs.* / github.event.* / steps.*.outputs.*": ANY expression in
`run:` is refused, so a new context can't slip past a list.

Run:  python3 tests/no-expr-in-run.py [workflow.yml ...]   (default: .github/workflows/*.yml)
"""
import re
import sys
from pathlib import Path

import yaml

EXPR = re.compile(r"\$\{\{(.*?)\}\}", re.S)


def findings(path):
    doc = yaml.safe_load(Path(path).read_text()) or {}
    out = []
    for jname, job in (doc.get("jobs") or {}).items():
        for i, step in enumerate(job.get("steps") or []):
            run = step.get("run")
            if not isinstance(run, str):
                continue
            for m in EXPR.finditer(run):
                out.append((jname, step.get("name") or f"step {i}", m.group(1).strip()))
    return out


def main(argv):
    root = Path(__file__).resolve().parent.parent / ".github" / "workflows"
    files = [Path(a) for a in argv] or sorted(root.glob("*.yml"))
    total = 0
    for f in files:
        fs = findings(f)
        total += len(fs)
        for j, s, e in fs:
            print(f"  🔴 {f.name}: job {j!r}, step {s!r}: ${{{{ {e} }}}} inside run:")
    if total:
        print(f"{total} expression(s) inside run: across {len(files)} workflow(s). Pass each through env: and use \"$VAR\".")
        return 1
    print(f"✓ no expression inside any run: block ({len(files)} workflow(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

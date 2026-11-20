#!/usr/bin/env python3
"""tests/pins.py — every `uses:` in .github/ is pinned to something that cannot move.

Allowed:
  ./local/path                                   this repo, at the caller's commit
  sbe-devops/<repo>[/path]@vX.Y.Z                SBE's own, whose v* tags the org ruleset
                                                 `org-release-tags-immutable` forbids moving
  <owner>/<repo>[/path]@<40 hex> # vX.Y.Z        anyone else's, by commit, with the version named

Refused: a floating tag (`@v6`), a branch, a short SHA, a SHA with no version comment, and an
SBE ref that isn't an exact release tag.

Self-test: `--self-test` runs the matcher on fixed good and bad lines, so a matcher that
accepts everything fails here instead of passing CI.
"""
from __future__ import annotations

import pathlib
import re
import sys

USES = re.compile(r"^\s*(?:-\s+)?uses:\s*(\S+)(.*)$")
OK = [
    re.compile(r"^\./\S+$"),
    re.compile(r"^sbe-devops/[A-Za-z0-9_.-]+(/[A-Za-z0-9_./-]+)?@v\d+\.\d+\.\d+$"),
]
THIRD = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(/[A-Za-z0-9_./-]+)?@[0-9a-f]{40}$")
VERSION_COMMENT = re.compile(r"^\s+#\s+v\d+\.\d+\.\d+\b")


def bad(ref: str, rest: str) -> str | None:
    if any(p.match(ref) for p in OK):
        return None
    if THIRD.match(ref):
        if ref.startswith("sbe-devops/"):
            return "SBE's own actions pin an exact release tag, not a SHA"
        return None if VERSION_COMMENT.match(rest) else "a SHA pin needs a `# vX.Y.Z` comment"
    return "not pinned to a commit (third-party) or an exact release tag (sbe-devops)"


def self_test() -> int:
    good = [
        "      - uses: ./.github/actions/x",
        "        uses: sbe-devops/security-actions/.github/actions/scan@v0.4.1",
        "        uses: sbe-devops/gh-setup-crane@v0.1.0",
        "        uses: aws-actions/amazon-ecr-login@7290e214a610b32bc0eef81748948b6d466a8783 # v2.2.0",
        "      - uses: release-drafter/release-drafter/autolabeler@d1a19e60e81a7e650d00a7de9277f87e439117ea # v7.11.0",
    ]
    badl = [
        "        uses: actions/checkout@v6",
        "        uses: actions/checkout@main",
        "        uses: actions/checkout@d23441a",
        "        uses: actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803",
        "        uses: actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803 # latest",
        "        uses: sbe-devops/security-actions/.github/actions/scan@v0",
        "        uses: sbe-devops/security-actions/.github/actions/scan@main",
        "        uses: sbe-devops/gh-setup-crane@d23441a48e516b6c34aea4fa41551a30e30af803 # v0.1.0",
        "        uses: docker://alpine:3",
    ]
    wrong = 0
    for line, want in [(g, False) for g in good] + [(b, True) for b in badl]:
        m = USES.match(line)
        got = m is not None and bad(m.group(1), m.group(2)) is not None
        if got != want:
            wrong += 1
            print(f"🔴 self-test: {'accepted' if want else 'refused'} {line.strip()}")
    n = len(good) + len(badl)
    print(f"pins self-test: {n - wrong}/{n} lines decided as expected")
    return 1 if wrong else 0


def main(argv: list[str]) -> int:
    if argv == ["--self-test"]:
        return self_test()
    root = pathlib.Path(argv[0] if argv else ".")
    files = sorted(p for p in (root / ".github").rglob("*") if p.suffix in (".yml", ".yaml"))
    found = checked = 0
    for f in files:
        for i, line in enumerate(f.read_text().splitlines(), 1):
            m = USES.match(line)
            if not m:
                continue
            checked += 1
            why = bad(m.group(1), m.group(2))
            if why:
                found += 1
                print(f"::error file={f.relative_to(root)},line={i}::{m.group(1)}: {why}")
    if checked == 0:
        print("::error::read no `uses:` at all; the scan is broken")
        return 1
    if found:
        print(f"{found} unpinned `uses:` of {checked}")
        return 1
    print(f"✓ all {checked} `uses:` pinned ({len(files)} file(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

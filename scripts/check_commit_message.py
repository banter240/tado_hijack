#!/usr/bin/env python3
"""Validate commit messages against the conventional-commit rules.

Runs at the commit-msg stage; pre-commit passes the message file as
the first argument. The checks mirror what semantic-release actually
parses: an unknown header type silently skips the release bump, and
mid-body trailer lines silently truncate the release notes because the
template prints header and body only. The '!' marker is rejected
because this pipeline maps it to a minor bump — major releases need
the explicit uppercase BREAKING CHANGE footer.

Pure standard library.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

TYPES = (
    "feat",
    "fix",
    "perf",
    "revert",
    "docs",
    "style",
    "chore",
    "refactor",
    "test",
    "build",
    "ci",
)
HEADER_RE = re.compile(rf"^({'|'.join(TYPES)})(\([a-z0-9_./-]+\))?(!)?: (.+)$")
TRAILER_RE = re.compile(
    r"^(BREAKING CHANGE|Fixes |Closes |Resolves |Co-authored-by: )",
    re.IGNORECASE,
)
SUBJECT_MAX = 72
LINE_MAX = 100


def strip_comments(text: str) -> str:
    """Drop the git help block (lines starting with '#')."""
    return "\n".join(line for line in text.splitlines() if not line.startswith("#"))


def check(message: str) -> list[str]:
    """Return a list of rule violations for one commit message."""
    errors: list[str] = []
    if not message.strip():
        return ["empty commit message"]

    header, _, rest = message.partition("\n")
    # Merge/revert and git's fixup!/squash! helpers carry no conventional
    # header by design.
    if header.startswith(("Merge ", 'Revert "', "fixup! ", "squash! ")):
        return []

    match = HEADER_RE.match(header)
    if match is None:
        hinted = re.match(r"^([a-z]+)(?:\(.*\))?!?: ", header)
        if hinted and hinted[1] not in TYPES:
            errors.append(f"unknown type '{hinted[1]}', allowed: {', '.join(TYPES)}")
        else:
            errors.append(f"header must match 'type(scope): subject', got: {header!r}")
        return errors

    if match.group(3):
        errors.append(
            "'!' maps to a minor bump in this pipeline, use an explicit "
            "'BREAKING CHANGE:' footer for major releases"
        )

    subject = match.group(4)
    if len(subject) > SUBJECT_MAX:
        errors.append(f"subject exceeds {SUBJECT_MAX} chars ({len(subject)})")
    if subject.endswith("."):
        errors.append("subject should not end with a period")

    paragraphs = [p for p in re.split(r"\n\s*\n", rest) if p.strip()]
    for paragraph in paragraphs[:-1]:
        errors.extend(
            f"trailer outside the footer block: {line.strip()!r}; trailers belong in the last paragraph"
            for line in paragraph.splitlines()
            if TRAILER_RE.match(line)
        )
    if paragraphs:
        for line in paragraphs[-1].splitlines():
            is_bc = re.match(r"(?i)^breaking change\b", line)
            if is_bc and not line.startswith("BREAKING CHANGE"):
                errors.append("bump footers must be upper-case 'BREAKING CHANGE'")

    errors.extend(
        f"line exceeds {LINE_MAX} chars: {line[:40]!r}"
        for line in message.splitlines()
        if len(line) > LINE_MAX
    )
    return errors


def main() -> int:
    """Check the message file passed by the commit-msg hook."""
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".git") / "COMMIT_EDITMSG"
    errors = check(strip_comments(path.read_text()))
    for error in errors:
        sys.stderr.write(f"commit message: {error}\n")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())

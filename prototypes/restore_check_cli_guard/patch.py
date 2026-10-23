"""Produce a guarded temporary copy of a historical Yuva CLI source file."""

from __future__ import annotations


PARSE_MARKER = b"    a = p.parse_args()\n"
GUARD = b'''    if (getattr(a, "cmd", None) == "gorev"
            and any(parent.name.startswith("restore-check.")
                    for parent in Path(__file__).resolve().parents)):
        print("restore-check CLI is inspection-only; task mutations disabled",
              file=sys.stderr)
        raise SystemExit(2)
'''


def guarded_source(source: bytes) -> bytes:
    """Insert a restore-check-path task-command denial into a CLI source copy.

    Only the single historical ``main()`` parse marker is accepted. Callers
    should write this result into a disposable fixture or explicit maintenance
    staging area, never over a backup archive source.
    """
    if source.count(PARSE_MARKER) != 1 or b"from pathlib import Path" not in source:
        raise ValueError("unrecognized historical CLI source")
    return source.replace(PARSE_MARKER, PARSE_MARKER + GUARD, 1)

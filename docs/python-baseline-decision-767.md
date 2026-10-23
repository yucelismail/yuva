# Python minimum-version decision note (#767)

**Selected policy: Python 3.8+ (maintainer choice in #768).** This note records
the decision and the runtime evidence still required to validate it.

## Current repository state

- README says Linux and Python 3.8+; the CLI and panel use the standard
  library only.
- No `pyproject.toml`, `setup.py`, `setup.cfg`, `tox.ini`, requirements file,
  or `Requires-Python` metadata exists. There is no published package metadata
  to align today.
- Before #768, Actions ran the syntax scanner under Python 3.8 and the
  unittest suite under Python 3.12. That was not a runtime test of Python 3.8.
- The #738 audit found `str.removeprefix()` in
  `tests/test_release_manifest.py`, which was added in Python 3.9. Therefore
  the full test suite does not currently meet the README's 3.8+ claim.
- As of 2026-10-23, Python's Developer Guide lists 3.10 as end-of-life and
  3.11 as the oldest upstream-supported series; 3.11 is in security support
  through 2027-10. Python 3.15.1 is the latest stable release ([version
  status](https://devguide.python.org/versions/), [3.15.1 release](https://www.python.org/downloads/release/python-3151/)).

## Options

| Policy | Benefits | Costs and required work |
|---|---|---|
| Keep Python 3.8+ | Preserves the documented compatibility promise and supports older system interpreters. | 3.8 is upstream EOL. Replace the 3.9-only test call, run the full suite on real Python 3.8, then add 3.8 and current stable (3.15) to runtime CI. The project would own compatibility/security backports for EOL Python. |
| Adopt upstream-supported minimum 3.11+ | Aligns the minimum with active upstream security support and removes unsupported-version maintenance. | Explicitly drops 3.8–3.10. Update README, set syntax validation to 3.11, and run the suite on 3.11 plus current stable (3.15). Since CI currently has one stable `unittest` check, preserve that check with an aggregate gate if matrix expansion changes its name; then reconcile the branch-protection runbook and observed Actions check. |

## Decision and verification sequence

The initial security-maintenance recommendation was **3.11+**, but the
maintainer chose continuity of the documented 3.8+ support range. Python 3.8
is therefore the minimum runtime target; until its full suite passes in CI,
the claim is selected but not yet validated.

Validation record for #768:

- The existing README already states Python 3.8+, so its support range remains
  unchanged. If package metadata is introduced later, set `Requires-Python` to
  the same minimum.
- `.github/workflows/ci.yml` now runs the full test suite on Python 3.8 and
  Python 3.15 in the existing `unittest` job. The Python 3.8-only
  `str.removeprefix()` use in `tests/test_release_manifest.py` was replaced by
  slicing.
- The focused local tests and syntax scan pass, but this checkout has no Python
  3.8 interpreter. The exact Python 3.8 runtime result is pending a GitHub
  Actions run; support is not claimed as runtime-validated until that run
  passes.
- The check identity remains `unittest`; the #735 runbook now describes the
  added runtime steps. No repository settings or remote workflow run were
  changed or triggered.

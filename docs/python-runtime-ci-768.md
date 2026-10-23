# Python runtime CI for the selected 3.8+ baseline (#768)

The maintainer selected Python 3.8+ in #768. CI now keeps the existing single
`unittest` status check and runs the complete test runner on Python 3.8 and
Python 3.15. The syntax scan also runs on Python 3.8. Keeping both runtime
steps in the same job means the required status check remains `unittest`.

The 3.8-only `str.removeprefix()` call in `tests/test_release_manifest.py` was
replaced with slicing so test discovery and execution do not require Python
3.9 APIs.

## Verification

- Local interpreter: Python 3.14.4.
- `tests.test_release_manifest` and `tests.test_ci_checkout_credentials`:
  18 tests passed locally.
- `scripts/check_python_syntax.py`: 132 source files passed locally.
- `git diff --check`: passed.
- This host does not have Python 3.8 or 3.15 installed. The full suite's
  Python 3.8 and 3.15 runtime results are therefore pending the next GitHub
  Actions run. The local results do not establish compatibility on either
  configured endpoint.

No remote run was triggered. Once Actions runs, record its exact interpreter
versions, test counts, and exit codes here before treating the 3.8+ support
claim as runtime-verified.

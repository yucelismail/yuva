## Test and CI evidence

- [ ] Tests changed or added use disposable fixture roots (such as
  `TemporaryDirectory`) and fixture-only endpoints. No live Yuva data, panel, or
  host service was used. Select N/A if the change does not add or run tests.

Local test command:

```text
PYTHONDONTWRITEBYTECODE=1 python scripts/run_tests.py
```

Result: `Pending` / `Passed` / `Failed` / `Not run` / `N/A`

CI run URL: `Paste the GitHub Actions run link`

Commit SHA checked: `Paste the commit SHA shown by that run`

CI status: `Pending` / `Passed` / `Failed` / `Not run`

Verify the linked run reports the result for the commit SHA above. A pending,
missing, or older run is not a passing result. Local test and CI results are
evidence for review; they do not approve or merge the PR automatically.

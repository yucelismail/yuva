# CI unittest failure propagation (#748)

The workflow has a single `run` command for the test step:
`PYTHONDONTWRITEBYTECODE=1 python scripts/run_tests.py`. It has no command
pipeline or chained command, `|| true`, `continue-on-error`, `set +e`, or
always-run condition that could turn a failing suite into a successful job.
No custom shell is specified; on `ubuntu-latest`, GitHub Actions uses
`bash -e` for a non-Windows `run` step when no shell is set. Its documented
fail-fast behavior propagates a nonzero command exit to the step result
([GitHub workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax)).

The runner returns status `1` when `TextTestRunner` reports a failed/error
suite, status `2` for discovery failure or zero discovered tests, and passes
that status to the process via `sys.exit(main())`. A synthetic failing suite
was run through `main(start_dir=...)`; it returned status `1`. The runner
finishes the suite, reports failures, then makes the workflow's sole command
exit nonzero, so the step/job fails.

No workflow or runner changes were needed. This was a static workflow review
and disposable synthetic failure check; the full suite and GitHub Actions job
were not run.

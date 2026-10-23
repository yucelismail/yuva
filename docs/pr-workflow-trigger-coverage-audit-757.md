# Pull request workflow trigger coverage (#757)

`.github/workflows/ci.yml` declares `pull_request:` without branch, path, or
activity-type filters. Its single `unittest` job has no job-level or step-level
`if` condition. The syntax check and full unittest suite therefore run for
pull requests regardless of whether changes are in documentation, workflows,
tests, or application code. The workflow has no `paths`, `paths-ignore`, or
skip condition that could leave the required `unittest` check unreported for a
file-category-only change.

The same workflow also runs on pushes to `main`; this separate push branch
filter does not narrow the `pull_request` trigger. GitHub documents that path
and branch filters constrain runs when configured and that skipped required
checks can remain pending ([triggering a workflow](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow)).

This was a static workflow audit. No live pull request, repository setting,
branch rule, or workflow run was changed or created.

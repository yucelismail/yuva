# CI checkout credential persistence (#766)

`.github/workflows/ci.yml` now sets `persist-credentials: false` on its pinned
`actions/checkout` step. The job's later steps configure Python, run the source
syntax checker, and run the unittest suite; none invokes authenticated Git.
The checkout action pin, event permissions, and repository settings were not
changed.

`tests/test_ci_checkout_credentials.py` statically requires the explicit
`false` setting and guards the current post-checkout job from adding an
authenticated Git command without review. The targeted regression tests passed
2/2. This is a workflow source check, not a GitHub Actions run or a repository
settings verification.

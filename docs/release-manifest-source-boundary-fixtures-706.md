# Release manifest source-boundary fixtures (#706)

## Scope

Added adversarial Git source and payload cases to `tests/test_release_manifest.py`. Every repository, submodule, archive and payload is created inside a disposable temporary directory. The real repository index, branch, release tree and host are not touched.

## Results

| Case | Evidence |
|---|---|
| Gitlink with initialized nested submodule | Clean nested checkout is reported `pinned_clean`, but `git ls-tree` gitlink rejection keeps payload matching and release eligibility false; verifier fails closed. |
| Dirty nested submodule | Changing a file inside the initialized nested submodule makes source state `dirty`; generated manifest stays ineligible. |
| `export-ignore` asset omitted by `git archive` | Source remains clean, but tracked-tree/payload set mismatch yields `payload_matches_source=false`, `source_match=false`, and no eligible release. |
| Ignored extra payload file | Git source can remain clean, but payload/tree mismatch prevents eligibility. |
| Untracked extra payload file | Source is dirty and payload/tree mismatch prevents eligibility. |
| Missing required asset | Manifest generation and verification both raise `ManifestError`; no eligible result is produced. |

## Verification

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_release_manifest -v
```

Result: 13 tests passed. Manifest digests generated inside a fixture are used only to exercise the verifier's digest-matching path; they are not independent trust anchors or production pins.

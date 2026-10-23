# Staging inventory uncertainty stays HOLD (#728)

## Scope

Added temporary-root regressions in `tests/test_release_staging_inventory.py` for the #647/#681 inventory contract. The tests exercise only disposable directories; no installed release, host `INSTALL_ROOT`, service, pointer, or live data was used.

## Coverage matrix

| Case | Fixture result |
|---|---|
| `max_entries=2` with excess unknown entries | Listing is marked `truncated`, unknown count is positive, unknown names are omitted, the tree is unchanged, and `decision` is `HOLD`. |
| Child directory replaced between metadata lookup and open | Opened directory inode/device differs from the prior metadata snapshot; report state is `changed_during_scan`, no outside release is included, FD count is unchanged, and decision is `HOLD`. |
| Missing manifest receipt | Receipt state is `missing`; classification is `PUBLISHED_RECEIPT_INCOMPLETE`; decision stays `HOLD`. |
| Manifest with unsafe mode or symlink | Receipt state is `unsafe_metadata`; classification is `HOLD_UNKNOWN`; manifest target/content is not read or disclosed; tree is unchanged. |

The existing suite also covers an over-limit listing, unknown-name redaction, unsafe pointer targets, symlinked staging entries, and stable cleanup on injected `fstat`, second child-open, and `close` errors.

## Verification

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_release_staging_inventory -v
```

Result: 13 tests passed. The inventory remains observational: no branch authorizes cleanup, publish, resume, or current-pointer mutation. Truncated or uncertain state remains `HOLD`.

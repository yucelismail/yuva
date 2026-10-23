# Release manifest tampering and canonical bytes (#707)

## Scope

Expanded `tests.test_release_manifest` with disposable source repositories and payloads. The checks mutate source, payload and manifest state only inside each temporary fixture. Hashes generated from fixture bytes are test inputs, not independent trust anchors or production pins.

## Results matrix

| Mutation | Fail-closed evidence |
|---|---|
| Source content differs from the committed tree | `source_match=false`, `verified_release=false`. The earlier fixture also covers untracked source state. |
| Payload file set has an extra file | `payload_match=false`, `verified_release=false`. |
| Payload mode differs from the manifest | `payload_match=false`, `verified_release=false`. |
| Payload content differs from the manifest/source | `payload_match=false`, `verified_release=false`. |
| Manifest file order is reversed | `ManifestError` for noncanonical path order. |
| Manifest bytes gain trailing whitespace | `ManifestError` for noncanonical serialization before digest trust is considered. |
| Manifest file set gains a canonically ordered record with internally recomputed payload digest and release ID | Verifier returns `payload_match=false` and `verified_release=false`, even with a fixture-local SHA-256 matching those bytes. |

## Verification

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_release_manifest -v
```

Result: 15 tests passed. The internal digest in the self-consistent manifest mutation only exercises consistency checks; it does not establish independent authenticity.

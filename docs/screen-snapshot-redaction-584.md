# Historical screen snapshot redaction prototype (#584)

**Date:** 2026-10-23
**Status:** Fixture-only prototype and focused tests complete; submitted for review.
**Boundary:** No live `YUVA_DIR`, historical screen JSONL, backup, panel process, or service was read or changed. The projection is not connected to `panel/server.py` and is not a production control.

## Prototype behavior

`prototypes/screen-snapshot-redaction/project_fixture.py` projects only a marked, private fixture tree under the system temp directory. It does not read `YUVA_DIR`. It reads direct `ekran/*.jsonl` fixture files read-only and requires a private marker, private directories, owner-only regular files, one link, safe identity filenames, and bounded file/row/record sizes. It rejects paths outside the fixture contract before reading records.

Both policies call the shared `yuva_screen_redaction.redact_screen_record()` implementation used by the panel and CLI writers:

| Policy | Snapshot result | Use and tradeoff |
|---|---|---|
| `redact` | Return rows after the shared redactor masks recognized credential forms. | Retains useful benign context, but the regex rules are not complete DLP. |
| `reject` | If a row would change under the redactor, omit its entire file from the snapshot. | Stronger content minimization, but removes benign rows from that file too. |

In either mode, malformed JSON, duplicate object keys, invalid schema/field values, oversized rows, encoding errors, or redactor failures reject the whole file. The output contains only constant reason codes and counts; exception text, path, source row, and credential values are not emitted. The input JSONL is never rewritten. The prototype logs only policy and aggregate counts.

## Fixture evidence

`tests/test_screen_snapshot_redaction.py` uses only a `TemporaryDirectory` fixture and synthetic marker values. Three tests cover:

1. `redact`: benign text remains, a synthetic bearer value is absent from serialized snapshot/API output, the projected screen map used as UI input, and captured logs; source bytes remain identical.
2. `reject`: a file containing a recognized credential is omitted as a whole; raw value is absent from output/logs and source bytes remain identical.
3. Malformed record: the entire file is omitted with a constant reason; the raw sentinel is absent from output/logs and the malformed source bytes remain identical.

Run: `python3 -m unittest tests.test_screen_snapshot_redaction -v` — **3 tests passed**.

The API/UI assertions serialize the isolated projection as sinks; they do not call a running HTTP route or browser. The test proves behavior for these synthetic inputs only.

## Limits and decision

This is a read-time prototype, not a migration or a durable cleanup. It does not alter the historical JSONL, backup, export, CLI reader, live panel, or UI. Returning redacted text does not revoke a credential already present in source history; a discovered real credential still requires the separate owner-approved revoke/rotation response. Known-pattern redaction cannot establish that arbitrary content is secret-free. Integrating either policy into a real snapshot requires a separate product decision about file-level omission, partial UI behavior, and access control.

Related decisions: `docs/screen-jsonl-offline-migration-579.md`, `docs/screen-secret-redaction-564.md`, `docs/screen-secret-redaction-rotation-559.md`, and `docs/jsonl-redaction-policy-adr-465.md`.

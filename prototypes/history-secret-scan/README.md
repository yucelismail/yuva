# Fixture-only historical chat/screen secret-pattern scan

`scanner.py` is a read-only offline prototype. It accepts only a marked,
owner-private fixture below the system temporary directory; it has no default
data root, backup discovery, recursive traversal, or live Yuva integration.
The fixture layout is one `mesaj.jsonl` plus a direct `ekran/` directory with
screen JSONL files. The root must contain the exact private marker described in
the task report: `.yuva-history-secret-scan-fixture` with bytes
`yuva-history-secret-scan-fixture-v1\n` (the final byte is LF). The root and
`ekran/` directory must be owned by the current user and private (mode `0700`);
the marker and each JSONL file must be owner-only regular files (mode `0600`,
one hard link). The only root entries are the marker, `mesaj.jsonl`, and
`ekran/`. A missing chat file or any unexpected entry makes the report partial.

The scanner checks chat `metin`/optional `ad` fields and screen `ad`/`satir`
fields with the existing shared screen redactor. It prints only aggregate file,
record, and changed-field counts plus fixed reason codes. It does not print
paths, row contents, matched values, hashes, regex fragments, or exceptions.
Malformed, oversized, changing, unsafe, or unsupported input makes the result
partial/rejected; it is never summarized as clean.

Run only against an explicitly constructed synthetic fixture:

```sh
python3 prototypes/history-secret-scan/scanner.py --fixture-root /tmp/<marked-fixture>
```

`no_known_pattern_detected` means only that the existing known-pattern rules
found no match in the scanned fields. It is not a DLP guarantee, does not mean
the full records are secret-free, and does not justify deletion. If a real
credential is suspected, do not point this prototype at live history or
backups; follow the owner-approved exposure, revoke/rotate, hold, and copy
inventory process. A match count does not identify or revoke a credential.

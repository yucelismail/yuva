# Fixture-only ekran JSONL migration prototype

`migrate_fixture.py` is an offline, one-file prototype for applying the shared
`yuva_screen_redaction.redact_screen_record()` contract to historical screen
records. It has no default data root, no backup discovery, and no recursive
scan. The resolved root must be a private directory below the system temporary
directory, contain the exact `.yuva-screen-migration-fixture` marker, and have
a direct private `ekran/` child. Pass one direct `*.jsonl` basename.

For each file it holds the fixture's stable `.kilit` across complete read,
parse, redaction, metadata copy, temp write, file `fsync`, same-directory
`os.replace`, and directory `fsync`. Invalid/partial/duplicate-key records,
unsafe file types/permissions, unknown record shape, and unsupported metadata
fail closed. It preserves row count, JSON fields, line ending style, owner,
group, permission bits, timestamps and extended attributes where the host
permits. The inode and ctime necessarily change after replacement. No-change
input skips replacement, making a second run byte/inode/mtime stable.

Output contains only a status code, original device/inode file identity, row
count, and count of fields changed by the redactor. It never includes file
paths, record contents, credential values, exception strings, or hashes of
secret-bearing content. `commit_unknown` after rename/directory-fsync failure
is not retried automatically.

This is not an installed migration command and must not be pointed at
`YUVA_DIR`, backups, or live data. Tests create synthetic records only under
`TemporaryDirectory`. If future offline review discovers a real credential in
an old record, masking does not revoke it: stop before opening/re-writing the
source with `--credential-exposure-reported`, then follow the credential
owner's rotation/revocation process. The flag accepts no credential value and
returns only `credential_exposure_requires_rotation`. This prototype neither
discovers nor edits backup/export/restore copies; atomic replace is not a
rollback plan, and restoring an older raw copy could reintroduce the exposure.
Treat all such copies separately under the owner-controlled incident/retention
process. An `unchanged` result means only that this redactor found no supported
pattern; it is not a clean-history guarantee.

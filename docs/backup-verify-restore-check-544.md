# Backup verifier and restore-check (#544)

`backup_verify.py` is a standalone, standard-library-only tool for the plain,
uncompressed GNU tar format documented in `linux-gecis.md`. It does not open a
live backup by itself; provide an archive path explicitly.

## Read-only verification

```sh
python3 backup_verify.py verify --archive /path/to/yuva-YYYYMMDD.tar
```

An optional independently recorded digest can be supplied to both `verify`
and `restore-check` with `--expected-sha256 <64-lowercase-hex>`. A mismatch
fails verification and prevents restore-check before it creates the scratch
destination. The tool cannot prove where the caller obtained that digest;
`authenticity` therefore remains `unverified`. See
[`docs/backup-expected-digest-cli-616.md`](backup-expected-digest-cli-616.md).

The adjacent files must be named `<archive>.sha256` and `<archive>.list`.
Verification checks that the archive is a regular file owned by the effective
user with mode `0600`, checks that the sidecars are regular files owned by the
effective user and not group/other writable, compares the adjacent SHA-256
record with the archive, and parses the tar member table without extraction.
Sidecar files may be group/other readable, but the report warns about that.
Archive and sidecars inside the active data root are refused. The root defaults
to `YUVA_DIR`, or `~/yuva` if that variable is unset; an alternate root can be
passed with `--active-data-root`.

The verifier accepts a single top-level directory containing regular files
and directories. It rejects absolute/traversing or duplicate paths, links,
special files, special permission bits, and malformed/uncompressed-tar input.
It reports the listing sidecar's size and digest but does not compare its text
to tar output. A matching adjacent checksum is only local consistency evidence:
the report labels authenticity `unverified` because the checksum is not an
independent trust anchor.

## Scratch restore-check

The scratch root must already exist, be a real directory owned by the effective
user with mode `0700`, and be outside the active data root. The destination
name is one path component. Restore-check refuses an existing destination and
creates a new one; it never targets or overwrites active `YUVA_DIR`.

```sh
mkdir -m 700 /path/to/private-scratch
python3 backup_verify.py restore-check \
  --archive /path/to/yuva-YYYYMMDD.tar \
  --scratch-root /path/to/private-scratch \
  --destination-name restore-check-01
```

The command verifies the archive before extracting regular files and
directories to that new destination, then checks the restored `durum.json`,
`gorevler.json`, `mesaj.jsonl`, and `ekran/*.jsonl` when present. State/task
JSON files are optional to support partial data roots. JSONL records must be
UTF-8 JSON objects, one per line. ACLs and xattrs are not restored by this
tool; its output explicitly reports `acl_xattr_restore: not_performed`. To
bound scratch disk use, restore-check refuses an archive whose declared
unpacked regular-file total exceeds 256 MiB or whose largest single member
exceeds 64 MiB. It checks these limits from the tar member table before
creating the destination. The read-only verify output includes the measured
sizes and limit result. On an error after extraction starts, the partial
scratch destination is retained for inspection and must be removed by its
operator.

Because older archived `bin/yuva` copies may write an empty default over a
broken task ledger, restore-check replaces `bin/yuva` **in the extracted
scratch tree only** with a fixed exit-2 stub and reports
`restore_cli_policy: task_mutations_disabled`. This scratch tree is for data
inspection and is not a runnable restored release. The archive and existing
restore-check source copies are not changed; their original bytes remain
covered by the archive digest. See
[`docs/restore-check-cli-task-write-guard-638.md`](restore-check-cli-task-write-guard-638.md).

Exit codes: `0` means the requested check passed, `1` means verification
reported a failed permission/hash check, and `2` means malformed input or a
refused operation. Fixture coverage is in `tests/test_backup_verify.py`.

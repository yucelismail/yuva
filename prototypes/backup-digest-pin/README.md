# Backup digest pin fixture prototype

Run from the repository root:

```sh
python3 prototypes/backup-digest-pin/fixture.py
```

The script creates a marked, mode-0700 synthetic tree inside a fresh system
temporary directory, builds a tiny synthetic tar, and calls the existing
`backup_verify.verify_backup()` preflight. Its `trust-input/expected-sha256.txt`
is outside the fixture `backup/` directory; the prototype compares this
caller-supplied value to the verifier's computed archive digest. It does not
use the adjacent `.sha256` as a pin and does not invoke `restore_check()`.

The emitted cases show that:

- a matching supplied digest is only a digest comparison: `authenticity`
  remains `unverified` and `restore_authorized` remains false;
- replacing the synthetic archive and adjacent checksum together passes the
  existing local consistency preflight but mismatches the unchanged supplied
  pin;
- missing, malformed, or wrong supplied pins never upgrade authenticity.

This is a fixture harness, not a production CLI or persistent pin ledger. The
harness writes its own pin after creating the synthetic archive, so it does
**not** demonstrate an operationally independent trust domain. A real pin
must be delivered through a separate, authenticated channel/media by an
authorized operator. The digest is deliberately not printed. No real backup,
digest, private key, active Yuva data, or restore destination is used; no
production verifier code is modified.

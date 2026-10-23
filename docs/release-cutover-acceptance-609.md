# Yuva #609 — Release install/cutover/rollback fixture

`release_acceptance.py fixture` now exercises a complete synthetic release
chain inside one `TemporaryDirectory`:

1. It creates two clean fixture Git sources and payloads, computes their
   manifests and digest pins, then installs both through `release_installer`.
2. It verifies the selected v2 release against its source and pin and follows
   the installer-owned `current` pointer.
3. A fixture-only `~/.local/bin/yuva` symlink is resolved through an explicit
   fixture `PATH`; the canary is invoked using that PATH command. The installed
   unit file is a copy of the release template under the temporary home.
   Its `%h`-expanded `WorkingDirectory`, panel `ExecStart`, and `YUVA_DIR` are
   parsed as data and compared with the current release and separate fixture
   data directory. No systemd command or service is called.
4. CLI and unit-targeted panel canaries read the same synthetic task/message
   records. A before/after tree digest verifies they did not change the data.
5. The fixture verifies a backup and scratch restore-check, checks known data
   schema compatibility, rolls back through the installer, then repeats the
   manifest, PATH, unit, CLI/panel, and data-root checks against v1.
6. The report's fixture GO requires explicit `True` for each gate. Host rollout
   stays NO-GO because the fixture pin is not an independent trust anchor and
   no live process/writer identity is inspected. The writer gate is explicitly
   `fixture_writer_sequential`: it describes only the sequential synthetic
   CLI/panel canaries and is not evidence of host writer singleton.

The report also confirms that the temporary root no longer exists **after**
the `TemporaryDirectory` context exits by checking the path with `lstat`; the
report contains no pre-context placeholder value. All install, release, payload, backup,
scratch, PATH alias, unit, source and data files are below that root. The
subprocess `YUVA_DIR` is explicitly set to the synthetic data directory; the
host Yuva data directory is not read or written.

Targeted acceptance command:

```sh
python3 -m unittest tests.test_release_acceptance -v
```

This fixture validates wiring and rollback behavior for synthetic files only.
It does not inspect or start the real panel, alter a real PATH entry or unit,
or approve a host release.

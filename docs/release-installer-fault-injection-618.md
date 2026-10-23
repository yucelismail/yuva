# Yuva #618 — Release installer fault-injection fixture

`tests/test_release_installer.py` injects failures only into installer calls
whose source, payload, install root, and data root are created under its
`TemporaryDirectory`. No real install root, YUVA data, service manager, or
systemd unit is read or changed.

| Fault point | Expected result | `current` / data-root result |
|---|---|---|
| Partial payload copy | Ordinary install failure; staging tree removed | Prior `current` target remains byte-for-byte the same; full data-root tree digest is unchanged |
| Staged manifest verification | Install fails before publication; staging tree removed | Prior pointer and data-root digest remain unchanged |
| Release-directory fsync after release rename | Install stops before manifest/pointer switch; an unpublished release directory may remain for inspection | Prior pointer and data-root digest remain unchanged; result is NO-GO, with no automatic cleanup/rollback of the published release tree |
| `current` pointer `os.replace` fault | `CommitUnknown`; caller must inspect exact pointer before retry | Fixture observes the pointer and confirms the data-root digest is unchanged; no compensating pointer switch runs |
| Parent-directory fsync after `current` replacement | `CommitUnknown`; visible target may be new while crash durability is unknown | Fixture observes the new symlink target, confirms the data-root digest is unchanged, and confirms no automatic switch back to the prior release |

Pointer replacement errors are treated conservatively as `CommitUnknown`, even
when an injected failure happens before the test filesystem changes the link.
The exception is still a NO-GO signal; it is not permission to retry, infer
which release will survive a crash, or roll the pointer back automatically.
Pre-pointer failures that preserve the old target are also NO-GO for the
requested install, though their active-code pointer is known to be unchanged.

Run the isolated fault and ordinary install fixtures with:

```sh
python3 -m unittest tests.test_release_installer -v
```

The fixture compares exact `current` symlink targets and a recursive
data-root digest before/after each injected failure. It proves only the
modeled paths on the test filesystem; it does not simulate power loss, prove
host writer identity, or authorize a live install/rollback.

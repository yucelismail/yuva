# Yuva wait lock revalidation cleanup (#764)

`_locked_root()` now holds setup and the yielded critical section under one
cleanup boundary. If lock path revalidation fails after `flock`, the context
manager unlocks and closes the descriptor before preserving the existing
`ValueError` rejection. Lock acquisition and timeout semantics are unchanged.

The regression injects an `os.stat` failure after lock acquisition, compares
the lock-path descriptor count before and after, successfully takes the lock
with a second nonblocking probe, then performs a successful bootstrap and
cursor read. Receipt writes remain confined to the test's marked temporary
fixture.

Verification: the failure-injection module passed 9 tests and the core receipt
store module passed 7 tests. No live Yuva data or consumer runtime was used.

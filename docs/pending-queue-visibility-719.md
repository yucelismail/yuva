# Pending queue visibility (#719)

`yuva tahta` now warns when fewer than 12 tasks are in `pending`, and stays
quiet at 12 or more. The count uses the `pending` state only; assigned work
does not fill the unassigned queue. Display is read-only and does not create
or assign tasks.

Disposable fixture coverage checks 11/12/13 task boundaries, an all-assigned
board, and a real CLI claim moving one task from pending to assigned (12 to 11).

Validation:

```text
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest \
  tests.test_pending_queue_visibility -v
Ran 3 tests ... OK
```

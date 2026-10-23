# Isolated task scheduler sketch

`scheduler.py` is a pure, provider-neutral and Yuva-CLI-independent decision
prototype. A caller gives `decide()` a detached task snapshot, the worker ID,
and any operation IDs whose write result is still unknown. The function returns
one recommendation; it never claims, edits, delivers, or persists a task.

## Transition table

| Observed state | Recommendation | Meaning / next safe step |
| --- | --- | --- |
| Operation result is unknown | `reconcile_required` | Read canonical task/operation state first. Do not repeat the mutation based on a timeout or missing message. |
| Task has an unrecognized status | `reconcile_required` | Do not infer a transition. Re-read the canonical task record. |
| More than one task is `assigned` to this worker | `resolve_multiple_active_tasks` | The one-active-execution contract is already violated; resolve it before claiming more work. |
| A task assigned to this worker is `pending_revision`, and another task is active | `pause_at_safe_point_then_resume_revision` | Record progress on the active task, reach a safe stop, then reclaim the revision. Yuva has no modeled pause transition here. |
| A task assigned to this worker is `pending_revision`, with no other active task | `resume_revision` | Reclaim this revision before considering unrelated pending tasks. |
| One task is already `assigned` to this worker | `continue_assigned` | Continue that active task; do not claim a second one. |
| Eligible `pending` task with all explicit dependencies `verified` | `claim_independent_pending` | This is the next candidate. A `parent_id` alone does not block it. |
| Pending task has a dependency absent from the snapshot | `reconcile_required` | The snapshot is incomplete; do not treat the missing prerequisite as satisfied. |
| Pending tasks have unmet dependencies, and none are eligible | `wait_for_dependencies` | Keep those tasks pending until each explicit prerequisite is verified. |
| Only `pending_gorevli_review` / `pending_verification` work remains | `await_review_or_new_independent_task` | Review-pending deliveries are not active execution and are not final approval. |
| No eligible work or review is present | `no_work` | No next task can be recommended from this snapshot. |

## State and scope limits

- `assigned` is treated as the worker's active slot. Review-pending tasks do
  not occupy it, so an unrelated eligible pending task can be recommended.
- `pending_revision` for this worker takes precedence. If another task is
  active, the recommendation explicitly requires a safe stop and progress
  record first; the prototype does not claim that Yuva can pause that task.
- `parent_id` expresses hierarchy only. Only `dependency_ids` express a
  prerequisite, and this sketch requires each listed prerequisite to be
  `verified` before recommending a claim.
- Unknown operation results are supplied by the caller, because this sketch
  has no mutation channel. They block all scheduling until external
  reconciliation. No absent message, timeout, or failed response is treated as
  proof that an operation did not happen.
- Task snapshots, worker identity, dependency lists, and operation IDs are
  caller assertions. The prototype does not authenticate them, detect changes
  after the read, serialize concurrent workers, or guarantee that a later claim
  succeeds.
- All inputs are read-only and all state is volatile. There is no provider,
  Yuva CLI, panel, task store, queue, persistence, locking, or runtime hook.

No tests or runtime checks were run, as required by the task.

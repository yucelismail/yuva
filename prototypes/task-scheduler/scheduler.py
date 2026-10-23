"""Provider- and CLI-neutral task scheduling decision sketch.

The caller supplies a detached task snapshot and unresolved operation IDs.
This module performs no I/O, claims no task, mutates no task record, and keeps
no durable or shared state. Its output is a recommendation for an outer worker.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence


REVIEW_STATES = frozenset({"pending_gorevli_review", "pending_verification"})
KNOWN_STATES = frozenset({
    "pending",
    "assigned",
    "pending_gorevli_review",
    "pending_verification",
    "pending_revision",
    "verified",
    "dropped",
})


@dataclass(frozen=True)
class Task:
    """Minimal caller-provided task view; parent and prerequisites differ."""

    task_id: str
    status: str
    assignee: str | None = None
    parent_id: str | None = None
    dependency_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class Decision:
    """A recommendation only; it is not a successful task transition."""

    action: str
    task_id: str | None = None
    reason: str = ""
    related_task_ids: tuple[str, ...] = ()
    operation_ids: tuple[str, ...] = ()


def decide(
    tasks: Sequence[Task],
    worker_id: str,
    *,
    unresolved_operation_ids: Iterable[str] = (),
) -> Decision:
    """Recommend one safe next action from a single externally read snapshot.

    `dependency_ids` are explicit prerequisites and require `verified` status.
    `parent_id` is descriptive hierarchy only. A result-unknown operation or an
    unrecognized task status stops scheduling until the caller reconciles it.
    """
    if not worker_id:
        return Decision("blocked", reason="worker_id_required")

    unresolved = tuple(sorted(set(unresolved_operation_ids)))
    if unresolved:
        return Decision(
            "reconcile_required",
            reason="operation_result_unknown; do_not_repeat_mutation",
            operation_ids=unresolved,
        )

    by_id: dict[str, Task] = {}
    for task in tasks:
        if not task.task_id or task.task_id in by_id:
            return Decision("unknown", reason="missing_or_duplicate_task_id")
        by_id[task.task_id] = task

    unknown = tuple(sorted(
        task.task_id for task in tasks if task.status not in KNOWN_STATES
    ))
    if unknown:
        return Decision(
            "reconcile_required",
            reason="unrecognized_task_status",
            related_task_ids=unknown,
        )

    active = tuple(sorted(
        task.task_id for task in tasks
        if task.status == "assigned" and task.assignee == worker_id
    ))
    if len(active) > 1:
        return Decision(
            "resolve_multiple_active_tasks",
            reason="single_active_execution_limit_exceeded",
            related_task_ids=active,
        )

    revisions = tuple(sorted(
        task.task_id for task in tasks
        if task.status == "pending_revision" and task.assignee == worker_id
    ))
    if revisions:
        revision_id = revisions[0]
        if len(revisions) > 1:
            return Decision(
                "resolve_multiple_revisions",
                reason="revision_priority_is_ambiguous",
                related_task_ids=revisions,
            )
        if active and active[0] != revision_id:
            return Decision(
                "pause_at_safe_point_then_resume_revision",
                task_id=revision_id,
                reason="pending_revision_has_priority; record_current_progress_before_switch",
                related_task_ids=(active[0], revision_id),
            )
        return Decision(
            "resume_revision",
            task_id=revision_id,
            reason="claim_pending_revision_before_independent_work",
        )

    # A review-pending task is not active execution, so it does not occupy the
    # worker slot. An already assigned task does occupy it.
    if active:
        return Decision(
            "continue_assigned",
            task_id=active[0],
            reason="one_active_task_already_assigned",
        )

    blocked: list[str] = []
    for task in sorted(tasks, key=lambda item: item.task_id):
        if task.status != "pending":
            continue
        unmet = False
        for dependency_id in task.dependency_ids:
            dependency = by_id.get(dependency_id)
            if dependency is None:
                return Decision(
                    "reconcile_required",
                    task_id=task.task_id,
                    reason="dependency_missing_from_snapshot",
                    related_task_ids=(task.task_id, dependency_id),
                )
            if dependency.status != "verified":
                unmet = True
                break
        if unmet:
            blocked.append(task.task_id)
            continue
        return Decision(
            "claim_independent_pending",
            task_id=task.task_id,
            reason="no_active_task; explicit_dependencies_verified",
        )

    review_ids = tuple(sorted(
        task.task_id for task in tasks if task.status in REVIEW_STATES
    ))
    if blocked:
        return Decision(
            "wait_for_dependencies",
            reason="pending_tasks_have_unmet_explicit_prerequisites",
            related_task_ids=tuple(blocked),
        )
    if review_ids:
        return Decision(
            "await_review_or_new_independent_task",
            reason="review_pending_is_not_final_approval_or_active_execution",
            related_task_ids=review_ids,
        )
    return Decision("no_work", reason="no_eligible_pending_task")

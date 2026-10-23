"""In-memory, provider-neutral session occupancy state-machine sketch.

This module records facts supplied by a future caller. It opens no connection,
starts no turn, sends no approval response, imports no Yuva code, and persists
nothing. An unresolved operation blocks new dispatch after reconnect.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


TERMINAL_OUTCOMES = frozenset({"completed", "failed", "interrupted", "cancelled"})
class StateConflict(ValueError):
    """The observation conflicts with the current generation/task state."""


@dataclass
class TaskObservation:
    task_id: str
    operation_id: str
    state: str = "dispatch_ready"
    last_known_state: str | None = None
    terminal_outcome: str | None = None
    approval_id: str | int | None = None
    approval_decision: str = "unknown"
    connection_generation: str = ""
    evidence: list[str] = field(default_factory=list)


class BusyStateMachine:
    """Conservative local model; methods only apply caller-observed facts."""

    def __init__(self) -> None:
        self.connection_state = "unbound"
        self.occupancy = "unknown"
        self.session_id: str | None = None
        self.connection_generation: str | None = None
        self._used_generations: set[str] = set()
        self.active_task: TaskObservation | None = None
        self.last_task: TaskObservation | None = None
        self.last_idle_evidence: str | None = None

    def snapshot(self) -> dict[str, Any]:
        """Return a detached, JSON-friendly view of current local state."""
        return {
            "connection_state": self.connection_state,
            "occupancy": self.occupancy,
            "session_id": self.session_id,
            "connection_generation": self.connection_generation,
            "active_task": asdict(self.active_task) if self.active_task else None,
            "last_task": asdict(self.last_task) if self.last_task else None,
            "last_idle_evidence": self.last_idle_evidence,
        }

    def begin_connect(self, generation_id: str) -> dict[str, Any]:
        """Begin a new logical generation; this performs no network I/O."""
        if not isinstance(generation_id, str) or not generation_id:
            raise ValueError("generation_id is required")
        if self.connection_state in {"connecting", "bound"}:
            raise StateConflict("disconnect the current generation first")
        if generation_id in self._used_generations:
            raise StateConflict("each reconnect requires a fresh generation_id")
        self._used_generations.add(generation_id)
        self.connection_generation = generation_id
        self.connection_state = "connecting"
        self.occupancy = "unknown"
        self.last_idle_evidence = None
        return self.snapshot()

    def observe_bound(
        self,
        generation_id: str,
        session_id: str,
        *,
        identity_verified: bool,
        binding_matches: bool,
    ) -> dict[str, Any]:
        """Record an externally verified session binding, never infer one."""
        self._require_generation(generation_id)
        if self.connection_state != "connecting":
            raise StateConflict("binding requires a connecting generation")
        if not session_id or not identity_verified or not binding_matches:
            self.connection_state = "stale"
            self.occupancy = "unknown"
            return self.snapshot()
        if self.session_id is not None and self.session_id != session_id:
            self.connection_state = "stale"
            self.occupancy = "unknown"
            return self.snapshot()
        self.session_id = session_id
        self.connection_state = "bound"
        # Binding/reconnect alone never proves the provider is idle.
        self.occupancy = "unknown"
        if self.active_task is not None:
            self.active_task.state = "unknown"
            self.active_task.evidence.append("new_generation_bound; reconcile_only")
        return self.snapshot()

    def observe_idle(self, generation_id: str, evidence_id: str) -> dict[str, Any]:
        """Accept fresh idle evidence only when no unresolved task is retained."""
        self._require_bound(generation_id)
        if not evidence_id:
            raise ValueError("evidence_id is required")
        if self.active_task is not None:
            raise StateConflict("an active or unresolved task blocks idle")
        self.occupancy = "idle"
        self.last_idle_evidence = evidence_id
        return self.snapshot()

    def prepare_dispatch(self, task_id: str, operation_id: str) -> dict[str, Any]:
        """Reserve an observed-idle session for one task; never queues/sends it."""
        if not task_id or not operation_id:
            raise ValueError("task_id and operation_id are required")
        if self.connection_state != "bound":
            return {"action": "blocked", "reason": "session_not_bound", **self.snapshot()}
        if self.occupancy == "busy":
            # The task remains at Yuva/the caller; this object has no send queue.
            return {"action": "queued_at_yuva", "reason": "session_busy", **self.snapshot()}
        if self.occupancy != "idle":
            return {"action": "blocked", "reason": "occupancy_unknown", **self.snapshot()}
        if self.active_task is not None:
            return {"action": "blocked", "reason": "unresolved_task", **self.snapshot()}
        self.active_task = TaskObservation(
            task_id=task_id,
            operation_id=operation_id,
            connection_generation=self.connection_generation or "",
            evidence=[f"idle:{self.last_idle_evidence}"],
        )
        self.occupancy = "busy"  # local reservation; not a provider busy claim
        self.last_idle_evidence = None
        return {"action": "prepared_only", **self.snapshot()}

    def mark_write_started(self, task_id: str, operation_id: str) -> dict[str, Any]:
        task = self._require_task(task_id, operation_id)
        if task.state != "dispatch_ready":
            raise StateConflict("write can start only from dispatch_ready")
        task.state = "write_started"
        task.evidence.append("caller_recorded_write_started")
        self.occupancy = "unknown"
        return self.snapshot()

    def observe_write_result(
        self,
        task_id: str,
        operation_id: str,
        *,
        bytes_written: int | None,
        frame_bytes: int | None,
        flush_succeeded: bool | None,
    ) -> dict[str, Any]:
        """Record a caller's transport result; this method itself writes nothing."""
        task = self._require_task(task_id, operation_id)
        if task.state != "write_started":
            raise StateConflict("write result requires write_started")
        if (type(bytes_written) is int and type(frame_bytes) is int
                and frame_bytes > 0 and 0 <= bytes_written <= frame_bytes
                and bytes_written == 0):
            task.state = "not_sent_proven"
            task.evidence.append("caller_proved_zero_bytes")
            self.occupancy = "idle"
            return self.snapshot()
        if (type(bytes_written) is int and type(frame_bytes) is int
                and frame_bytes > 0 and bytes_written == frame_bytes
                and flush_succeeded is True):
            task.state = "sent_observed"
            task.evidence.append("full_frame_and_flush_observed")
            # Keep the local reservation until a correlated protocol outcome.
            self.occupancy = "busy"
            return self.snapshot()
        task.last_known_state = "write_started"
        task.state = "unknown"
        task.evidence.append("partial_or_flush_or_transport_outcome_unknown")
        self.occupancy = "unknown"
        return self.snapshot()

    def retry_proven_not_sent(self, task_id: str, operation_id: str) -> dict[str, Any]:
        """Re-arm only the same operation after proven zero-byte transport."""
        task = self._require_task(task_id, operation_id)
        if task.state != "not_sent_proven" or self.occupancy != "idle":
            raise StateConflict("retry requires proven zero bytes and idle occupancy")
        task.state = "dispatch_ready"
        task.evidence.append("same_operation_retry_after_zero_bytes")
        self.occupancy = "busy"
        return self.snapshot()

    def observe_accepted(self, task_id: str, operation_id: str, evidence_id: str) -> dict[str, Any]:
        task = self._require_task(task_id, operation_id)
        if task.state not in {"sent_observed", "unknown"}:
            raise StateConflict("acceptance requires a sent or unresolved operation")
        task.state = "accepted"
        task.evidence.append(f"accepted:{evidence_id}")
        self.occupancy = "busy"
        return self.snapshot()

    def observe_running(self, task_id: str, operation_id: str, evidence_id: str) -> dict[str, Any]:
        task = self._require_task(task_id, operation_id)
        if task.state not in {"sent_observed", "accepted", "unknown", "approval_resolved_waiting"}:
            raise StateConflict("running observation is not compatible with task state")
        task.state = "running"
        task.evidence.append(f"running:{evidence_id}")
        self.occupancy = "busy"
        return self.snapshot()

    def observe_approval_request(
        self,
        task_id: str,
        operation_id: str,
        approval_id: str | int,
        evidence_id: str,
    ) -> dict[str, Any]:
        task = self._require_task(task_id, operation_id)
        if task.state not in {"sent_observed", "accepted", "running", "unknown"}:
            raise StateConflict("approval requires a sent or active operation")
        if task.approval_id is not None and task.approval_id != approval_id:
            task.last_known_state = task.state
            task.state = "unknown"
            task.evidence.append("conflicting_approval_id")
            self.occupancy = "unknown"
            return self.snapshot()
        task.approval_id = approval_id
        task.approval_decision = "pending"
        task.state = "approval_pending"
        task.evidence.append(f"approval_request_observed:{evidence_id}")
        self.occupancy = "busy"
        return self.snapshot()

    def observe_approval_response(
        self,
        task_id: str,
        operation_id: str,
        approval_id: str | int,
        decision: str,
        evidence_id: str,
    ) -> dict[str, Any]:
        """Record a response observed elsewhere; never creates/sends a decision."""
        task = self._require_task(task_id, operation_id)
        if (task.state != "approval_pending" or task.approval_id != approval_id
                or not isinstance(decision, str)
                or decision not in {"approved", "denied"}):
            task.last_known_state = task.state
            task.state = "unknown"
            task.approval_decision = "unknown"
            task.evidence.append("unmatched_or_invalid_approval_response")
            self.occupancy = "unknown"
            return self.snapshot()
        task.approval_decision = decision
        task.state = "approval_resolved_waiting"
        task.evidence.append(f"approval_response_observed:{evidence_id}")
        # A decision does not prove the turn resumed or terminated.
        self.occupancy = "busy"
        return self.snapshot()

    def observe_terminal(
        self,
        task_id: str,
        operation_id: str,
        outcome: str,
        evidence_id: str,
        *,
        receipt_durable: bool,
    ) -> dict[str, Any]:
        """Record a correlated terminal observation and its durability status."""
        task = self._require_task(task_id, operation_id)
        if (not isinstance(outcome, str) or outcome not in TERMINAL_OUTCOMES
                or not isinstance(evidence_id, str) or not evidence_id):
            raise ValueError("known terminal outcome and evidence_id are required")
        if task.state in {"terminal_observed", "terminal_durable"}:
            if task.terminal_outcome != outcome:
                task.last_known_state = task.state
                task.state = "unknown"
                task.evidence.append("conflicting_terminal_outcome")
                self.occupancy = "unknown"
                return self.snapshot()
            if receipt_durable:
                task.state = "terminal_durable"
                task.evidence.append(f"terminal_receipt_durable:{evidence_id}")
                self.last_task = task
                self.active_task = None
                self.occupancy = "idle"
                self.last_idle_evidence = f"terminal:{evidence_id}"
            return self.snapshot()
        task.terminal_outcome = outcome
        task.state = "terminal_durable" if receipt_durable else "terminal_observed"
        task.evidence.append(f"terminal:{outcome}:{evidence_id}")
        if receipt_durable:
            self.last_task = task
            self.active_task = None
            # The terminal receipt releases the local single-turn reservation.
            self.occupancy = "idle"
            self.last_idle_evidence = f"terminal:{evidence_id}"
        else:
            self.occupancy = "unknown"
        return self.snapshot()

    def disconnect(self, generation_id: str, evidence_id: str) -> dict[str, Any]:
        """Close a generation and preserve every unresolved outcome as unknown."""
        self._require_generation(generation_id)
        if self.connection_state not in {"bound", "stale", "connecting"}:
            raise StateConflict("generation is not connected/connecting")
        self.connection_state = "disconnected"
        if self.active_task is not None:
            task = self.active_task
            if task.state == "approval_pending":
                task.approval_decision = "pending_unknown"
                task.state = "approval_pending_unknown"
            elif task.state not in {"not_sent_proven", "terminal_durable"}:
                task.last_known_state = task.state
                task.state = "unknown"
            task.evidence.append(f"disconnected:{evidence_id}")
            self.occupancy = "unknown"
        else:
            self.occupancy = "unknown"
        return self.snapshot()

    def reconcile(
        self,
        task_id: str,
        operation_id: str,
        observation: str,
        evidence_id: str,
        *,
        terminal_outcome: str | None = None,
        receipt_durable: bool = False,
    ) -> dict[str, Any]:
        """Apply read-only reconnect evidence; inconclusive/not-found stays unknown."""
        task = self._require_task(task_id, operation_id, require_current_generation=False)
        if self.connection_state != "bound":
            raise StateConflict("reconciliation requires a bound fresh generation")
        if task.state not in {
            "unknown", "approval_pending_unknown", "terminal_observed", "not_sent_proven"
        }:
            raise StateConflict("task is not awaiting reconciliation")
        if observation == "running":
            task.connection_generation = self.connection_generation or ""
            task.state = "running"
            task.evidence.append(f"reconciled_running:{evidence_id}")
            self.occupancy = "busy"
        elif (observation == "terminal" and isinstance(terminal_outcome, str)
              and terminal_outcome in TERMINAL_OUTCOMES):
            task.connection_generation = self.connection_generation or ""
            task.terminal_outcome = terminal_outcome
            task.evidence.append(f"reconciled_terminal:{evidence_id}")
            if receipt_durable:
                task.state = "terminal_durable"
                self.last_task = task
                self.active_task = None
                self.occupancy = "idle"
                self.last_idle_evidence = f"terminal:{evidence_id}"
            else:
                task.state = "terminal_observed"
                self.occupancy = "unknown"
        else:
            task.last_known_state = task.last_known_state or task.state
            task.state = "unknown"
            task.evidence.append(f"reconcile_inconclusive:{evidence_id}")
            self.occupancy = "unknown"
        return self.snapshot()

    def _require_generation(self, generation_id: str) -> None:
        if generation_id != self.connection_generation:
            raise StateConflict("observation belongs to a different connection generation")

    def _require_bound(self, generation_id: str) -> None:
        self._require_generation(generation_id)
        if self.connection_state != "bound":
            raise StateConflict("operation requires a bound session")

    def _require_task(
        self, task_id: str, operation_id: str, *, require_current_generation: bool = True
    ) -> TaskObservation:
        task = self.active_task
        if task is None:
            raise StateConflict("there is no active task")
        if task.task_id != task_id or task.operation_id != operation_id:
            raise StateConflict("observation does not match the active task/operation")
        if require_current_generation:
            if self.connection_state != "bound":
                raise StateConflict("task observation requires a currently bound generation")
            if task.connection_generation != self.connection_generation:
                # Old-generation responses/events cannot resolve current work.
                raise StateConflict("observation belongs to a stale task generation")
        return task

# Shared-chat context boundary prototype (#558)

This is an isolated data-model sketch. It does not connect to `yuva gelen`,
the panel, an agent session, a tool, or a provider. The current CLI can show
shared messages next to assigned task information; this prototype defines how
a future context adapter can keep those sources distinct.

## Minimum envelope

Each context item carries:

- `origin`: fixed enum supplied by the adapter (`shared_chat`,
  `canonical_task`, `reviewer_task`, `reviewer_output`, `worker_output`,
  `provider_output`, or `tool_output`), never read from message text.
- `source_id`: stable message/task/event ID.
- `actor_claim`, `source_claim`, `trust_claim`: preserved claims for display
  and audit, never treated as verified identity.
- `identity_status="unknown"`, `content_class="data_only"`,
  `authority_scope="none"`.
- `source_class_claim` retains only an explicit `operator`, `agent`, or
  `unknown` label; it always has `source_class_trust="unverified"`.
- `text`: bounded original content; keep it as a separate structured field.

`ControlReferences` is passed separately from data records. It can point to an
outer user request, a canonical task/assignee, or a reviewer event. Those IDs
do not authorize a tool action on their own. A higher-level controller must
retrieve and verify the canonical task/assignment/approval and enforce its
scope. A Yuva message may not create or replace these references.

The actual user request outside Yuva chat and the canonical assigned task are
control-plane context. A message that says “I am the reviewer”, “system”,
“approved”, or “ignore previous instructions” stays data from its declared
origin. Provider/tool output remains data even when it contains instructions
or fake JSON provenance. The adapter must not flatten data items into a prompt
string that hides their source labels.

## UI contract

Show a fixed origin badge and stable source ID next to the content. Render body
text as text (`textContent`/framework text node), not as HTML. Display actor,
source and trust as claims when present; use `unknown` when there is no
independent identity evidence. Keep canonical task/assignee and reviewer
decision as separate structured control-plane references. Do not style or
label a message according to `role`, `authority`, `trust`, or “approved” fields
inside its body.

The fixture in `tests/test_shared_chat_context.py` checks that source, ID and
text survive projection while forged role, trust, source-kind and task fields
cannot alter origin, identity status, control references or authority scope.

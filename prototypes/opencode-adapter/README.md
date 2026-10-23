# OpenCode HTTP adapter prototype

This directory is an isolated, standard-library-only prototype. Importing it
does not connect to a server. An explicit call to send_message, status, or
read_events performs an HTTP request.

## Surface

    adapter = OpenCodeAdapter(
        "http://127.0.0.1:4096",
        session_id="provider-session-id",
        timeout=10,
    )
    send_result = await adapter.send_message("Prompt text")
    status_result = await adapter.status()
    history_result = await adapter.messages(limit=100)
    event_batch = await adapter.read_events(max_events=50)

- send_message POSTs to /session/{session_id}/prompt_async. The prototype
  uses a text parts payload. An HTTP response, including 204, is only the
  endpoint's response; it is not a Yuva receipt, turn-completion proof, or
  exactly-once guarantee. It returns a typed SendResult: response_observed
  when an HTTP response was received, or unknown when transport or response
  handling failed. An unknown result may still have been applied by the
  provider. Do not retry automatically; inspect read-only status/history
  first.
- status reads /session/status, which may describe multiple sessions.
  Callers must correlate the returned provider data with the configured
  session ID and the installed server's schema.
- messages reads /session/{session_id}/message with a bounded history limit.
  It is read-only evidence that provider messages exist; it does not prove a
  Yuva delivery receipt, a complete event stream, or turn success.
- read_events reads a bounded batch from /event. An SSE event is emitted only
  after its blank-line delimiter. EOF discards any unfinished event, and
  complete=false marks EOF, timeout, or a configured read limit. The
  implementation does not claim replay, cursor, ordering, or reconnect
  recovery.
- reconcile.py contains a pure per-session event reducer and an explicit
  read-only `reconcile_after_disconnect(adapter, session_id=...)` example.
  Stream interruption sets activity to unknown. Reconciliation reads status
  and history; missing, malformed, or unmatched evidence leaves activity
  unknown and never resends a prompt.
- `session.idle` and `session.status` change occupancy only when the event
  explicitly carries a matching `properties.sessionID`. Global, ID-less,
  malformed, and other-session status events are unmatched/ignored and do not
  change this session's activity. This expected payload path still needs
  confirmation against the target server's `/doc` schema before integration.
- No OpenCode stream sequence field is treated as a monotonic cursor. Generic
  `sequence`, `seq`, and `version` fields are not ordering proof; conflicting
  unsequenced status transitions remain unknown until read-only REST
  reconciliation supplies a matching snapshot.
- Exact duplicates with the same SSE event ID and payload in one connection
  generation are ignored while their fingerprint remains in bounded history.
  Fingerprints and message observations are each capped at 4096 entries;
  conflicts are capped at 128. `SessionObservation.dedupe_history_evicted` is a
  sticky signal when a dedupe key is evicted. After eviction, a replay can be
  observed again: dedupe is best effort and provides no guarantee beyond the
  retained history. SSE IDs remain opaque and are never treated as cursors.
  Repeated message IDs may represent legitimate `message.updated` changes, so
  these are observations rather than conflicting delivery receipts.
- Responses are capped at 2 MiB; SSE reads have configurable event/byte caps
  and a per-line cap. Transport errors omit headers and response bodies.
- The only authentication option is optional HTTP Basic Auth. Credentials are
  held in memory for the adapter lifetime, are never included in exceptions,
  and are sent only to the configured base URL. Redirects are rejected.
- No permission response, shell endpoint, TUI control, Yuva task mutation,
  automatic approval, or approval bypass is implemented.

## Explicit assumptions and limits

The endpoint names and broad behaviors follow the research in
docs/opencode-session-bridge-options-472.md: /session/:id/prompt_async,
/session/status, and /event. Request/response schemas are version-dependent;
the exact parts request shape and actual session status payload must be
checked against the target server's /doc OpenAPI schema before integration.
No installed OpenCode server or schema fixture was available for this
prototype.

The base URL accepts HTTP or HTTPS with a numeric loopback IP literal only;
hostnames such as `localhost` are rejected to avoid DNS rebinding or resolution
ambiguity when Basic Auth is enabled. This is a development boundary, not
authentication against other local processes. `HttpResult` hides `body` and
`raw_body` from its repr, but callers should still avoid logging those fields
directly because provider content may be sensitive.
HTTPS certificate policy is left to Python's default TLS validation. There is
no Yuva integration, durable send ledger, redaction pipeline, workspace
binding, capability negotiation, or provider version fingerprint.

The prototype does not run at import time. It was not connected to a live
server; no tests or runtime checks were run.

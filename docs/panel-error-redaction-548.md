# Panel and CLI error redaction (#548)

## Findings and changes

- `BaseHTTPRequestHandler.log_message()` is disabled, so request lines and
  headers are not copied into the panel journal.
- Panel request failures previously returned exception text directly. It could
  include filesystem paths, request-derived values, or provider/auth diagnostics.
  They now return fixed, action-oriented messages. Unexpected server failures
  include a random 8-hex event ID; stderr records only that ID, a fixed context,
  exception type, and an optional numeric errno. Exception messages and
  tracebacks are not logged.
- Persistent data failures now explain that Yuva did not auto-repair the file
  and direct the operator to check permissions/disk or repair from a trusted
  backup. The exception content is withheld from both the response and log.
- Failed task operations no longer return captured CLI stdout/stderr or
  exception text. CLI stderr is captured separately and never returned or
  copied to the panel journal. Successful task responses keep their existing
  result shape.
- Startup output no longer includes the data-root path or auth-enabled state.
  Host, Origin, content type, JSON, and route errors no longer reflect raw
  request values.
- The host-supervised heartbeat launcher passes a private token in its
  `systemd-run` arguments. Failure handling used to relay raw process
  stdout/stderr, which could echo those arguments. It now reports only the
  command's exit code and a fixed cleanup result. CLI filesystem failures use
  a numeric errno instead of the exception's raw path text.

## Boundaries

Normal CLI commands that intentionally display messages or screen records still
display their requested data; those outputs are not operational logs. This
change does not redact data at message/screen write time, alter retention, or
change auth configuration. It did not read live logs, secrets, or service
state. The bounded diagnostic identifies the failure class and errno, not its
raw message; operators should use the event ID when sharing a report.

## Verification

`tests/test_error_redaction.py` uses synthetic prompt/token strings to check
that panel stderr and error bodies do not echo exception content. The focused
redaction fixtures pass. Related existing task-principal tests were also run;
three fail on pre-existing behavior outside this change: two expect missing or
malformed task requests to return 401 before input validation (the current code
returns 400), and one expects a direct CLI principal mutation to raise
`SystemExit` (the current working-tree CLI does not). No task-principal code was
changed here.

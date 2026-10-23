# Output minimization fixture

Run from the repository root:

```sh
python3 prototypes/output-log-minimization/fixture.py
```

The memory-only fixture uses synthetic environment values, argv, headers,
stdout/stderr and a Codex app-server `item/commandExecution/outputDelta`
message. It produces a report from a fixed metadata allowlist, a screen record
with constant status text passed through `yuva_screen_redaction`, and the
existing agent adapter's metadata-only event projection. It checks that the
synthetic values do not reach any of those sinks.

The fixture also demonstrates the limit of regex masking: the known synthetic
Bearer example is masked, while an unknown synthetic value remains unchanged
when passed directly to the screen redactor. The safe sinks stay clear because
free-form argv/environment/header/stdout/stderr/delta content is omitted by
construction, not because a regex is assumed to recognize every secret.

This is an isolated prototype, not a production change. It writes no Yuva
files and starts/connects to no service. The report contains only fixed
operation class, outcome and a duration bucket; it does not contain the full
command, environment names/values, headers, output, exact output size, path,
exception detail or raw protocol message.

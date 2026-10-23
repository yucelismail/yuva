# CI error redaction canary fixture (#749)

Added a regression case to `tests/test_error_redaction.py` that builds a
synthetic traceback containing a bearer-token marker, a private-key marker,
and a fixture-only absolute path. It passes that traceback as an exception
message through the persistent-state error response/logger path and checks
that neither the response nor stderr contains any canary or traceback text.

The assertions use fixed, sanitized failure messages so a redaction regression
does not echo the canary values into the unittest failure traceback. The test
uses no real credentials, key generation, CI log artifact, or external service.

Verification: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest
tests.test_error_redaction -v` passed (4/4); `git diff --check` was clean.

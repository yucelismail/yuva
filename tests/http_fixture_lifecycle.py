"""Lifecycle helpers for disposable loopback HTTP test servers."""

import threading


def stop_server(server, thread, *, timeout=2):
    """Stop and close a fixture server, then require its thread to exit."""
    failure = None
    try:
        server.shutdown()
    except Exception as exc:  # cleanup still closes and joins on shutdown errors
        failure = exc
    try:
        server.server_close()
    except Exception as exc:
        if failure is None:
            failure = exc
    try:
        thread.join(timeout=timeout)
    except Exception as exc:
        if failure is None:
            failure = exc

    if thread.is_alive():
        raise AssertionError("fixture HTTP server thread did not stop") from failure
    if failure is not None:
        raise failure


def start_server(testcase, server, *, timeout=2):
    """Start a non-daemon fixture server and register teardown immediately."""
    thread = threading.Thread(
        target=server.serve_forever,
        name=f"fixture-http-{server.server_port}",
        daemon=False,
    )
    try:
        thread.start()
    except Exception:
        server.server_close()
        raise
    testcase.addCleanup(stop_server, server, thread, timeout=timeout)
    return thread

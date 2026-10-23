# systemd panel and heartbeat unit names (#722)

The source defines two different roles and names:

- `yuva-panel.service` is the persistent user unit template for `panel/server.py`
  (UI and API). Its data root is `YUVA_DIR`; the unit does not run the
  heartbeat worker.
- `bin/yuva:host_birim()` constructs a separate transient
  `yuva-kalp-<hash>.service` name for the heartbeat worker. No heartbeat unit
  template is shipped, and the current fail-closed gate does not create or run
  that unit.

The panel unit description now names its UI/API role. README already documents
the two source entrypoints and their current gates; the Linux transition guide
now uses the same `current` release path for CLI and panel and explicitly
distinguishes the absent transient heartbeat unit. `preview/server.py` remains
a manual read-only preview, not another service.

Only repository files were inspected or changed. No systemd install, reload,
start, stop, status query, or live service modification was performed.

# Partial snapshot UI contract (#713)

The panel now consumes the global `snapshot_meta` on every successful snapshot,
not only the screen-specific metadata. A valid partial response displays an
accessible persistent status banner naming omitted groups/counts and stating
that visible lists may be incomplete. It does not label an empty visible list
as proof that no records exist.

Missing, malformed, unsupported, internally inconsistent, or unknown metadata
displays a separate coverage-unknown warning. The UI checks the metadata schema,
reason vocabulary, group counts, and that included counts match the rendered
snapshot. Complete metadata hides the warning. The screen-specific warning is
not duplicated when the global partial banner already covers it.

The fixture builds a real partial response through the snapshot budget selector
and checks its included/omitted contract against the accessible UI consumer.
Validation: `tests.test_panel_ui_workflow` and `tests.test_panel_snapshot_budget`
passed (13 tests). The ephemeral HTTP integration module could not bind a local
socket in the sandbox; no live endpoint or panel was used.

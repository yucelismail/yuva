# Yuva wait duplicate cursor conflict (#763)

`FixtureReceiptStore.observe()` now validates the duplicate's consumer epoch
and the original receipt's `previous_cursor` before returning
`duplicate_observation`. An existing message ID presented with a different
cursor or epoch returns `store_conflict`. A duplicate from the exact same
receipt chain remains idempotent; a new message with a stale cursor still
returns `cursor_conflict`.

Regression fixtures cover a changed cursor, replay against a restored older
store snapshot while the caller retains its later cursor, and an old message
ID presented in a new epoch. Conflict cases assert no append or byte changes;
the older receipt and store-derived cursor remain intact. The #724 audit test
names and expectations were updated to record the repaired behavior. The
fixture remains TemporaryDirectory-only and stores no message text.

Verification: the receipt store, failure-injection audit, CLI fixture, and
end-to-end fixture modules passed (24/24).

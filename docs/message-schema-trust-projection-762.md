# Message schema compatibility and trust projection (#762)

The failing legacy-reader assertion conflated two intentional read surfaces.
`bin/yuva` exposes archive-normalization metadata as top-level
`trust="unverified"`. The panel builds a narrower allowlist snapshot that does
not include top-level `trust`; it exposes the same unverified classification
inside the projected `provenance` object. Legacy records with no provenance
are normalized to `source="unknown"`, `trust="unverified"`, with no actor
identity.

Updated the fixture to assert each reader's actual contract and explicitly
document that distinction in the test. The test still verifies that an
explicitly unknown message schema version is skipped by both readers; it is
not reinterpreted as a legacy record. No production projection/schema code was
changed.

Verification: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest
tests.test_data_schema_compat -v` passed (6/6).

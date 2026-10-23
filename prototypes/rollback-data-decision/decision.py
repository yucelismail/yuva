"""Fixture-only rollback decision projection; never used by release_installer."""

KNOWN_CONTRACT = "yuva-data-contract/v1"
CONTRACT_ID_PREFIX = "yuva-data-contract/v"


def _recognized_contract_id(value):
    if not isinstance(value, str) or not value.startswith(CONTRACT_ID_PREFIX):
        return False
    suffix = value[len(CONTRACT_ID_PREFIX):]
    return bool(suffix) and suffix.isascii() and suffix.isdigit()


def decide_rollback(*, current_contract, target_contract, actual_schema,
                    target_reader, nested_extra_preservation,
                    screen_auxiliary_support, writers_frozen):
    """Return candidate/HOLD/NO-GO from synthetic evidence only.

    ``candidate`` means the fixture's reader/schema gates pass. It is not an
    operational rollback authorization; external pin, backup, runtime, owner,
    and host evidence are deliberately outside this projection.
    """
    reasons = []
    if (_recognized_contract_id(current_contract)
            and _recognized_contract_id(target_contract)
            and current_contract != target_contract):
        return {"decision": "NO-GO", "reasons": ["contract-mismatch"]}
    if current_contract != KNOWN_CONTRACT or target_contract != KNOWN_CONTRACT:
        return {"decision": "HOLD", "reasons": ["contract-unknown"]}

    required = {"durum", "gorevler", "mesajlar", "ekranlar"}
    if not isinstance(actual_schema, dict) or set(actual_schema) != required:
        return {"decision": "HOLD", "reasons": ["actual-schema-unknown"]}
    if not isinstance(target_reader, dict) or set(target_reader) != required:
        return {"decision": "HOLD", "reasons": ["target-reader-unknown"]}
    for source in required:
        observed = actual_schema[source]
        supported = target_reader[source]
        if observed in (None, "unknown") or supported in (None, "unknown"):
            return {"decision": "HOLD", "reasons": ["target-reader-unknown"]}
        if supported is False or (isinstance(supported, (set, tuple, list))
                                  and observed not in supported):
            return {"decision": "NO-GO", "reasons": ["target-reader-incompatible"]}
        if supported is not True and not isinstance(supported, (set, tuple, list)):
            return {"decision": "HOLD", "reasons": ["target-reader-unknown"]}

    if nested_extra_preservation is None:
        return {"decision": "HOLD", "reasons": ["nested-extra-preservation-unknown"]}
    if nested_extra_preservation is False:
        return {"decision": "NO-GO", "reasons": ["nested-extra-loss"]}
    if screen_auxiliary_support is None:
        return {"decision": "HOLD", "reasons": ["screen-auxiliary-unknown"]}
    if screen_auxiliary_support is False:
        return {"decision": "NO-GO", "reasons": ["screen-auxiliary-incompatible"]}
    if writers_frozen is not True:
        return {"decision": "HOLD", "reasons": ["writer-freeze-unproven"]}

    reasons.extend(("known-equal-contract", "actual-schema-supported",
                    "nested-extra-preserved", "screen-auxiliary-supported",
                    "writers-frozen"))
    return {"decision": "candidate", "reasons": reasons}

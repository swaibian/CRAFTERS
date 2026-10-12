# Coverage Map

> Last updated by: TC-C-02 (Accessibility Refs closer, EPIC_001 boundary), 2026-10-12

| SW-REQ | Tests | Coverage | Status |
|:-------|:------|:---------|:-------|
| SW-REQ-GW-CORE | 61 tests: 55 unit (`test_auth` 17, `test_backends` 15, `test_logger` 9, `test_phase1` 14) + 6 integration (`test_integration_tc_a`) | New package (no baseline); all gateway modules exercised incl. negative/unauthorized/redaction cases | ✅ |
| SW-REQ-GW-VERIFY | 63 tests: 57 unit (`test_phase2` 29, `test_containment` 28) + 6 integration (`test_integration_tc_b`) | Phase-2 tools + SnapshotStore/RecordStore + containment + token bootstrap exercised incl. negative/unauthorized/redaction/symlink cases | ✅ |
| SW-REQ-A11Y | 28 tests: 23 unit (`test_perception`) + 5 integration (`test_integration_tc_c`) | Perception math + filters + redaction + gateway wiring + pattern source-grounding | ✅ |
| SW-REQ-CHAT | TBD by TC-A-02 closer | — | 🔲 |
| SW-REQ-STREAM | TBD by TC-B-02 closer | — | 🔲 |
| SW-REQ-PACK | TBD by TC-C-02 closer | — | 🔲 |

Populated by TC closers.

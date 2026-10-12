# Requirements Matrix

> Last updated by: TC-C-02 (Accessibility Refs closer, EPIC_001 boundary), 2026-10-12

| SYS1 | SWE1 | SW-REQ | SWE3 (Issue) | SWE4 (Unit) | SWE5 (Integration) | Status |
|------|------|--------|-------------|-------------|-------------------|--------|
| SYS1-001 | SWE1-A | SW-REQ-GW-CORE | SWE3-A-01, SWE3-A-02 | `gateway/tests/test_auth.py` (17), `test_backends.py` (15), `test_logger.py` (9), `test_phase1.py` (14) | self-verify: `gateway/tests/test_integration_tc_a.py` (6) + SYS3 smoke (stdio + http `craft_status`) | ✅ |
| SYS1-001 | SWE1-B | SW-REQ-GW-VERIFY | SWE3-B-01, SWE3-B-02 | `gateway/tests/test_phase2.py` (29), `test_containment.py` (28), `gateway/snapshots.py` + `tools_phase2.py` + `main.py` bootstrap | self-verify: `gateway/tests/test_integration_tc_b.py` (6) + SYS3 smoke (in-memory full verify flow + live HTTP `craft_status` + Bearer-header list/call) | ✅ |
| SYS1-001 | SWE1-C | SW-REQ-A11Y | SWE3-C-01, SWE3-C-02 | `gateway/tests/test_perception.py` (23) + `docs/upstream-prs/` + `docs/a11y-contribution-pattern.md` | self-verify: `gateway/tests/test_integration_tc_c.py` (5) + SYS3 smoke (widgets + canvas_rect) | ✅ |
| SYS1-002 | SWE1-A | SW-REQ-CHAT | SWE3-A-01, SWE3-A-02 | TBD by TC-A-02 closer | self-verify (no-reviews) | 🔲 |
| SYS1-002 | SWE1-B | SW-REQ-STREAM | SWE3-B-01, SWE3-B-02 | TBD by TC-B-02 closer | self-verify (no-reviews) | 🔲 |
| SYS1-002 | SWE1-C | SW-REQ-PACK | SWE3-C-01, SWE3-C-02 | TBD by TC-C-02 closer | self-verify (no-reviews) | 🔲 |

Rows filled by TC closers.

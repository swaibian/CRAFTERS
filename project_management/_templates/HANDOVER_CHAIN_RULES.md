# Handover Chain Rules

> Rules enforced by the issue architect when creating issues.
> For V-Model levels, gates, and task ordering details → see `V_MODEL_FRAMEWORK.md`.

---

## Rule 1: Task Ordering

All issues follow the ordering defined in `V_MODEL_FRAMEWORK.md` §6:
- **0.0** Architecture docs → **0.1** Predecessor context → **0.2** Test gate →
  **1..N** Implementation → **N+1** Test gate → **N+2** Completion report

Review issues (every 5th) follow the review ordering in `V_MODEL_FRAMEWORK.md` §6.

---

## Rule 2: Predecessor Reading (Task 0.1)

| Issue | Reads |
|-------|-------|
| TC-X-01 (first) | `TC-X-00_COMPONENT_DEFINITION.md` only |
| TC-X-02+ | `TC-X-00` + `TC-X-{YY-1}_COMPLETION_REPORT.md` |
| Review (5th) | `TC-X-00` + ALL 4 predecessor completion reports |

Non-adjacent dependencies: add those completion reports to Task 0.1 as well.

---

## Rule 3: Specific Handoff Content

The final task must document **what** was built, tailored to actual work:

| Work Type | Handoff Must Include |
|-----------|---------------------|
| API | Endpoints, payload shape, auth, error codes |
| Schema change | Column names, migration steps, backward compat |
| Infrastructure | Service location, config, instantiation |
| UI components | Props, state management, events |
| Protocol | Frame types, sequencing, error handling |
| Review issue | Findings, architecture changes, integration tests added |

Always: gate results, deviations, open risks, usage examples.
**"Add notes for successor" is NOT acceptable.**

For every runtime issue, also hand off the logging evidence: event names and
safe fields, request/user context propagation, redaction/no-secret tests,
transport/failure behavior, audit/metrics separation, and any explicit `N/A`
rationale. The next issue must be able to continue the same context and privacy
contract without rediscovering it.

---

## Rule 4: Reference Documents Must Link Predecessor

The `📖 Reference Documents` section must include the predecessor's completion
report path explicitly.

---

## Rule 5: Component Definition Stays Current

Every issue updates `TC-X-00_COMPONENT_DEFINITION.md` after completion:
issue status, new decisions, scope changes, architecture doc revision notes.

---

## Rule 6: 5-Issue Batch Cycle

See `V_MODEL_FRAMEWORK.md` §5 for the full pattern and edge cases.
See `REVIEW_ISSUE_TEMPLATE.md` for the review issue structure.

---

## Rule 7: Gate Enforcement

See `V_MODEL_FRAMEWORK.md` §4 for gate definitions.
- MANDATORY failure → stop, fix, escalate
- Gate results → recorded in completion report
- Coverage regression → MANDATORY failure
- CONDITIONAL skip → document reason

---

## Rule 8: Gap Deferral Escalation

Gaps identified in review issues (SWE5) follow escalating severity on repeat deferral:

| Deferral Count | Required Severity | Action |
|:--------------:|:-----------------:|:-------|
| 1st occurrence | LOW allowed | Defer with specific target issue |
| 2nd occurrence (same gap) | **MEDIUM minimum** | Must be fixed in the current review issue |
| 3rd occurrence | **HIGH** | Mandatory fix — blocks completion |

**Matching rule**: A gap is "the same" if it refers to the same file, interface, or wiring point
(e.g., "controller endpoint not registered in the FastAPI router" appearing across TC-R1-05,
TC-R2-05, TC-R3-05 is the same gap deferred three times).

**Tracking**: Review issues MUST search all predecessor completion reports and the coverage map
for previously deferred gaps before classifying any new gap as LOW.

---

## Quality Checklist

### Handover Chain
- [ ] Every issue has Task 0.0 (architecture docs) + 0.1 (predecessor) + 0.2 (test gate)
- [ ] Every issue ends with specific (not generic) handoff
- [ ] Reference Documents link predecessor completion report
- [ ] Header dependencies match predecessor chain
- [ ] Related Issues has Depends On / Blocks
- [ ] Logger section/evidence present, or a specific tested `N/A` rationale

### V-Model Compliance
- [ ] Every issue has `V-Model:` tag (SWE3-X-YY or SWE5-X-YY)
- [ ] Every issue links to its SW-REQ
- [ ] Traceability section present

### Batch Cycle
- [ ] Every 5th issue uses REVIEW_ISSUE_TEMPLATE (type 🔍)
- [ ] Review issues list all 4 predecessor reports in Task 0.1
- [ ] TC < 5 issues → last issue inherits review responsibilities

### File Structure
- [ ] Empty completion report stubs alongside each issue
- [ ] TC-X-00 lists all issues (🔨 impl / 🔍 review)
- [ ] Architecture docs folder scaffolded (if first epic)

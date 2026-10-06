# Boomi Code Review Report Template

Use this markdown template to generate the formal peer-review report for any reviewed Boomi integration.

---

```markdown
# Boomi Code Review Report

## Review Details
| Field | Value | Field | Value |
|---|---|---|---|
| **ServiceNow Ticket #** | `{{INC_OR_TICKET_NUMBER}}` | **Review Date** | `{{YYYY-MM-DD}}` |
| **Developer** | `{{DEVELOPER_NAME}}` | **Reviewer** | `{{REVIEWER_NAME}}` |
| **Tenant** | `{{TENANT_NAME}}` | **Environment** | `{{DEV / QA / UAT / PROD}}` |
| **Functional Area** | `{{FUNCTIONAL_AREA}}` | **Change Type** | `{{New Process / Modification / Connector Change / Map / Config}}` |
| **Process / Component Name** | `{{PROCESS_NAME}}` | **Boomi Component ID** | `{{COMPONENT_GUID}}` |

---

## Review Verdict

- [ ] **✔ Approved** — No Critical or Major issues. Ready for release.
- [ ] **⚠ Approved with conditions** — Minor/Advisory findings or manageable Major items that must be resolved prior to final deployment.
- [ ] **✖ Rework required** — Critical policy violations (e.g. DB non-SRV_ user, unhandled errors, duplicate/redundant connections) detected. Must fix and resubmit for review.

**Overall Verdict**: **`{{VERDICT}}`**

---

## Executive Summary
{{BRIEF_EXECUTIVE_SUMMARY_PARAGRAPH}}

---

## Findings Matrix

| Finding ID | Severity | Category | Component / Shape | Issue Description | Required Remediation |
|---|---|---|---|---|---|
| **F-01** | `CRITICAL` | Security / DB | DB Connection: `{{NAME}}` | DB user `{{USER}}` does not have required `SRV_` prefix. | Request DBA service user prefixed with `SRV_`. Update connection. |
| **F-02** | `MAJOR` | Connections | Process: `{{NAME}}` | Redundant connections found: `{{CONN1}}` and `{{CONN2}}` target same host `{{HOST}}`. | Consolidate to single reusable connection. |
| **F-03** | `MAJOR` | Configuration | Shape: `{{SHAPE_LABEL}}` | Configurable endpoint `{{URL}}` is hardcoded instead of using Project Process Property. | Move endpoint to project Process Property component with extensions. |
| **F-04** | `MAJOR` | Structure | Shapes: `{{SHAPES}}` | Shapes have default labels (`Decision`, `Map`). | Add clear descriptive userlabels to all shapes. |
| **F-05** | `CRITICAL` | Error Handling | Connector: `{{SHAPE_LABEL}}` | Outbound HTTP/DB connector call lacks Try/Catch wrapper. | Wrap external connector call with Try/Catch shape. |
| **F-06** | `CRITICAL` | API Pagination | Shape: `{{SHAPE_LABEL}}` | Pagination loop lacks guaranteed termination or exit condition on empty page token. | Add a Decision shape checking null/empty token or record count < page limit. |
| **F-07** | `MAJOR` | Error Notification | Shape: `{{SHAPE_LABEL}}` | Error alert lacks essential diagnostic fields (Environment, Atom, Execution ID, Business ID). | Include all 6 diagnostic fields in the notification template. |

---

## Batch Processing & Runtime Failure Dynamics

| Architectural Dimension | Behavior Analysis | Operational Impact |
|---|---|---|
| **Batch Document Isolation vs. Halt** | `{{ISOLATED / FULL_HALT / CONDITIONAL}}` | `{{Explain whether 1 failed document terminates the entire batch or continues processing valid records, citing Try/Catch placement and connector error handling settings}}` |
| **Target System Downtime (Negative Scenarios)** | `{{FAIL_SAFE_ALERT / UNHANDLED_ABORT / HANG}}` | `{{Explain how the process behaves when target HTTP/DB is completely offline (timeouts, 502/503)}}` |
| **Persistent Errors & Circuit Breaking** | `{{FINITE_RETRY_DEADLETTER / INFINITE_LOOP_RISK}}` | `{{Explain behavior when target continuously rejects calls across multiple attempts}}` |
| **Zero-Source Data Behavior** | `{{DO_NOTHING_GRACEFUL / FALSE_ALARM_ERROR}}` | `{{Verify whether 0 records returned from source exits gracefully without failure}}` |

---

## Checklist Verification Summary

| # | Checklist Item | Status | Notes / Observation |
|---|---|---|---|
| **1.1** | Process name follows `[Domain]_[Object]_[Direction]_[Target]` | `PASS / FAIL` | {{NOTES}} |
| **1.2** | All shapes clearly labelled (no default labels) | `PASS / FAIL` | {{NOTES}} |
| **1.3** | Sub-processes used appropriately for modularity | `PASS / FAIL / NA` | {{NOTES}} |
| **1.4** | Process description/notes populated | `PASS / FAIL` | {{NOTES}} |
| **2.1** | Shared connection reuse (no duplicates) | `PASS / FAIL` | {{NOTES}} |
| **2.2** | No redundant connections (e.g., HTTP vs REST to same host) | `PASS / FAIL` | {{NOTES}} |
| **2.3** | Database user has `SRV_` service account prefix | `PASS / FAIL / NA` | {{NOTES}} |
| **2.4** | Newly created connections checked against PROD baseline | `PASS / FAIL / NA` | {{NOTES}} |
| **2.5** | Credentials configured in Environment Extensions | `PASS / FAIL` | {{NOTES}} |
| **3.1** | Configurable values in Project Process Property | `PASS / FAIL` | {{NOTES}} |
| **3.2** | Property scoping correct (`DDP_` vs `DPP_`) | `PASS / FAIL` | {{NOTES}} |
| **4.1** | Maps clean (no orphaned source/target fields) | `PASS / FAIL / NA` | {{NOTES}} |
| **4.2** | Map scripting minimal and well-commented | `PASS / FAIL / NA` | {{NOTES}} |
| **4.3** | Sensitive data masked / not logged in Notify/cache | `PASS / FAIL` | {{NOTES}} |
| **5.1** | Try/catch configured on all external connector shapes | `PASS / FAIL` | {{NOTES}} |
| **5.2** | Error notifications configured on catch path | `PASS / FAIL` | {{NOTES}} |
| **5.3** | Failed documents routed to dead-letter path/table | `PASS / FAIL` | {{NOTES}} |
| **5.4** | Finite retry limits (2-3 max) for transient endpoints | `PASS / FAIL / NA` | {{NOTES}} |
| **5.5** | Diagnostic context in notifications (Env, Atom, Process, Exec ID, Error, Business ID) | `PASS / FAIL` | {{NOTES}} |
| **5.6** | Target downtime / negative scenarios handled cleanly | `PASS / FAIL` | {{NOTES}} |
| **5.7** | Persistent target failures handled without infinite loops | `PASS / FAIL` | {{NOTES}} |
| **6.1** | Batch processing and document isolation documented | `PASS / FAIL / NA` | {{NOTES}} |
| **6.2** | Data Passthrough enabled where transformation unneeded | `PASS / FAIL / NA` | {{NOTES}} |
| **6.3** | Document cache cleared when no longer required | `PASS / FAIL / NA` | {{NOTES}} |
| **7.1** | API pagination loops close deterministically | `PASS / FAIL / NA` | {{NOTES}} |
| **7.2** | Zero-data from source exits gracefully ("do nothing") | `PASS / FAIL / NA` | {{NOTES}} |


---

## Reviewer Notes & Action Items
1. {{ACTION_ITEM_1}}
2. {{ACTION_ITEM_2}}

---

## Sign-off
| Role | Name | Date | Status |
|---|---|---|---|
| **Developer** | `{{DEVELOPER_NAME}}` | `{{YYYY-MM-DD}}` | Submitted |
| **Review Committee** | `{{REVIEWER_NAME}}` | `{{YYYY-MM-DD}}` | `{{VERDICT}}` |

_Boomi Code Review Framework_
```

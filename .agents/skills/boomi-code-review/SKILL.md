---
name: boomi-code-review
description: Conducts comprehensive code reviews and quality assurance on Boomi integration processes, maps, connections, and components. Enforces Psiog Integrations peer review standards, database service user (SRV_) conventions, process property externalization, redundant connection detection, PROD connection diffing, shape labelling, Try/Catch resilience, and sensitive data protection.
---

# Boomi Code Review Skill

This skill performs automated and deep architectural peer reviews of Dell Boomi integration assets. It enforces the **Psiog Integrations Code Review Checklist**, enterprise naming conventions, resilience standards, and client-specific security policies.

---

## Navigation & Workflows

Reviewing Boomi code consists of three review modes:
1. **Automated Static Analysis**: Run `scripts/boomi_code_review.py` to scan component XML files in `active-development/` for naming, labelling, connection duplication, DB credentials, and Try/Catch shapes.
2. **Deep Architectural Peer Review**: Evaluate the end-to-end integration logic against `references/checklist.md` for batching, error dead-lettering, sub-process design, and environment extensions.
3. **Formal Review Report Generation**: Generate a signed review report using `references/report_template.md` with ServiceNow ticket metadata, checklist status, and an actionable verdict (`Approved`, `Approved with conditions`, `Rework required`).

---

## Core Review Policies

Every review must strictly evaluate the following critical requirements:

### 1. Configuration Externalization (Process Property per Project)
* **Rule**: All configurable values (URLs, environment endpoints, directory paths, batch thresholds, feature flags, email recipients) **MUST** be defined in a dedicated **Process Property component (`type="processproperty"`) per project**.
* **Anti-Pattern**: Hardcoding URLs or paths in Message shapes, Set Properties shapes, or scattering ad-hoc Dynamic Process Properties (`DPP_...`) across shapes.
* **Extensions**: The Process Property component must be marked for Environment Extensions so values can be injected per environment (DEV, QA, PROD).

### 2. Database Service User Prefix (`SRV_`)
* **Rule**: All database connections (Legacy Database and Database V2) must use a service user account where the username is prefixed with **`SRV_`** (e.g., `SRV_FINANCE_APP`, `SRV_BOOMI_ETL`).
* **Severity**: `CRITICAL`. Any DB connection using a personal user, `sa`, `root`, `admin`, or an un-prefixed username must be rejected.

### 3. Redundant Connections & Endpoint Duplication
* **Rule**: No redundant connections may exist within a process or integration:
  * **Duplicate Connections**: Two connection components having identical host, port, or base URL configurations must be consolidated into a single reusable connection.
  * **Mixed Connector Types**: Having both an **HTTP Client** connection and a **REST** connection pointing to the same endpoint/API is strictly prohibited. Reuse the existing connection asset.
* **Severity**: `MAJOR`.

### 4. New Connections vs. PROD Baseline
* **Rule**: Every connection component utilized in a process under review must be checked against the **Production baseline**:
  * Any connection newly created that does not exist in PROD must be explicitly flagged and highlighted in the review report.
  * The reviewer must verify whether this is an intentional new external integration or an accidental duplicate created by the developer instead of reusing an existing connection.
* **Severity**: `MAJOR`.

### 5. Shape Labelling & Documentation
* **Rule**: Every shape on the process canvas must have a clear, descriptive `userlabel`. Default platform labels (e.g., `Decision`, `Branch`, `Map`, `Connector`, `Message`, `Notify`, `Set Properties`) are prohibited.
* **Process Documentation**: The `<bns:description>` (Process Notes) field must be populated with a clear summary of process intent, business domain, triggering mechanism, and data flow.
* **Process Naming**: Process names must follow the agreed standard: `[Domain]_[Object]_[Direction]_[Target]` (e.g., `FIN_Invoice_Sync_to_SAP`).

### 6. Error Handling & Resilience
* **Rule**: All connector calls and failure-prone operations must be wrapped in a **Try/Catch** shape (`shapetype="catcherrors"`).
* **Catch Path**: Must handle the error gracefully:
  * Log the error context with document ID, error timestamp, and `meta.base.catcherrorsmessage`.
  * Route failed documents to a dead-letter path (e.g., disk archive, error queue, or database table) for replay.
  * Trigger notifications (email, Slack webhook, or alert).
  * Never terminate silently or leave an unhandled error path.

### 7. Sensitive Data Protection
* **Rule**: Passwords, API tokens, authorization headers, credit cards, or PII must never be logged in cleartext via Notify shapes or written unencrypted into document cache or logs.

### 8. API Pagination & Zero-Data Source Handling
* **Pagination Loop Closure**: For paginated APIs, verify that loop exit conditions are deterministic (e.g. empty/null `next_page_token`, `hasNextPage == false`, or received record count < page size). Guard against infinite pagination loops.
* **Empty Source Data**: If the source system returns zero documents/empty payload, verify whether the process fails, logs an error, or exits gracefully.
* **Default Expectation**: **Do nothing / graceful exit** on empty source data unless the business specification explicitly mandates an alert/failure.

### 9. Target System Downtime (Negative Scenarios)
* **Rule**: How does the process treat target system outages (connection timeouts, HTTP 502/503/504, DB unreachable)?
* **Requirements**:
  * Outage must be trapped gracefully by Try/Catch without leaving the execution hung.
  * Must prevent partial/corrupted state (e.g. roll back or halt before marking records as processed).
  * Must fail the execution with an Exception shape or operational alert so support teams are notified.

### 10. Persistent Errors & Retry Governance
* **Rule**: If the target system persistently fails across multiple records or calls:
  * **No Infinite Retries**: Retry counts on Try/Catch must be finite (typically 2-3 attempts max).
  * **No Unbounded Recursion**: Recursive sub-process calls for paging or retries must have a strict depth/counter guard (`DPP_RetryCount < MAX_RETRIES`).
  * **Dead-Letter Routing**: Repeatedly failing records must be isolated to a dead-letter path or error table to prevent blocking subsequent batches.

### 11. Error Notification Metadata Completeness
* **Rule**: All error notifications (emails, alerts, or support tickets) **MUST** provide complete diagnostic context to enable rapid troubleshooting:
  1. **Environment Name**: (e.g., `DEV`, `QA`, `PROD` via environment property).
  2. **Runtime / Atom Name**: (e.g., `Execution Property - Atom Name`).
  3. **Process Name**: Component name of the failing process.
  4. **Execution ID**: Native Boomi execution ID (`meta.base.executionid`).
  5. **Native Error Message**: Boomi error message (`meta.base.catcherrorsmessage`).
  6. **Business Identifier**: Document tracking key (e.g. `DDP_InvoiceNumber`, `DDP_EmployeeID`, `DDP_OrderID`) to identify the exact document causing the failure.
* **Severity**: `MAJOR` if notifications lack these critical fields.

### 12. Batch Processing Isolation vs. Halt Dynamics
* **Rule**: The review must explicitly evaluate and document document-level failure behavior in batch processing:
  * **Halt Behavior**: If 1 document in a batch fails, does it cause the entire process to abort and halt all remaining valid documents?
  * **Isolated Processing**: Does the process isolate the failed document (e.g., via Try/Catch positioned *after* a Split shape) and continue processing the remaining valid documents?
  * **Conditional Triggers**: Document the exact conditions under which the process halts (e.g., connector error without "Return Application Error Responses", top-level Exception shape, or fatal database constraint).


## Review Execution Guide

### Step 1: Resolve the Skill Path
At the start of the review session:
```bash
# Get the absolute skill directory
SKILL_DIR=".agents/skills/boomi-code-review"
```

### Step 2: Component Acquisition
If the user provides a Boomi platform URL or Component ID:
1. Pull the root component and its dependencies into `active-development/` using the `boomi-integration` skill:
   ```bash
   bash .agents/skills/boomi-integration/scripts/boomi-component-pull.sh --component-id <GUID>
   ```
2. Inspect the pulled XML components in `active-development/`.

### Step 3: Run Automated Linter
Execute the review script on the component file or directory:
```bash
# Run review on a single process
python .agents/skills/boomi-code-review/scripts/boomi_code_review.py active-development/components/MyProcess.xml

# Run review on entire active-development workspace with PROD connection check
python .agents/skills/boomi-code-review/scripts/boomi_code_review.py active-development/ --prod-connections prod-baseline/
```

### Step 4: Perform Deep Architectural Inspection
Cross-check items that require semantic analysis using `references/checklist.md`:
* Sub-process modularity (Data Passthrough vs Bridge).
* Map cleanliness (no orphaned mappings, inline Groovy commented).
* Property scoping (`DDP_` for document-level vs `DPP_` for execution-level).
* Batching and cache clearing.

### Step 5: Generate Review Report
Format the findings using `references/report_template.md`. Compute the final verdict:
* **Approved (✔)**: Zero Critical, zero Major issues. Minor suggestions are optional.
* **Approved with conditions (⚠)**: Zero Critical issues, 1-2 Major issues that can be remediated before deployment, or advisory items.
* **Rework required (✖)**: Any Critical issue (e.g., DB username without `SRV_`, hardcoded credentials, unhandled outbound connector) or multiple Major issues (redundant connections, unlabelled shapes).

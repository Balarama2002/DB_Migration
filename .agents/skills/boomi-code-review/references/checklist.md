# Boomi Code Review Checklist Reference

This reference document details the full evaluation criteria for peer-reviewing Boomi integrations, synthesized from the Psiog Integrations review framework and enterprise security standards.

---

## 1. Structure & Naming Governance

| # | Check Item | Description & Rationale | Severity | XML & UI Verification Method | Remediation |
|---|---|---|---|---|---|
| **1.1** | **Process Naming Convention** | Process names must follow `[Domain]_[Object]_[Direction]_[Target]` (e.g. `FIN_Invoice_Sync_to_SAP`). Avoid generic names like `Test_Process` or missing prefixes. | **MAJOR** | Check `name` attribute on `<bns:Component type="process">`. | Rename process to follow the domain standard. |
| **1.2** | **Shape Labelling** | All shapes must have descriptive `userlabel` explaining business action. Unnamed shapes or default names (`Decision`, `Map`, `Connector`, `Branch`, `Message`, `Notify`, `Set Properties`) are prohibited. | **MAJOR** | Scan `<shape userlabel="...">`. Flag empty strings or matches against default shape type names. | Double-click shape in Boomi canvas; enter clear label (e.g., `Set DDP_OrderID`, `Branch 1: Active Accounts`). |
| **1.3** | **Process Description / Notes** | Process notes field must document business purpose, trigger schedule/event, source/target systems, and author details. | **MINOR** | Inspect `<bns:description>` on root `<bns:Component>`. Must not be empty. | Fill in the "Process Description" in Boomi Process Options. |
| **1.4** | **Sub-Process Modularity** | Reusable logic (common mapping, canonical transformations, standard notification pipelines) should be factored into reusable sub-processes. Avoid sprawling, monolithic canvas designs (>25 shapes without sub-processes). | **ADVISORY** | Inspect process canvas complexity and evaluate if repeated logic exists. | Extract repeating branches into child processes invoked via Process Call shape. |

---

## 2. Connectors & Connections

| # | Check Item | Description & Rationale | Severity | XML & UI Verification Method | Remediation |
|---|---|---|---|---|---|
| **2.1** | **Database Service User (`SRV_`)** | All Database connection components (Legacy Database and Database V2) must use a service user account starting with `SRV_` (e.g. `SRV_BOOMI_ORACLE`). Personal or generic accounts (`admin`, `root`, `sa`) are strictly rejected. | **CRITICAL** | For legacy DB: check `username` attribute on `<DatabaseConnectionSettings>`. For DB V2: check `<field id="username" value="...">` under `<GenericConnectionConfig>`. | Request DBA to provision a dedicated service account with `SRV_` prefix. Update connection component. |
| **2.2** | **No Redundant Connections** | No duplicate connections with identical host, port, or base URL may exist. Furthermore, do not mix connector types (e.g., an HTTP Client connection and a REST connection both pointing to the same API base URL). | **MAJOR** | Compare `url`, `host`, `port` across all connection XMLs (`http`, `rest`, `database`, `sftp`). | Consolidate onto a single, shared connection component across the workspace. |
| **2.3** | **New Connections vs. PROD Baseline** | Newly created connections not existing in the Production environment must be identified and flagged to prevent accidental duplication of existing enterprise connections. | **MAJOR** | Cross-reference connection component IDs in the process against known PROD connection GUIDs. | Confirm with integration architect whether the connection is a legitimate new system or an unintentional duplicate. |
| **2.4** | **Credentials in Extensions (No Hardcoding)** | Connection credentials (passwords, client secrets, API tokens) must NOT be hardcoded in component definitions. They must be configured as Environment Extensions. | **CRITICAL** | Inspect `<bns:encryptedValues>` and connection `<GenericConnectionConfig>` / `<DatabaseConnectionSettings>`. Verify extensions are declared. | Remove plaintext credentials; extend the connection password in Process Extensions. |
| **2.5** | **Connector Operation Context** | Operations should not be overloaded or reused across conflicting contexts (e.g. using a single GET operation intended for Account for an Order query). | **MINOR** | Review operation names and associated profiles (`requestProfileId`, `responseProfileId`). | Create dedicated, single-purpose connector operations. |

---

## 3. Configuration & Process Properties

| # | Check Item | Description & Rationale | Severity | XML & UI Verification Method | Remediation |
|---|---|---|---|---|---|
| **3.1** | **Project Process Property Component** | Configurable settings (environment URLs, file directories, thresholds, email recipients) must reside in a dedicated Process Property component (`type="processproperty"`) per project. | **MAJOR** | Check if project includes a `<DefinedProcessProperties>` component and shapes reference it. Flag static URLs in Message or Set Properties shapes. | Create a project Process Property component (e.g., `FIN_ERP_Properties`) and reference defined keys. |
| **3.2** | **Property Scoping (`DDP_` vs `DPP_`)** | Dynamic Document Properties must be prefixed with `DDP_` (document-scoped). Dynamic Process Properties must be prefixed with `DPP_` (execution-wide). Do not use execution-level DPPs for document-specific tracking. | **MAJOR** | Scan `<parametervalue>` and Set Properties shapes for property name conventions. | Standardize property names; ensure multi-document batches do not overwrite DPP values in loops. |

---

## 4. Data Handling & Mapping

| # | Check Item | Description & Rationale | Severity | XML & UI Verification Method | Remediation |
|---|---|---|---|---|---|
| **4.1** | **Map Cleanliness & Orphaned Fields** | Boomi maps (`transform.map`) must not contain disconnected/orphaned source or destination lines, unused function steps, or unmapped mandatory target fields. | **MINOR** | Inspect `<Mappings>`, `<Functions>` in `Map` XML. Ensure all function outputs link to target fields. | Clean up unnecessary function shapes and dangling lines in the map. |
| **4.2** | **Map Scripting Standards** | Custom Groovy or JavaScript in maps must be minimal, modular, and thoroughly commented explaining business logic and edge cases. | **MINOR** | Check `<FunctionStep category="Scripting">` or `<mapscript>`. Verify comment density and code simplicity. | Add explanatory header comments and inline documentation to custom scripts. |
| **4.3** | **Sensitive Data Protection** | Passwords, tokens, API keys, Social Security numbers, or PCI data must never be logged in cleartext via Notify shapes or written unencrypted to Document Cache. | **CRITICAL** | Scan Notify messages (`<notifyMessage>`) and Message shapes for keywords: `password`, `secret`, `bearer`, `apikey`, `token`, `auth`. | Mask or exclude sensitive fields before sending payloads to logs or alerts. |

---

## 5. Error Handling & Resilience

| # | Check Item | Description & Rationale | Severity | XML & UI Verification Method | Remediation |
|---|---|---|---|---|---|
| **5.1** | **Try/Catch on Connector Shapes** | All external connector shapes (HTTP, REST, Database, SFTP, SAP) and error-prone sub-processes must have Try/Catch coverage (`shapetype="catcherrors"`). | **CRITICAL** | Inspect shape connectivity graph. Ensure outbound connectors are preceded by a Try/Catch step. | Insert a Try/Catch shape upstream of external calls; configure `catchAll="true"`. |
| **5.2** | **Error Notifications** | Catch paths must dispatch an alert/notification (Email, Slack/Teams webhook, or Notify shape) containing operational context. | **MAJOR** | Check shapes on `identifier="error"` path of Try/Catch. Verify presence of notification mechanism. | Add a Notify or Mail connector shape on the catch branch. |
| **5.3** | **Dead-Letter / Reprocessing Path** | Failed documents must not simply be discarded. They should be written to a dead-letter directory, error table, or message queue for analysis and replay. | **MAJOR** | Trace terminal shapes on error path. Ensure documents are persisted before Stop shape. | Route failed payloads to an error queue, S3 bucket, or dead-letter table. |
| **5.4** | **Retry Logic for Transient Failures** | Connectors subject to network timeouts or rate-limiting should implement retry logic (either Try/Catch `retryCount > 0` or connector retry settings). Retry counts must be finite (2-3 max) to avoid execution hangs. | **MINOR** | Check `retryCount` on `<catcherrors>` or timeout/retry settings in connector operations. | Set `retryCount="2"` or `"3"` on Try/Catch for transient HTTP/REST/DB endpoints. |
| **5.5** | **Diagnostic Context in Notifications** | Error notifications (email, alert, ticket) **MUST** include all 6 key operational fields: **(1) Environment Name**, **(2) Runtime / Atom Name**, **(3) Process Name**, **(4) Execution ID**, **(5) Error Message**, and **(6) Business Identifier** (e.g. Invoice #, Order ID, Employee ID). | **MAJOR** | Inspect `<notifyMessage>` or Message shape placeholders. Verify presence of `atomName`, `executionId`, `catcherrorsmessage`, and business tracking property. | Add missing parameters to the error message template so on-call engineers can immediately diagnose the failed transaction. |
| **5.6** | **Target Downtime / Negative Scenarios** | Verify how the process treats target system outages (HTTP 502/503/504, connection timeouts, DB connection refused). Must fail safely, prevent partial corrupt commits, and trigger immediate support notifications. | **CRITICAL** | Review connector timeout settings, Try/Catch catchAll coverage, and database transaction commit boundaries. | Ensure connection exceptions route to a catch handler that stops execution cleanly and alerts without leaving hanging threads. |
| **5.7** | **Persistent Target Failures** | When target systems repeatedly reject calls or return consecutive errors, verify the process does not execute unbounded retry loops or exhaust API quotas. Ensure failed batches abort cleanly after reaching retry limits. | **MAJOR** | Check recursive sub-process calls and loop counters. Verify maximum iteration/retry limits. | Implement circuit breaking or strict loop counter guard (`DPP_RetryCount < MAX_RETRIES`) before recursing. |

---

## 6. Performance & Scalability

| # | Check Item | Description & Rationale | Severity | XML & UI Verification Method | Remediation |
|---|---|---|---|---|---|
| **6.1** | **Batch Processing & Halt Dynamics** | High-volume integrations must document and control document failure isolation: <br>• **Halt Behavior**: Does 1 failed document terminate the entire batch and halt remaining valid documents? <br>• **Isolated Processing**: Does the process isolate bad records (Try/Catch *after* Split) and continue remaining records? <br>• **Conditions**: Specify if halt occurs only on fatal connector errors vs data validation errors. | **MAJOR** | Check positioning of Try/Catch relative to Split shapes and Data Process splits. Inspect whether connectors have "Return Application Error Responses" enabled. | Place Try/Catch *downstream* of the Split shape if individual document isolation is required; document batch halt behavior in process notes. |
| **6.2** | **Data Passthrough Optimization** | Sub-processes that do not transform payload data should use **Data Passthrough** (`<passthroughaction/>`) start shapes rather than No Data + internal connector queries. | **MINOR** | Inspect start shape configuration of child processes. | Configure start shape as Data Passthrough. |
| **6.3** | **Document Cache Management** | Document caches must be cleared when no longer needed to prevent Java heap memory exhaustion in high-volume executions. | **MINOR** | Check for Document Cache Clear steps after mapping or lookup phases. | Add a Document Cache Clear step after the transformation completes. |
| **6.4** | **Non-Overlapping Schedules** | Scheduled processes must have realistic execution windows to avoid overlapping executions (or ensure `allowSimultaneous="false"`). | **MINOR** | Check `allowSimultaneous` in `<process>` options. | Set `allowSimultaneous="false"` for batch ETL processes. |

---

## 7. API Pagination & Ingestion Resilience

| # | Check Item | Description & Rationale | Severity | XML & UI Verification Method | Remediation |
|---|---|---|---|---|---|
| **7.1** | **Pagination Loop Termination** | For paginated REST/HTTP APIs, loop exit conditions must be deterministic. Verify that loops terminate when: <br>• `next_page_token` or cursor is null/empty/blank <br>• `hasNextPage == false` <br>• Received records < page size <br>• Hard safety counter (e.g. max 500 pages) reached to prevent infinite loops. | **CRITICAL** | Inspect Decision shapes, loops, and recursive sub-process calls handling pagination tokens. | Add a Decision shape checking both empty/null token and a maximum iteration counter before recursing. |
| **7.2** | **Zero-Data Source Handling** | When the source system returns zero records (empty array `[]` or no documents): <br>• **Default Expectation**: **Do nothing / graceful exit** without throwing errors, raising false alarms, or failing the process. <br>• Exception only if a business spec explicitly requires an alert for missing daily files. | **MAJOR** | Check Decision shapes following source query and `<process stopProcessingIfZeroDocuments="...">`. | Ensure process paths terminate cleanly at a Stop shape (`continue="true"`) when 0 records are returned; do not route to Exception or error alert. |


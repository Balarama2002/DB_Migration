---
name: boomi-db-migration
description: End-to-end automated and guided migration of Dell Boomi legacy Database connector components, operations, profiles, maps, caches, and processes to modern Database V2 (officialboomi-X3979C-dbv2da-prod). Includes discovery scanning, hierarchical nested subfolder audits, dependency tracking, JSON profile generation, operation mapping, map re-wiring, process connector shape updates, and multi-sheet Excel reporting.
---

# Boomi Database (Legacy) to Database V2 Migration Skill

This skill provides comprehensive instructions, architectural rules, transformation logic, and automated procedures for migrating Dell Boomi legacy **Database (Legacy)** connector components, profiles, operations, maps, document caches, and processes to modern **Database V2** (`officialboomi-X3979C-dbv2da-prod`).

---

## 1. Scope & Component Identification

The migration agent identifies and converts six primary integration artifacts:

| # | Artifact Category | Boomi Component Type | Discovery & Classification Criteria |
|---|---|---|---|
| **1** | **DB Connections** | `connector-settings` (`subType="database"`) | Legacy JDBC connection configurations. |
| **2** | **DB Operations** | `connector-action` (`subType="database"`) | SQL statements (`Standard Get`, `Standard Insert/Update/Delete`, `Dynamic Insert`, `Dynamic Update`, `Dynamic Delete`, `Stored Procedure`). |
| **3** | **DB Profiles** | `profile.db` | Column definitions, statement types, and parameters used in database actions. |
| **4** | **Maps (DB Profiles)** | `transform.map` | Maps that use DB Profiles as source (`fromProfile`) or target (`toProfile`). |
| **5** | **Document Caches** | `documentcache` | Document caches indexing data using a legacy DB Profile. |
| **6** | **DB Processes** | `process` | Processes containing DB Connector shapes OR referencing discovered Maps/Caches transitively. |

---

## 2. Hierarchical Subfolder Tree & Rollup Auditing

Boomi component metadata provides immediate folder names (`folderName`) and folder IDs (`folderId`), while the platform `Folder` object hierarchy links folders via `parentId`.

### A. Recursive Full Path Resolution
1. The migration tools query Boomi `Folder` objects across the account.
2. Build a lookup map recursively following `parentId` up to the top level root folder:
   $$\text{full\_path} = \text{resolve}(\text{parentId}) + "/" + \text{folderName}$$
3. Every component (`ComponentMetadata`) is enriched with its complete canonical `folderPath` (e.g. `TGH/Veeva/Stats9/Tecnics/#Connections`).

### B. Unified Hierarchy vs Detached Subfolders
- **Never Treat Subfolders as Detached Roots**: Subfolders (depth > 1) are never listed as independent top-level root folders.
- **Single Unified Tree**: Top-level root folders (depth 1) form the root cards. Expanding a parent folder reveals its direct subfolders with visual hierarchy guide lines, which in turn expand into further nested levels.
- **Direct vs. Rollup (Recursive) Counting**:
  - **Direct Items**: Components residing strictly at that exact folder level.
  - **Rollup Items**: Direct components + all components inside all descendant subfolders recursively.
- **Search Filtering**: When a user filters or searches by a folder name, only components and branches matching that folder are analyzed and presented.

### C. High-Performance Discovery & Batched Querying
- **Early Folder Existence Validation**: When a folder filter is provided, the agent validates whether the folder exists in the Boomi account first. If not found, it exits immediately without scanning unnecessary components.
- **Targeted Query Constraint**: Instead of fetching all components across the account and filtering in memory, the query passes `folderId` (for the target folder and its descendant subfolders) directly to Boomi API `QueryFilter`.
- **Batched Parent & Metadata Resolution**: `ComponentReference` and `ComponentMetadata` queries batch up to 40 component IDs using `OR` expressions in parallel, reducing HTTP round trips by 95% and resolving Maps, Caches, and Processes in seconds.

---

## 3. Database V2 Conversion & Modernization Rules

### A. Database V2 Connector Type
- **Connector Type ID**: `officialboomi-X3979C-dbv2da-prod`
- Modern Database V2 operations accept and produce **JSON Profiles** instead of flat column database profiles.

### B. Database Profile to JSON Profile Synthesis
For every `profile.db`, synthesize a corresponding `profile.json`:
1. Parse database fields (`DataType`: `character`, `number`, `integer`, `boolean`, `datetime`).
2. Construct hierarchical JSON structure:
   - Root: `JSONRootValue` (`key="1"`, `name="Root"`)
   - Object: `JSONObject` (`key="2"`, `name="Object"`)
   - Entries: `JSONObjectEntry` for each database field with matching data types:
     - `character` -> `character` (`ProfileCharacterFormat`)
     - `integer`/`numeric`/`float` -> `number` (`ProfileNumberFormat`)
     - `boolean` -> `boolean` (`ProfileBooleanFormat`)
     - `date`/`time`/`datetime` -> `datetime` (`ProfileDateFormat`)

### C. Operation Conversion (`connector-action`)
1. Determine Modern Action Type:
   - `Standard Get` / `select` -> `GET` (Custom Operation Type `Standard Get`)
   - `Standard Insert` / `dynamicinsert` -> `CREATE`
   - `Dynamic Update` -> `UPDATE`
   - `Dynamic Delete` -> `DELETE`
   - `Stored Procedure` -> `EXECUTE`
2. Link generated Request and Response JSON Profiles:
   - `requestProfile`: `<Request_Profile_ID>` (`requestProfileType="json"`)
   - `responseProfile`: `<Response_Profile_ID>` (`responseProfileType="json"`)

### D. Map Shape Profile & Mapping Re-Wiring (`transform.map`)
1. If the Map's source is a legacy DB profile, swap `fromProfile` to the new JSON profile ID.
2. If the Map's target is a legacy DB profile, swap `toProfile` to the new JSON profile ID.
3. Update all `<Mapping>` elements:
   - Map keys: Update `fromKeyPath` / `toKeyPath` from `*[@key='1']/*[@key='{db_field_key}']` to `*[@key='1']/*[@key='2']/*[@key='{json_field_key}']`.

### E. Process Connector Shape Re-Wiring (`process`)
1. Scan process XML for `<shape shapetype="connectoraction">`.
2. Locate `<connectoraction>` referencing the legacy `operationId`.
3. Update attributes:
   - `connectorType="officialboomi-X3979C-dbv2da-prod"`
   - `connectionId="<NEW_DB_V2_CONN_ID>"`
   - `operationId="<NEW_DB_V2_OPER_ID>"`

---

## 4. Automation Tools & Codebase Architecture

The project contains a complete agent suite in `boomi_migration_agent/`:

- `boomi_client.py`: Boomi Platform REST API client (authentication, queries, pagination, XML fetch/update)
- `migration_tools.py`: Core discovery, analysis, profile synthesis, shape rewriting & Excel report engine
- `ai_service.py`: Multi-provider decoupled AI engine (Gemini, Claude, GPT, Qwen, Mistral, DeepSeek, LLaMA)
- `server.py`: FastAPI backend with SSE streaming endpoints for real-time migration logs
- `static/index.html`: Interactive UI Hub with 6-stat grid, deep-links, and password visibility toggles
- `static/app.js`: Reactive hierarchical folder tree explorer and SSE logger
- `static/style.css`: Modern styling and interactive component indicators

### Running the Web Hub:
```bash
python -m uvicorn boomi_migration_agent.server:app --host 127.0.0.1 --port 8000 --reload
```

---

## 5. Excel Audit Report Specification (`.xlsx`)

The generated audit workbook contains 8 sheets:
1. **Summary Overview**: High-level inventory, component counts, and target migration actions.
2. **DB Connections**: Catalog of all legacy database connections.
3. **DB Operations**: Catalog of all legacy database operations.
4. **DB Profiles**: Catalog of all legacy database profiles.
5. **Maps (DB Profiles)**: Maps referencing database profiles.
6. **Document Caches**: Document caches referencing database profiles.
7. **DB Processes**: Processes with legacy database dependencies.
8. **Folder Inventory**:
   - `Folder Full Path`, `Folder Name`, `Parent Folder`, `Depth Level`
   - `Total Rollup Items` vs `Direct Items`
   - Full Rollup and Direct breakdown for all 6 component types.

---

## 6. Deep Linking to Boomi Platform

All component names throughout the UI and reports support direct navigation to the Boomi Build tab:
```
https://platform.boomi.com/AtomSphere.html#build;accountId={accountId};components={componentId}
```
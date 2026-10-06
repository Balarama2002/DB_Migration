# Boomi Legacy Database Component Audit Report

This report lists all Database (Legacy) connections, operations, profiles, and their dependent workflows.

## 1. Legacy Database Connections
| Connection Name | Component ID | Folder Path | Version |
| --- | --- | --- | --- |
| ORCL_DB_Connection | `19f5664a-d127-430e-bb66-6729a506d769` | Training-Bala Rama Krishna-Cherukuri / DataBase_Migration | 1 |


## 2. Legacy Database Operations
| Operation Name | Component ID | Folder Path | Version |
| --- | --- | --- | --- |
| Get_Opearation | `9834d403-e05a-4e3d-854c-9c6bc8ccb653` | Training-Bala Rama Krishna-Cherukuri / DataBase_Migration | 1 |
| Video13_Operation | `b5f984f2-ff17-443a-97b1-bbd5b5108666` | Training-Bala Rama Krishna-Cherukuri / DataBase_Migration | 1 |


## 3. Legacy Database Profiles
| Profile Name | Component ID | Folder Path | Version |
| --- | --- | --- | --- |
| Video13_DB_pRofile | `781dd9ee-6655-4c6a-bc3f-bbaf36f75ebe` | Training-Bala Rama Krishna-Cherukuri / DataBase_Migration | 1 |
| Get_Data_DB | `6f14259d-e688-4987-b757-ccf53c330fd4` | Training-Bala Rama Krishna-Cherukuri / DataBase_Migration | 1 |


## 4. Where Used / Dependency Mapping
### Connection: ORCL_DB_Connection (`19f5664a-d127-430e-bb66-6729a506d769`)
*   **Used By Dependencies**:
    *   **Enforce_Unique_Details** (Type: `process`, ID: `895ae8f4-744b-40bb-850f-63d22bffa180`, Folder: `DataBase_Migration`)

### Operation: Get_Opearation (`9834d403-e05a-4e3d-854c-9c6bc8ccb653`)
*   **Used By Dependencies**:
    *   **Enforce_Unique_Details** (Type: `process`, ID: `895ae8f4-744b-40bb-850f-63d22bffa180`, Folder: `DataBase_Migration`)

### Operation: Video13_Operation (`b5f984f2-ff17-443a-97b1-bbd5b5108666`)
*   **Used By Dependencies**:
    *   **Enforce_Unique_Details** (Type: `process`, ID: `895ae8f4-744b-40bb-850f-63d22bffa180`, Folder: `DataBase_Migration`)

### Profile: Video13_DB_pRofile (`781dd9ee-6655-4c6a-bc3f-bbaf36f75ebe`)
*   **Used By Dependencies**:
    *   **Enforce_Unique_Details** (Type: `process`, ID: `895ae8f4-744b-40bb-850f-63d22bffa180`, Folder: `DataBase_Migration`)
    *   **XML_DB_Video13** (Type: `transform.map`, ID: `85619fa1-e0cb-4937-985a-8896337fe6a6`, Folder: `DataBase_Migration`)
    *   **Video13_Operation** (Type: `connector-action`, ID: `b5f984f2-ff17-443a-97b1-bbd5b5108666`, Folder: `DataBase_Migration`)

### Profile: Get_Data_DB (`6f14259d-e688-4987-b757-ccf53c330fd4`)
*   **Used By Dependencies**:
    *   **Enforce_Unique_Details** (Type: `process`, ID: `895ae8f4-744b-40bb-850f-63d22bffa180`, Folder: `DataBase_Migration`)
    *   **XML_DB_Video13** (Type: `transform.map`, ID: `85619fa1-e0cb-4937-985a-8896337fe6a6`, Folder: `DataBase_Migration`)
    *   **Get_Opearation** (Type: `connector-action`, ID: `9834d403-e05a-4e3d-854c-9c6bc8ccb653`, Folder: `DataBase_Migration`)

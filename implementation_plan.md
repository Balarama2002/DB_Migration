# Boomi Legacy Database Migration Agent: Implementation Plan & Web UI Architecture

We are adding a modern, responsive Web User Interface (UI) to the Boomi Migration Agent, introducing support for decoupled AI engines (Gemini, Claude, OpenAI, Qwen, Mistral), targeted folder migration filtering, and duplicate profile creation prevention.

---

## 1. Updated Architecture Diagram (CEO / CTO Level)

```mermaid
graph TD
    %% Styling Definitions
    classDef uiStyle fill:#e0f2f1,stroke:#004d40,stroke-width:2px;
    classDef apiStyle fill:#ede7f6,stroke:#4a148c,stroke-width:2px;
    classDef agentStyle fill:#e8eaf6,stroke:#1a237e,stroke-width:2px;
    classDef providerStyle fill:#fffde7,stroke:#f57f17,stroke-width:2px;
    classDef cloudStyle fill:#e1f5fe,stroke:#01579b,stroke-width:2px;

    %% Elements
    subgraph Frontend ["1. Modern Web UI (Single Page App)"]
        UI["Web Interface<br>(Vanilla JS, CSS Grid/Flexbox, sleek dark mode)"]:::uiStyle
    end

    subgraph Backend ["2. FastAPI Server"]
        Router["API Endpoints Router<br>(/api/validate, /api/scan, /api/migrate)"]:::apiStyle
        Client["Boomi REST Client<br>(boomi_client.py)"]:::apiStyle
        MigTools["Migration Tools & Logic<br>(migration_tools.py)"]:::apiStyle
    end

    subgraph AIService ["3. Decoupled AI Provider Engine"]
        Wrapper["AI Service Wrapper<br>(ai_service.py)"]:::providerStyle
        GeminiSDK["Gemini Provider<br>(google-genai)"]:::providerStyle
        ClaudeSDK["Claude Provider<br>(anthropic)"]:::providerStyle
        OpenAISDK["OpenAI / Mistral / Qwen<br>(openai)"]:::providerStyle
    end

    subgraph BoomiCloud ["4. Boomi AtomSphere Platform"]
        API["Platform REST API<br>(ComponentMetadata, Component, Folder)"]:::cloudStyle
    end

    %% Mappings & Flow
    UI <--> Router
    Router <--> Wrapper
    Router <--> MigTools
    MigTools <--> Client
    Client <--> API

    Wrapper --> GeminiSDK
    Wrapper --> ClaudeSDK
    Wrapper --> OpenAISDK
```

---

## 2. Proposed Changes & Design Decisions

### A. Prevention of Duplicate Profiles & Operations
*   **Problem**: Retriggering the migration currently creates multiple duplicate JSON profiles (e.g. `Get_Data_DB_JSON 2`, `3`) because the script calls `/Component` (Create) unconditionally.
*   **Solution**: In `migration_tools.py`, query `ComponentMetadata` to check if a component with the same name, type, and folder path already exists on the platform. If it exists, reuse the existing component ID instead of creating a new one.

### B. Decoupled AI Engine (`ai_service.py`)
*   **Design**: Create a unified `AIService` class under `boomi_migration_agent/ai_service.py` that wraps:
    *   **Gemini** via `google-genai`
    *   **Claude** via `anthropic`
    *   **OpenAI/Qwen/Mistral** via `openai`
*   The UI will allow the user to select their provider and supply the corresponding API key, which will be routed through the server dynamically.

### C. FastAPI Backend Web Server
*   Create a web server in `boomi_migration_agent/server.py` containing endpoints:
    *   `POST /api/validate`: Validates Boomi account status by executing a query.
    *   `POST /api/scan`: Runs Phase 1 scan and extracts legacy database connection structures, operations, profiles, and where-used lists.
    *   `POST /api/migrate`: Executes the migration dynamically, supporting a targeted folder name filter. If specified, only components in that folder are migrated.
    *   `GET /api/download-report`: Generates and serves the legacy audit report.
    *   `GET /api/download-migration-report`: Serves the walkthrough completion report.

### D. Responsive Glassmorphic Web UI
*   Create an index.html and style.css for a state-of-the-art web interface with:
    *   **Theme**: Dark futuristic mode with blue/teal gradients.
    *   **Credentials Validator**: Validates account credentials instantly with clear validation messages.
    *   **Interactivity**: Expandable tables, dependency trees, targeted folder input, and a real-time console logger.
    *   **Export**: Built-in download features.

---

## 3. Verification Plan

### Automated & Manual Tests
*   Run the FastAPI server locally:
    ```powershell
    python boomi_migration_agent/server.py
    ```
*   Open the UI in the browser, input active credentials, and click "Validate".
*   Scan the components, check the folder filtering behavior, and verify the resulting connections/operations are reusable (zero duplicate creation).

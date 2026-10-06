import os
import re
import sys
import json
import time
import tempfile
import traceback
import xml.etree.ElementTree as ET
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, List

# Ensure codebase root is in Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from boomi_migration_agent.boomi_client import BoomiClient
from boomi_migration_agent.migration_tools import MigrationTools
from boomi_migration_agent.ai_service import get_ai_service

app = FastAPI(title="Boomi Database V2 Migration Hub")

@app.middleware("http")
async def add_no_cache_header(request: Request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

# Mount static files
static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

import queue
import threading

class BoomiCredentials(BaseModel):
    username: str
    api_token: str
    account_id: str
    branch: Optional[str] = None
    api_url: Optional[str] = "https://api.boomi.com"

class ScanRequest(BaseModel):
    username: str
    api_token: str
    account_id: str
    branch: Optional[str] = None
    api_url: Optional[str] = "https://api.boomi.com"
    folder_filter: Optional[str] = ""
    session_id: Optional[str] = None

class MigrationRequest(BaseModel):
    credentials: BoomiCredentials
    ai_provider: str
    ai_key: str
    folder_filter: Optional[str] = ""
    selected_process_ids: Optional[List[str]] = None
    selected_connection_ids: Optional[List[str]] = None
    selected_operation_ids: Optional[List[str]] = None
    selected_profile_ids: Optional[List[str]] = None
    selected_map_ids: Optional[List[str]] = None
    selected_cache_ids: Optional[List[str]] = None
    session_id: Optional[str] = None

# Keep scan results in memory for report generation/download per tab session and per account
SCAN_RESULTS_CACHE = {}
MIGRATION_REPORT_CACHE = {}

@app.get("/")
def read_root():
    return FileResponse(os.path.join(static_dir, "index.html"))

@app.post("/api/validate")
def validate_credentials(creds: BoomiCredentials):
    if not (creds.username or "").strip() or not (creds.api_token or "").strip() or not (creds.account_id or "").strip():
        raise HTTPException(status_code=400, detail="Please enter your Boomi Username, API Token, and Account ID.")
    branch_val = (creds.branch or "").strip()
    if not branch_val:
        raise HTTPException(status_code=400, detail="Working Branch is required. Please specify a development or feature branch (e.g. 'dbv2_merging'). Note: Direct execution on 'main' is prohibited.")
    if branch_val.lower() == "main":
        raise HTTPException(
            status_code=400,
            detail="Execution terminated: Operations on the 'main' branch are strictly prohibited to safeguard production code. Please specify a non-main development or feature branch (e.g. 'dbv2_merging')."
        )
    try:
        client = BoomiClient(
            api_url=creds.api_url,
            account_id=creds.account_id,
            username=creds.username,
            api_token=creds.api_token,
            branch=creds.branch
        )
        # Fast lightweight check on Folder object (resolves in ~1s)
        query_payload = {
            "QueryFilter": {
                "expression": {
                    "operator": "EQUALS",
                    "property": "name",
                    "argument": ["DataBase_Migration"]
                }
            }
        }
        client.query("Folder", query_payload, single_page=True)
        return {
            "status": "success",
            "message": "Connection Successful",
            "branch_name": client.branch_name,
            "branch_id": client.branch_id
        }
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        err_str = str(e)
        if "Execution terminated:" in err_str or "strictly prohibited" in err_str:
            err_msg = err_str
        elif "user has been locked" in err_str.lower():
            err_msg = "This Boomi user account is locked. Please contact your account administrator or unlock in Boomi User Management."
        elif "403" in err_str:
            err_msg = f"Access denied (HTTP 403): {err_str}"
        elif "401" in err_str:
            err_msg = "Authentication failed (HTTP 401). Please verify your Boomi Username and API Token."
        else:
            err_msg = f"Validation failed: {err_str}"
        raise HTTPException(status_code=400, detail=err_msg)

@app.post("/api/scan-stream")
def scan_components_stream(req: ScanRequest):
    if not (req.username or "").strip() or not (req.api_token or "").strip() or not (req.account_id or "").strip():
        raise HTTPException(status_code=400, detail="Missing Boomi credentials. Please enter your Username, API Token, and Account ID in Configuration Settings.")
    branch_val = (req.branch or "").strip()
    if not branch_val:
        raise HTTPException(status_code=400, detail="Working Branch is required. Please specify a development or feature branch (e.g. 'dbv2_merging'). Note: Direct execution on 'main' is prohibited.")
    if branch_val.lower() == "main":
        raise HTTPException(
            status_code=400,
            detail="Execution terminated: Operations on the 'main' branch are strictly prohibited to safeguard production code. Please specify a non-main development or feature branch (e.g. 'dbv2_merging')."
        )
    def event_stream():
        q = queue.Queue()
        
        def progress_cb(cat, count, page):
            q.put({"type": "progress", "category": cat, "count": count, "page": page})
            
        def worker():
            try:
                client = BoomiClient(
                    api_url=req.api_url,
                    account_id=req.account_id,
                    username=req.username,
                    api_token=req.api_token,
                    branch=req.branch
                )
                q.put({"type": "progress", "category": "connections", "count": f"Scoped to branch: {client.branch_name}", "page": 1})
                migrator = MigrationTools(client=client)
                results = migrator.scan_legacy_components(
                    folder_filter=req.folder_filter,
                    progress_callback=progress_cb
                )
                entry = {
                    "results": results,
                    "creds": req,
                    "account_id": req.account_id,
                    "branch": client.branch_name,
                    "branch_id": client.branch_id,
                    "folder_filter": req.folder_filter,
                    "timestamp": time.time()
                }
                if req.session_id:
                    SCAN_RESULTS_CACHE[req.session_id] = entry
                if req.account_id:
                    SCAN_RESULTS_CACHE[f"acc_{req.account_id}"] = entry
                SCAN_RESULTS_CACHE["last"] = entry
                q.put({"type": "complete", "results": results, "branch_name": client.branch_name, "branch_id": client.branch_id})
            except Exception as e:
                q.put({"type": "error", "error": str(e)})

        t = threading.Thread(target=worker)
        t.start()

        while True:
            try:
                msg = q.get(timeout=0.5)
                yield "data: " + json.dumps(msg) + "\n\n"
                if msg["type"] in ("complete", "error"):
                    break
            except queue.Empty:
                if not t.is_alive():
                    break
                yield ": keepalive\n\n"
                
    return StreamingResponse(event_stream(), media_type="text/event-stream")

@app.post("/api/scan")
def scan_components(creds: ScanRequest):
    if not (creds.username or "").strip() or not (creds.api_token or "").strip() or not (creds.account_id or "").strip():
        raise HTTPException(status_code=400, detail="Missing Boomi credentials. Please enter your Username, API Token, and Account ID.")
    branch_val = (creds.branch or "").strip()
    if not branch_val:
        raise HTTPException(status_code=400, detail="Working Branch is required. Please specify a development or feature branch (e.g. 'dbv2_merging'). Note: Direct execution on 'main' is prohibited.")
    if branch_val.lower() == "main":
        raise HTTPException(
            status_code=400,
            detail="Execution terminated: Operations on the 'main' branch are strictly prohibited to safeguard production code. Please specify a non-main development or feature branch (e.g. 'dbv2_merging')."
        )
    try:
        client = BoomiClient(
            api_url=creds.api_url,
            account_id=creds.account_id,
            username=creds.username,
            api_token=creds.api_token,
            branch=creds.branch
        )
        migrator = MigrationTools(client=client)
        results = migrator.scan_legacy_components(folder_filter=creds.folder_filter)
        
        # Cache results in memory per session and per account
        entry = {
            "results": results,
            "creds": creds,
            "account_id": creds.account_id,
            "branch": client.branch_name,
            "branch_id": client.branch_id,
            "folder_filter": creds.folder_filter,
            "timestamp": time.time()
        }
        if creds.session_id:
            SCAN_RESULTS_CACHE[creds.session_id] = entry
        if creds.account_id:
            SCAN_RESULTS_CACHE[f"acc_{creds.account_id}"] = entry
        SCAN_RESULTS_CACHE["last"] = entry
        
        return {
            "status": "success",
            "branch_name": client.branch_name,
            "branch_id": client.branch_id,
            "connections": results.get("connections", []),
            "operations": results.get("operations", []),
            "profiles": results.get("profiles", []),
            "maps": results.get("maps", []),
            "caches": results.get("caches", []),
            "processes": results.get("processes", [])
        }
    except Exception as e:
        raise HTTPException(status_code=400 if "Execution terminated" in str(e) else 500, detail=f"Scan failed: {str(e)}")

class ComponentUsageRequest(BaseModel):
    credentials: BoomiCredentials
    component_id: str
    version: Optional[int] = 1

@app.post("/api/component-usage")
def get_component_usage(req: ComponentUsageRequest):
    try:
        creds = req.credentials
        client = BoomiClient(
            api_url=creds.api_url,
            account_id=creds.account_id,
            username=creds.username,
            api_token=creds.api_token,
            branch=creds.branch
        )
        migrator = MigrationTools(client=client)
        refs = migrator.find_where_used(req.component_id, req.version)
        ref_by = refs.get("referenced_by", [])
        
        processes = []
        for ref in ref_by:
            parent_id = ref.get("parentComponentId")
            details = migrator.resolve_component_details(parent_id)
            if details:
                processes.append({
                    "id": parent_id,
                    "name": details.get("name", f"Component {parent_id}"),
                    "type": details.get("type", "unknown"),
                    "folder": details.get("folderName", "Unknown Folder")
                })
            else:
                processes.append({
                    "id": parent_id,
                    "name": f"Parent {parent_id}",
                    "type": "unknown",
                    "folder": "Unknown"
                })
        return {"status": "success", "used_in": processes}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/download-report-excel")
def download_report_excel(session_id: Optional[str] = None, account_id: Optional[str] = None):
    entry = None
    if session_id and session_id in SCAN_RESULTS_CACHE:
        entry = SCAN_RESULTS_CACHE[session_id]
    elif account_id and f"acc_{account_id}" in SCAN_RESULTS_CACHE:
        entry = SCAN_RESULTS_CACHE[f"acc_{account_id}"]
    elif "last" in SCAN_RESULTS_CACHE:
        entry = SCAN_RESULTS_CACHE["last"]

    if not entry or not entry.get("results"):
        raise HTTPException(status_code=400, detail="No scan results available for this session or account. Please run a scan first.")
        
    results = entry["results"]
    creds = entry["creds"]
    acc_id = account_id or entry.get("account_id") or getattr(creds, "account_id", "account")
    
    client = BoomiClient(
        api_url=getattr(creds, "api_url", "https://api.boomi.com"),
        account_id=getattr(creds, "account_id", acc_id),
        username=getattr(creds, "username", ""),
        api_token=getattr(creds, "api_token", ""),
        branch=getattr(creds, "branch", None) or entry.get("branch")
    )
    migrator = MigrationTools(client=client)
    
    reports_dir = os.path.join(tempfile.gettempdir(), "boomi_reports")
    os.makedirs(reports_dir, exist_ok=True)
    file_key = f"{acc_id}_{session_id or 'default'}_{int(time.time())}"
    temp_path = os.path.join(reports_dir, f"legacy_db_audit_report_{file_key}.xlsx")
    
    migrator.generate_audit_report_excel(results, file_path=temp_path, max_where_used=50)
    
    download_filename = f"legacy_db_audit_report_{acc_id}.xlsx"
    return FileResponse(
        temp_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=download_filename
    )

@app.get("/api/download-report")
def download_report(session_id: Optional[str] = None, account_id: Optional[str] = None):
    entry = None
    if session_id and session_id in SCAN_RESULTS_CACHE:
        entry = SCAN_RESULTS_CACHE[session_id]
    elif account_id and f"acc_{account_id}" in SCAN_RESULTS_CACHE:
        entry = SCAN_RESULTS_CACHE[f"acc_{account_id}"]
    elif "last" in SCAN_RESULTS_CACHE:
        entry = SCAN_RESULTS_CACHE["last"]

    if not entry or not entry.get("results"):
        raise HTTPException(status_code=400, detail="No scan results available for this session or account. Please run a scan first.")
        
    results = entry["results"]
    creds = entry["creds"]
    acc_id = account_id or entry.get("account_id") or getattr(creds, "account_id", "account")
    
    client = BoomiClient(
        api_url=getattr(creds, "api_url", "https://api.boomi.com"),
        account_id=getattr(creds, "account_id", acc_id),
        username=getattr(creds, "username", ""),
        api_token=getattr(creds, "api_token", ""),
        branch=getattr(creds, "branch", None) or entry.get("branch")
    )
    migrator = MigrationTools(client=client)
    report_content = migrator.generate_audit_report_md(results)
    
    reports_dir = os.path.join(tempfile.gettempdir(), "boomi_reports")
    os.makedirs(reports_dir, exist_ok=True)
    file_key = f"{acc_id}_{session_id or 'default'}_{int(time.time())}"
    temp_path = os.path.join(reports_dir, f"legacy_db_audit_report_{file_key}.md")
    
    with open(temp_path, "w", encoding="utf-8") as f:
        f.write(report_content)
        
    download_filename = f"legacy_db_audit_report_{acc_id}.md"
    return FileResponse(
        temp_path,
        media_type="text/markdown",
        filename=download_filename
    )

@app.post("/api/migrate")
def migrate_components(req: MigrationRequest):
    creds = req.credentials
    if not (creds.username or "").strip() or not (creds.api_token or "").strip() or not (creds.account_id or "").strip():
        raise HTTPException(status_code=400, detail="Missing Boomi credentials. Please enter your Username, API Token, and Account ID.")
    branch_val = (creds.branch or "").strip()
    if not branch_val:
        raise HTTPException(status_code=400, detail="Working Branch is required. Please specify a development or feature branch (e.g. 'dbv2_merging'). Note: Direct execution on 'main' is prohibited.")
    if branch_val.lower() == "main":
        raise HTTPException(
            status_code=400,
            detail="Execution terminated: Operations on the 'main' branch are strictly prohibited to safeguard production code. Please specify a non-main development or feature branch (e.g. 'dbv2_merging')."
        )
    def event_stream():
        yield "data: " + json.dumps({"log": "--- Starting Boomi Database V2 Migration ---"}) + "\n\n"
        
        try:
            client = BoomiClient(
                api_url=creds.api_url,
                account_id=creds.account_id,
                username=creds.username,
                api_token=creds.api_token,
                branch=creds.branch
            )
            migrator = MigrationTools(client=client)
            
            yield "data: " + json.dumps({"log": f"Active Working Branch: {client.branch_name} (ID: {client.branch_id}) [Main Branch Protection: ACTIVE]"}) + "\n\n"
            
            # Decoupled AI service setup
            ai_provider = req.ai_provider
            yield "data: " + json.dumps({"log": f"AI Engine initialized: {ai_provider.upper()}"}) + "\n\n"
            
            migration_summary = []
            migrated_conns = {}
            migrated_ops = {}
            migrated_profiles = {}

            sel_procs = req.selected_process_ids or []
            sel_conns = req.selected_connection_ids or []
            sel_ops = req.selected_operation_ids or []
            sel_profs = req.selected_profile_ids or []
            sel_maps = req.selected_map_ids or []
            sel_caches = req.selected_cache_ids or []
            has_targeted_items = bool(sel_procs or sel_conns or sel_ops or sel_profs or sel_maps or sel_caches)

            def do_migrate_conn(c_id, fallback_folder=""):
                if c_id in migrated_conns:
                    return migrated_conns[c_id]
                conn_xml = client.get_component_xml(c_id)
                conn_root = ET.fromstring(conn_xml)
                if conn_root.find('.//DatabaseConnectionSettings') is None and 'subType="database"' not in conn_xml:
                    return None
                conn_name = conn_root.get("name") or f"DB_Connection_{c_id[:8]}"
                conn_folder_id = conn_root.get("folderId") or fallback_folder
                name_v2 = f"{conn_name}_V2"
                v2_xml = migrator.assemble_dbv2_connection_xml(conn_xml, conn_folder_id, name_v2)
                v2_id = client.get_or_create_component(name_v2, "connector-settings", conn_folder_id, v2_xml)
                migrated_conns[c_id] = v2_id
                migration_summary.append({
                    "type": "Connection",
                    "old_name": conn_name,
                    "old_id": c_id,
                    "new_name": name_v2,
                    "new_id": v2_id,
                    "status": "Success"
                })
                return v2_id

            def do_migrate_profile(p_id, fallback_folder=""):
                if p_id in migrated_profiles:
                    return migrated_profiles[p_id]
                prof_xml = client.get_component_xml(p_id)
                prof_root = ET.fromstring(prof_xml)
                prof_name = prof_root.get("name") or f"DB_Profile_{p_id[:8]}"
                folder_id = prof_root.get("folderId") or fallback_folder
                prof_meta = migrator.parse_profile_db_sql(prof_xml)

                req_id = None
                resp_id = None
                req_xml = None
                resp_xml = None

                if prof_meta["statementType"] == "select":
                    if prof_meta["params"]:
                        req_name = f"{prof_name}_Req_JSON"
                        req_xml = migrator.generate_json_profile_xml(req_name, prof_meta["params"], folder_id)
                        req_id = client.get_or_create_component(req_name, "profile.json", folder_id, req_xml)
                        migration_summary.append({
                            "type": "Profile",
                            "old_name": f"{prof_name} (Param)",
                            "old_id": p_id,
                            "new_name": req_name,
                            "new_id": req_id,
                            "status": "Success (JSON Profile)"
                        })
                    if prof_meta["fields"]:
                        resp_name = f"{prof_name}_Resp_JSON"
                        resp_xml = migrator.generate_json_profile_xml(resp_name, prof_meta["fields"], folder_id)
                        resp_id = client.get_or_create_component(resp_name, "profile.json", folder_id, resp_xml)
                        migration_summary.append({
                            "type": "Profile",
                            "old_name": prof_name,
                            "old_id": p_id,
                            "new_name": resp_name,
                            "new_id": resp_id,
                            "status": "Success (JSON Profile)"
                        })
                else:
                    st_type = prof_meta.get("statementType", "")
                    if st_type == "dynamicupdate":
                        # Only dynamicupdate combines SET fields and WHERE condition fields
                        write_fields = list(prof_meta.get("fields", []))
                        for p in prof_meta.get("params", []):
                            if not any(f.get("name") == p.get("name") for f in write_fields):
                                write_fields.append(p)
                    elif st_type == "dynamicdelete":
                        # Delete only uses condition parameters
                        write_fields = list(prof_meta.get("params", []))
                    else:
                        # Dynamic Insert or Standard Insert: only insertion fields
                        write_fields = list(prof_meta.get("fields", []))

                    if write_fields:
                        req_name = f"{prof_name}_Req_JSON"
                        req_xml = migrator.generate_json_profile_xml(req_name, write_fields, folder_id)
                        req_id = client.get_or_create_component(req_name, "profile.json", folder_id, req_xml)
                        migration_summary.append({
                            "type": "Profile",
                            "old_name": prof_name,
                            "old_id": p_id,
                            "new_name": req_name,
                            "new_id": req_id,
                            "status": "Success (JSON Profile)"
                        })

                    # Also create standard response profile for DB V2 write actions (UPDATE, CREATE)
                    t_name = prof_meta.get("tableName", "table")
                    act_name = "UPDATE" if st_type == "dynamicupdate" else ("DELETE" if st_type == "dynamicdelete" else "CREATE")
                    resp_name, resp_xml_gen = migrator.generate_dbv2_standard_response_profile(t_name, folder_id, act_name)
                    resp_id = client.get_or_create_component(resp_name, "profile.json", folder_id, resp_xml_gen)
                    resp_xml = resp_xml_gen

                p_info = {
                    "legacy_profile_id": p_id,
                    "new_profile_id": resp_id or req_id,
                    "request_profile_id": req_id,
                    "response_profile_id": resp_id,
                    "legacy_profile_xml": prof_xml,
                    "new_profile_xml": resp_xml or req_xml
                }
                migrated_profiles[p_id] = p_info
                return p_info

            def do_migrate_operation(o_id, fallback_folder="", explicit_conn_id=None):
                if o_id in migrated_ops:
                    return migrated_ops[o_id]
                oper_xml = client.get_component_xml(o_id)
                clean_oper_xml = re.sub(r'<\?xml[^>]*\?>', '', oper_xml).strip()
                oper_root = ET.fromstring(clean_oper_xml)
                op_name = oper_root.get("name") or f"DB_Operation_{o_id[:8]}"
                op_folder_id = oper_root.get("folderId") or fallback_folder
                name_v2 = f"{op_name}_V2"

                profile_el = oper_root.find('.//ReadProfile') or oper_root.find('.//WriteProfile') or oper_root.find('.//*[@profileId]')
                legacy_prof_id = None
                req_prof_id = None
                resp_prof_id = None
                prof_xml = None
                req_xml = None
                resp_xml = None
                prof_meta = None

                if profile_el is not None:
                    legacy_prof_id = profile_el.get("profileId")
                    if legacy_prof_id:
                        p_info = do_migrate_profile(legacy_prof_id, op_folder_id)
                        prof_xml = p_info.get("legacy_profile_xml")
                        prof_meta = migrator.parse_profile_db_sql(prof_xml)
                        if prof_meta["statementType"] == "select":
                            resp_prof_id = p_info.get("new_profile_id")
                            if prof_meta.get("params"):
                                for s in migration_summary:
                                    if s.get("type") == "Profile" and s.get("old_id") == legacy_prof_id and "(Param)" in s.get("old_name", ""):
                                        req_prof_id = s.get("new_id")
                        else:
                            req_prof_id = p_info.get("request_profile_id") or p_info.get("new_profile_id")
                            resp_prof_id = p_info.get("response_profile_id")

                v2_conn_id = explicit_conn_id
                if not v2_conn_id:
                    v2_conn_id = list(migrated_conns.values())[0] if migrated_conns else "13243dc8-3802-47f0-a7ac-0c173ae06df3"

                sql_str = prof_meta["sql"] if prof_meta else ""
                stmt_type = prof_meta["statementType"] if prof_meta else "dynamic"
                t_name = prof_meta.get("tableName", "") if prof_meta else ""
                v2_oper_xml = migrator.assemble_dbv2_operation_xml(
                    name_v2, v2_conn_id, sql_str, stmt_type,
                    req_prof_id, resp_prof_id, op_folder_id,
                    table_name=t_name
                )
                v2_op_id = client.get_or_create_component(name_v2, "connector-action", op_folder_id, v2_oper_xml)
                target_action = "GET" if stmt_type == "select" else ("CREATE" if stmt_type in ["dynamicinsert", "standardinsertupdatedelete"] else "UPDATE")
                op_info = {
                    "new_oper_id": v2_op_id,
                    "legacy_profile_id": legacy_prof_id,
                    "new_profile_id": resp_prof_id or req_prof_id,
                    "legacy_profile_xml": prof_xml,
                    "new_profile_xml": resp_xml or req_xml,
                    "action_type": target_action
                }
                migrated_ops[o_id] = op_info
                migration_summary.append({
                    "type": "Operation",
                    "old_name": op_name,
                    "old_id": o_id,
                    "new_name": name_v2,
                    "new_id": v2_op_id,
                    "status": "Success"
                })
                return op_info

            def do_update_map(m_id):
                m_xml = client.get_component_xml(m_id)
                m_root = ET.fromstring(m_xml)
                m_comp_el = m_root.find('.//Map')
                if m_comp_el is None:
                    return False
                m_from = m_comp_el.get("fromProfile")
                m_to = m_comp_el.get("toProfile")
                m_name = m_root.get("name") or m_id

                all_prof_infos = list(migrated_ops.values()) + list(migrated_profiles.values())
                
                for p_cand in [m_from, m_to]:
                    if p_cand and p_cand not in [pi.get("legacy_profile_id") for pi in all_prof_infos]:
                        try:
                            px = client.get_component_xml(p_cand)
                            if 'subType="database"' in px or '<DatabaseProfile' in px:
                                pi = do_migrate_profile(p_cand, m_root.get("folderId") or "")
                                all_prof_infos.append(pi)
                        except Exception:
                            pass

                for p_info in all_prof_infos:
                    leg_p = p_info.get("legacy_profile_id")
                    new_p = p_info.get("new_profile_id")
                    leg_pxml = p_info.get("legacy_profile_xml")
                    new_pxml = p_info.get("new_profile_xml")
                    if leg_p and new_p and leg_pxml and new_pxml and (m_from == leg_p or m_to == leg_p):
                        upd_map_xml = migrator.update_map_for_db_profile(
                            m_xml, leg_p, new_p, leg_pxml, new_pxml
                        )
                        client.update_component(m_id, upd_map_xml)
                        migration_summary.append({
                            "type": "Map",
                            "old_name": m_name,
                            "old_id": m_id,
                            "new_name": m_name,
                            "new_id": m_id,
                            "status": "Success (Updated to JSON Profile)"
                        })
                        return True
                return False

            def do_update_cache(ca_id):
                c_xml = client.get_component_xml(ca_id)
                c_root = ET.fromstring(c_xml)
                c_name = c_root.get("name") or ca_id
                cache_el = c_root.find('.//DocumentCache') or c_root.find('.//*[@profileId]')
                if cache_el is None:
                    return False
                leg_p = cache_el.get("profileId")
                all_prof_infos = list(migrated_ops.values()) + list(migrated_profiles.values())
                
                if leg_p and leg_p not in [pi.get("legacy_profile_id") for pi in all_prof_infos]:
                    try:
                        px = client.get_component_xml(leg_p)
                        if 'subType="database"' in px or '<DatabaseProfile' in px:
                            pi = do_migrate_profile(leg_p, c_root.get("folderId") or "")
                            all_prof_infos.append(pi)
                    except Exception:
                        pass

                for p_info in all_prof_infos:
                    if p_info.get("legacy_profile_id") == leg_p and p_info.get("new_profile_id"):
                        new_p = p_info["new_profile_id"]
                        cache_el.set("profileId", new_p)
                        if cache_el.get("profileType"):
                            cache_el.set("profileType", "profile.json")
                        upd_cxml = ET.tostring(c_root, encoding='utf-8').decode('utf-8')
                        client.update_component(ca_id, upd_cxml)
                        migration_summary.append({
                            "type": "Cache",
                            "old_name": c_name,
                            "old_id": ca_id,
                            "new_name": c_name,
                            "new_id": ca_id,
                            "status": "Success (Updated to JSON Profile)"
                        })
                        return True
                return False

            # MODE A: TARGETED COMPONENT MIGRATION (Checkboxes selected)
            if has_targeted_items:
                total_targeted = len(sel_conns) + len(sel_ops) + len(sel_profs) + len(sel_maps) + len(sel_caches) + len(sel_procs)
                yield "data: " + json.dumps({
                    "log": f"🎯 Targeted Migration Mode: Migrating {total_targeted} selected component(s)... "
                           f"({len(sel_conns)} conns, {len(sel_ops)} ops, {len(sel_profs)} profs, {len(sel_maps)} maps, {len(sel_caches)} caches, {len(sel_procs)} procs)"
                }) + "\n\n"

                # 1. Migrate explicitly selected Connections
                if sel_conns:
                    yield "data: " + json.dumps({"log": f"--- Stage 1: Migrating {len(sel_conns)} Connection(s) ---"}) + "\n\n"
                    for c_id in sel_conns:
                        try:
                            v2_id = do_migrate_conn(c_id)
                            if v2_id:
                                yield "data: " + json.dumps({"log": f"✅ Migrated DB Connection: {c_id} -> {v2_id}"}) + "\n\n"
                        except Exception as ce:
                            yield "data: " + json.dumps({"log": f"⚠️ Error migrating Connection {c_id}: {str(ce)}"}) + "\n\n"

                # 2. Migrate explicitly selected Profiles & Operations
                if sel_profs:
                    yield "data: " + json.dumps({"log": f"--- Stage 2A: Migrating {len(sel_profs)} Profile(s) ---"}) + "\n\n"
                    for p_id in sel_profs:
                        try:
                            p_info = do_migrate_profile(p_id)
                            if p_info:
                                yield "data: " + json.dumps({"log": f"✅ Migrated DB Profile: {p_id} -> JSON Profile {p_info.get('new_profile_id')}"}) + "\n\n"
                        except Exception as pe:
                            yield "data: " + json.dumps({"log": f"⚠️ Error migrating Profile {p_id}: {str(pe)}"}) + "\n\n"

                if sel_ops:
                    yield "data: " + json.dumps({"log": f"--- Stage 2B: Migrating {len(sel_ops)} Operation(s) ---"}) + "\n\n"
                    for o_id in sel_ops:
                        try:
                            op_info = do_migrate_operation(o_id)
                            if op_info:
                                yield "data: " + json.dumps({"log": f"✅ Migrated DB Operation: {o_id} -> DB V2 Operation {op_info.get('new_oper_id')}"}) + "\n\n"
                        except Exception as oe:
                            yield "data: " + json.dumps({"log": f"⚠️ Error migrating Operation {o_id}: {str(oe)}"}) + "\n\n"

                # 3. Migrate explicitly selected Maps & Caches
                if sel_maps:
                    yield "data: " + json.dumps({"log": f"--- Stage 3A: Updating {len(sel_maps)} Map(s) ---"}) + "\n\n"
                    for m_id in sel_maps:
                        try:
                            ok = do_update_map(m_id)
                            if ok:
                                yield "data: " + json.dumps({"log": f"✅ Updated Map {m_id} to DB V2 profile."}) + "\n\n"
                            else:
                                yield "data: " + json.dumps({"log": f"ℹ️ Map {m_id} checked, no matching DB profile updates needed."}) + "\n\n"
                        except Exception as me:
                            yield "data: " + json.dumps({"log": f"⚠️ Error updating Map {m_id}: {str(me)}"}) + "\n\n"

                if sel_caches:
                    yield "data: " + json.dumps({"log": f"--- Stage 3B: Updating {len(sel_caches)} Document Cache(s) ---"}) + "\n\n"
                    for ca_id in sel_caches:
                        try:
                            ok = do_update_cache(ca_id)
                            if ok:
                                yield "data: " + json.dumps({"log": f"✅ Updated Document Cache {ca_id} to DB V2 profile."}) + "\n\n"
                            else:
                                yield "data: " + json.dumps({"log": f"ℹ️ Cache {ca_id} checked, no matching DB profile updates needed."}) + "\n\n"
                        except Exception as cae:
                            yield "data: " + json.dumps({"log": f"⚠️ Error updating Cache {ca_id}: {str(cae)}"}) + "\n\n"

                # 4. Migrate & Re-wire explicitly selected Processes
                if sel_procs:
                    yield "data: " + json.dumps({"log": f"--- Stage 4: Re-wiring {len(sel_procs)} Process(es) ---"}) + "\n\n"
                    for proc_id in sel_procs:
                        try:
                            proc_xml = client.get_component_xml(proc_id)
                            root = ET.fromstring(proc_xml)
                            proc_name = root.get("name") or proc_id
                            proc_folder_id = root.get("folderId") or ""
                            yield "data: " + json.dumps({"log": f"🔍 Analyzing Process: '{proc_name}' ({proc_id})..."}) + "\n\n"

                            # Find all connector actions in the process
                            shapes = root.findall('.//shapes/shape[@shapetype="connectoraction"]')
                            start_shape = root.find('.//shapes/shape[@shapetype="start"]//connectoraction')
                            all_actions = []
                            if start_shape is not None:
                                all_actions.append(start_shape)
                            for s in shapes:
                                a = s.find('.//connectoraction')
                                if a is not None:
                                    all_actions.append(a)

                            found_db_actions = []
                            for act in all_actions:
                                c_id = act.get("connectionId")
                                o_id = act.get("operationId")
                                c_type = (act.get("connectorType") or "").lower()
                                if not c_id or not o_id:
                                    continue
                                if c_type in ["disk-sdk", "disk", "http", "https", "sftp", "ftp", "mail", "jms", "as2", "tradingpartner", "officialboomi-x3979c-dbv2da-prod"]:
                                    continue
                                if c_type == "database":
                                    found_db_actions.append((c_id, o_id, c_type))
                                else:
                                    try:
                                        chk_xml = client.get_component_xml(c_id)
                                        if 'subType="database"' in chk_xml or '<DatabaseConnectionSettings' in chk_xml:
                                            found_db_actions.append((c_id, o_id, "database"))
                                    except Exception:
                                        pass

                            if not found_db_actions:
                                yield "data: " + json.dumps({"log": f"ℹ️ No legacy database connector actions found in process '{proc_name}'."}) + "\n\n"
                            else:
                                yield "data: " + json.dumps({"log": f"Found {len(found_db_actions)} database action(s) in process '{proc_name}'."}) + "\n\n"

                                # Auto-migrate dependent connections
                                for c_id, o_id, _ in found_db_actions:
                                    if c_id not in migrated_conns:
                                        v2_c = do_migrate_conn(c_id, proc_folder_id)
                                        if v2_c:
                                            yield "data: " + json.dumps({"log": f"✅ Migrated dependent DB Connection: {c_id} -> {v2_c}"}) + "\n\n"

                                # Auto-migrate dependent operations
                                for c_id, o_id, _ in found_db_actions:
                                    if o_id not in migrated_ops:
                                        v2_c = migrated_conns.get(c_id)
                                        op_inf = do_migrate_operation(o_id, proc_folder_id, explicit_conn_id=v2_c)
                                        if op_inf:
                                            yield "data: " + json.dumps({"log": f"✅ Migrated dependent DB Operation: {o_id} -> {op_inf.get('new_oper_id')}"}) + "\n\n"

                                # Update any map shapes in process
                                map_shapes = root.findall('.//shapes/shape[@shapetype="map"]')
                                for ms in map_shapes:
                                    m_el = ms.find('.//map')
                                    if m_el is not None and m_el.get("mapId"):
                                        try:
                                            do_update_map(m_el.get("mapId"))
                                        except Exception as me:
                                            yield "data: " + json.dumps({"log": f"⚠️ Could not update Map {m_el.get('mapId')}: {str(me)}"}) + "\n\n"

                                # Re-wire process XML connector shapes
                                yield "data: " + json.dumps({"log": f"Re-wiring connector shapes in process '{proc_name}'..."}) + "\n\n"
                                updated_proc_xml = proc_xml
                                for c_id, o_id, _ in found_db_actions:
                                    v2_conn_id = migrated_conns.get(c_id, "")
                                    v2_op_info = migrated_ops.get(o_id)
                                    if v2_conn_id and v2_op_info:
                                        updated_proc_xml = migrator.migrate_process_connector_shapes(
                                            updated_proc_xml, c_id, v2_conn_id, o_id, v2_op_info["new_oper_id"],
                                            target_action_type=v2_op_info.get("action_type")
                                        )

                                client.update_component(proc_id, updated_proc_xml)
                                yield "data: " + json.dumps({"log": f"🚀 Successfully re-wired process '{proc_name}' ({proc_id}) to DB V2 on platform!"}) + "\n\n"
                                migration_summary.append({
                                    "type": "Process",
                                    "old_name": proc_name,
                                    "old_id": proc_id,
                                    "new_name": f"{proc_name} (V2 Re-wired)",
                                    "new_id": proc_id,
                                    "status": "Success"
                                })
                        except Exception as p_err:
                            yield "data: " + json.dumps({"log": f"❌ Error migrating process {proc_id}: {str(p_err)}", "status": "error"}) + "\n\n"

            # MODE B: FOLDER / ALL MIGRATION (No individual checkboxes checked)
            else:
                yield "data: " + json.dumps({"log": "Scanning legacy database components on Boomi platform..."}) + "\n\n"
                scan_results = migrator.scan_legacy_components(folder_filter=req.folder_filter)
                
                folder_filter = req.folder_filter.strip().lower()
                if folder_filter:
                    yield "data: " + json.dumps({"log": f"Applying folder filter: '{req.folder_filter}'"}) + "\n\n"
                    scan_results["connections"] = [c for c in scan_results["connections"] if folder_filter in c.get("folderPath", "").lower()]
                    scan_results["operations"] = [o for o in scan_results["operations"] if folder_filter in o.get("folderPath", "").lower()]
                    scan_results["profiles"] = [p for p in scan_results["profiles"] if folder_filter in p.get("folderPath", "").lower()]
                    
                yield "data: " + json.dumps({
                    "log": f"Components to migrate: {len(scan_results['connections'])} connections, "
                           f"{len(scan_results['operations'])} operations, {len(scan_results['profiles'])} profiles."
                }) + "\n\n"
                
                # 1. Migrate Connections
                for conn in scan_results["connections"]:
                    legacy_id = conn["componentId"]
                    name_v2 = f"{conn['name']}_V2"
                    yield "data: " + json.dumps({"log": f"Migrating Connection: {conn['name']} ({legacy_id})..."}) + "\n\n"
                    legacy_xml = client.get_component_xml(legacy_id)
                    conn_root = ET.fromstring(legacy_xml)
                    if conn_root.find('.//DatabaseConnectionSettings') is None:
                        yield "data: " + json.dumps({"log": f"⚠️ Component {conn['name']} does not contain DatabaseConnectionSettings. Skipping."}) + "\n\n"
                        continue
                    folder_id = conn["folderId"]
                    v2_xml = migrator.assemble_dbv2_connection_xml(legacy_xml, folder_id, name_v2)
                    v2_id = client.get_or_create_component(name_v2, "connector-settings", folder_id, v2_xml)
                    migrated_conns[legacy_id] = v2_id
                    yield "data: " + json.dumps({"log": f"Connection V2 ID: {v2_id} (Reused/Created)"}) + "\n\n"
                    migration_summary.append({
                        "type": "Connection",
                        "old_name": conn["name"],
                        "old_id": legacy_id,
                        "new_name": name_v2,
                        "new_id": v2_id,
                        "status": "Success"
                    })
                    
                conn_v2_id = list(migrated_conns.values())[0] if migrated_conns else "13243dc8-3802-47f0-a7ac-0c173ae06df3"
                
                # 2. Migrate Operations & Profiles
                for op_meta in scan_results["operations"]:
                    legacy_id = op_meta["componentId"]
                    name_v2 = f"{op_meta['name']}_V2"
                    yield "data: " + json.dumps({"log": f"Migrating Operation: {op_meta['name']} ({legacy_id})..."}) + "\n\n"
                    oper_xml = client.get_component_xml(legacy_id)
                    clean_oper_xml = re.sub(r'<\?xml[^>]*\?>', '', oper_xml).strip()
                    oper_root = ET.fromstring(clean_oper_xml)
                    folder_id = op_meta["folderId"]
                    
                    profile_el = oper_root.find('.//ReadProfile') or oper_root.find('.//WriteProfile') or oper_root.find('.//*[@profileId]')
                    if profile_el is None:
                        yield "data: " + json.dumps({"log": f"Skipping operation {op_meta['name']} - no database profile reference found."}) + "\n\n"
                        continue
                        
                    legacy_profile_id = profile_el.get("profileId")
                    legacy_profile_xml = client.get_component_xml(legacy_profile_id)
                    profile_meta = migrator.parse_profile_db_sql(legacy_profile_xml)
                    
                    req_profile_id = None
                    resp_profile_id = None
                    req_xml = None
                    resp_xml = None
                    if profile_meta["statementType"] == "select":
                        if profile_meta["params"]:
                            req_name = f"{op_meta['name']}_Req_JSON"
                            req_xml = migrator.generate_json_profile_xml(req_name, profile_meta["params"], folder_id)
                            req_profile_id = client.get_or_create_component(req_name, "profile.json", folder_id, req_xml)
                            yield "data: " + json.dumps({"log": f"Request JSON Profile: {req_profile_id}"}) + "\n\n"
                            migration_summary.append({
                                "type": "Profile",
                                "old_name": f"{profile_meta.get('name', legacy_profile_id)} (Param)",
                                "old_id": legacy_profile_id,
                                "new_name": req_name,
                                "new_id": req_profile_id,
                                "status": "Success (JSON Profile)"
                            })
                        if profile_meta["fields"]:
                            resp_name = f"{op_meta['name']}_Resp_JSON"
                            resp_xml = migrator.generate_json_profile_xml(resp_name, profile_meta["fields"], folder_id)
                            resp_profile_id = client.get_or_create_component(resp_name, "profile.json", folder_id, resp_xml)
                            yield "data: " + json.dumps({"log": f"Response JSON Profile: {resp_profile_id}"}) + "\n\n"
                            migration_summary.append({
                                "type": "Profile",
                                "old_name": profile_meta.get('name', legacy_profile_id),
                                "old_id": legacy_profile_id,
                                "new_name": resp_name,
                                "new_id": resp_profile_id,
                                "status": "Success (JSON Profile)"
                            })
                    else:
                        st_type = profile_meta.get("statementType", "")
                        if st_type == "dynamicupdate":
                            # Only dynamicupdate combines SET fields and WHERE condition fields
                            write_fields = list(profile_meta.get("fields", []))
                            for p in profile_meta.get("params", []):
                                if not any(f.get("name") == p.get("name") for f in write_fields):
                                    write_fields.append(p)
                        elif st_type == "dynamicdelete":
                            # Delete only uses condition parameters
                            write_fields = list(profile_meta.get("params", []))
                        else:
                            # Dynamic Insert or Standard Insert: only insertion fields
                            write_fields = list(profile_meta.get("fields", []))

                        if write_fields:
                            req_name = f"{op_meta['name']}_Req_JSON"
                            req_xml = migrator.generate_json_profile_xml(req_name, write_fields, folder_id)
                            req_profile_id = client.get_or_create_component(req_name, "profile.json", folder_id, req_xml)
                            yield "data: " + json.dumps({"log": f"Request JSON Profile: {req_profile_id}"}) + "\n\n"
                            migration_summary.append({
                                "type": "Profile",
                                "old_name": profile_meta.get('name', legacy_profile_id),
                                "old_id": legacy_profile_id,
                                "new_name": req_name,
                                "new_id": req_profile_id,
                                "status": "Success (JSON Profile)"
                            })

                        # Also create standard response profile for DB V2 write actions (UPDATE, CREATE)
                        t_name = profile_meta.get("tableName", "table")
                        act_name = "UPDATE" if st_type == "dynamicupdate" else ("DELETE" if st_type == "dynamicdelete" else "CREATE")
                        resp_name, resp_xml_gen = migrator.generate_dbv2_standard_response_profile(t_name, folder_id, act_name)
                        resp_profile_id = client.get_or_create_component(resp_name, "profile.json", folder_id, resp_xml_gen)
                            
                    t_name = profile_meta.get("tableName", "") if profile_meta else ""
                    v2_oper_xml = migrator.assemble_dbv2_operation_xml(
                        name_v2, conn_v2_id, profile_meta["sql"], profile_meta["statementType"],
                        req_profile_id, resp_profile_id, folder_id,
                        table_name=t_name
                    )
                    v2_op_id = client.get_or_create_component(name_v2, "connector-action", folder_id, v2_oper_xml)
                    target_act = "GET" if profile_meta["statementType"] == "select" else ("CREATE" if profile_meta["statementType"] in ["dynamicinsert", "standardinsertupdatedelete"] else "UPDATE")
                    migrated_ops[legacy_id] = {
                        "new_oper_id": v2_op_id,
                        "legacy_profile_id": legacy_profile_id,
                        "new_profile_id": resp_profile_id or req_profile_id,
                        "legacy_profile_xml": legacy_profile_xml,
                        "new_profile_xml": resp_xml or req_xml,
                        "action_type": target_act
                    }
                    yield "data: " + json.dumps({"log": f"Created Operation V2 ID: {v2_op_id}"}) + "\n\n"
                    migration_summary.append({
                        "type": "Operation",
                        "old_name": op_meta["name"],
                        "old_id": legacy_id,
                        "new_name": name_v2,
                        "new_id": v2_op_id,
                        "status": "Success"
                    })

                # 3. Migrate / Update Maps in folder
                maps_to_migrate = scan_results.get("maps", [])
                for map_meta in maps_to_migrate:
                    map_id = map_meta.get("componentId")
                    map_name = map_meta.get("name") or map_id
                    try:
                        m_xml = client.get_component_xml(map_id)
                        m_root = ET.fromstring(m_xml)
                        m_comp_el = m_root.find('.//Map')
                        if m_comp_el is not None:
                            m_from = m_comp_el.get("fromProfile")
                            m_to = m_comp_el.get("toProfile")
                            for leg_op_id, op_info in migrated_ops.items():
                                leg_p = op_info.get("legacy_profile_id")
                                new_p = op_info.get("new_profile_id")
                                leg_pxml = op_info.get("legacy_profile_xml")
                                new_pxml = op_info.get("new_profile_xml")
                                if leg_p and new_p and leg_pxml and new_pxml and (m_from == leg_p or m_to == leg_p):
                                    yield "data: " + json.dumps({"log": f"Updating Map '{map_name}' ({map_id}) to use new JSON Profile {new_p}..."}) + "\n\n"
                                    upd_map_xml = migrator.update_map_for_db_profile(
                                        m_xml, leg_p, new_p, leg_pxml, new_pxml
                                    )
                                    client.update_component(map_id, upd_map_xml)
                                    yield "data: " + json.dumps({"log": f"✅ Successfully updated Map '{map_name}' ({map_id}) to DB V2 profile."}) + "\n\n"
                                    migration_summary.append({
                                        "type": "Map",
                                        "old_name": map_name,
                                        "old_id": map_id,
                                        "new_name": map_name,
                                        "new_id": map_id,
                                        "status": "Success (Updated to JSON Profile)"
                                    })
                    except Exception as map_err:
                        yield "data: " + json.dumps({"log": f"⚠️ Could not update Map {map_name} ({map_id}): {str(map_err)}"}) + "\n\n"

                # 4. Re-wire DB Processes in folder
                procs_to_migrate = scan_results.get("processes", [])
                for proc_meta in procs_to_migrate:
                    proc_id = proc_meta.get("componentId")
                    proc_name = proc_meta.get("name") or proc_id
                    try:
                        p_xml = client.get_component_xml(proc_id)
                        upd_pxml = p_xml
                        rewired = False
                        for leg_op_id, op_info in migrated_ops.items():
                            new_op_id = op_info.get("new_oper_id")
                            if new_op_id and leg_op_id in p_xml:
                                upd_pxml = migrator.migrate_process_connector_shapes(
                                    upd_pxml, "", conn_v2_id, leg_op_id, new_op_id,
                                    target_action_type=op_info.get("action_type")
                                )
                                rewired = True
                        if rewired:
                            client.update_component(proc_id, upd_pxml)
                            yield "data: " + json.dumps({"log": f"🚀 Successfully re-wired process '{proc_name}' ({proc_id}) to DB V2!"}) + "\n\n"
                            migration_summary.append({
                                "type": "Process",
                                "old_name": proc_name,
                                "old_id": proc_id,
                                "new_name": f"{proc_name} (V2 Re-wired)",
                                "new_id": proc_id,
                                "status": "Success"
                            })
                    except Exception as proc_err:
                        yield "data: " + json.dumps({"log": f"⚠️ Could not re-wire Process {proc_name} ({proc_id}): {str(proc_err)}"}) + "\n\n"

            # Cache the migration summary report per tab session and per account
            report_md = ["# Migration Summary Report\n"]
            acc_id = req.credentials.account_id or "account"
            report_md.append(f"> **Account ID**: `{acc_id}`  \n> **Generated At**: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}\n")
            report_md.append("| Type | Original Name | Original ID | Migrated Name | Migrated ID | Status |")
            report_md.append("| --- | --- | --- | --- | --- | --- |")
            for item in migration_summary:
                report_md.append(f"| {item['type']} | {item['old_name']} | `{item['old_id']}` | {item['new_name']} | `{item['new_id']}` | {item['status']} |")
            
            report_text = "\n".join(report_md)
            mig_entry = {
                "content": report_text,
                "account_id": acc_id,
                "timestamp": time.time()
            }
            if req.session_id:
                MIGRATION_REPORT_CACHE[req.session_id] = mig_entry
            if acc_id:
                MIGRATION_REPORT_CACHE[f"acc_{acc_id}"] = mig_entry
            MIGRATION_REPORT_CACHE["last"] = mig_entry
            
            yield "data: " + json.dumps({
                "status": "success",
                "log": "--- Boomi Database V2 Migration Completed Successfully! ---",
                "summary": migration_summary
            }) + "\n\n"
            
        except Exception as e:
            trace = traceback.format_exc()
            yield "data: " + json.dumps({"status": "error", "log": f"Migration failed: {str(e)}", "trace": trace}) + "\n\n"
            
    return StreamingResponse(event_stream(), media_type="text/event-stream")

@app.get("/api/download-migration-report")
def download_migration_report(session_id: Optional[str] = None, account_id: Optional[str] = None):
    entry = None
    if session_id and session_id in MIGRATION_REPORT_CACHE:
        entry = MIGRATION_REPORT_CACHE[session_id]
    elif account_id and f"acc_{account_id}" in MIGRATION_REPORT_CACHE:
        entry = MIGRATION_REPORT_CACHE[f"acc_{account_id}"]
    elif "last" in MIGRATION_REPORT_CACHE:
        entry = MIGRATION_REPORT_CACHE["last"]

    if not entry:
        raise HTTPException(status_code=400, detail="No migration results available for this session or account. Please run migration first.")
        
    report_content = entry.get("content", "") if isinstance(entry, dict) else str(entry)
    acc_id = account_id or (entry.get("account_id") if isinstance(entry, dict) else "account") or "account"
    
    reports_dir = os.path.join(tempfile.gettempdir(), "boomi_reports")
    os.makedirs(reports_dir, exist_ok=True)
    file_key = f"{acc_id}_{session_id or 'default'}_{int(time.time())}"
    temp_path = os.path.join(reports_dir, f"databasev2_migration_report_{file_key}.md")
    
    with open(temp_path, "w", encoding="utf-8") as f:
        f.write(report_content)
        
    download_filename = f"databasev2_migration_report_{acc_id}.md"
    return FileResponse(
        temp_path,
        media_type="text/markdown",
        filename=download_filename
    )

if __name__ == "__main__":
    import uvicorn
    # Standard startup on port 8000
    uvicorn.run(app, host="0.0.0.0", port=8000)

import os
import re
from google.adk.agents.llm_agent import Agent
from boomi_migration_agent.boomi_client import BoomiClient
from boomi_migration_agent.migration_tools import MigrationTools

# Initialize client and migration helpers
# Secrets are loaded dynamically from environment (.env)
client = BoomiClient()
migrator = MigrationTools(client=client)

# Define tools for ADK Agent

def scan_legacy_database_components() -> str:
    """
    Scans the Boomi account for all legacy database connections, operations, and profiles.
    Returns a text summary of the discovered components.
    """
    try:
        results = migrator.scan_legacy_components()
        summary = []
        summary.append(f"### Discovered Legacy Database Components")
        summary.append(f"**Connections found**: {len(results['connections'])}")
        for c in results['connections']:
            summary.append(f" - {c['name']} (ID: `{c['componentId']}`, Version: {c['version']}) in {c['folderPath']}")
        summary.append(f"\n**Operations found**: {len(results['operations'])}")
        for o in results['operations']:
            summary.append(f" - {o['name']} (ID: `{o['componentId']}`, Version: {o['version']}) in {o['folderPath']}")
        summary.append(f"\n**Profiles found**: {len(results['profiles'])}")
        for p in results['profiles']:
            summary.append(f" - {p['name']} (ID: `{p['componentId']}`, Version: {p['version']}) in {p['folderPath']}")
        return "\n".join(summary)
    except Exception as e:
        return f"Error scanning legacy components: {str(e)}"

def generate_markdown_audit_report() -> str:
    """
    Runs a where-used dependency analysis for all legacy database components and generates
    a detailed audit report in Markdown format.
    The report is saved to 'active-development/inventories/legacy_db_audit_report.md'.
    """
    try:
        results = migrator.scan_legacy_components()
        report = migrator.generate_audit_report_md(results)
        
        out_dir = "active-development/inventories"
        os.makedirs(out_dir, exist_ok=True)
        report_path = os.path.join(out_dir, "legacy_db_audit_report.md")
        
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report)
            
        return f"Audit report successfully written to {report_path}.\n\n### Report Content Preview:\n\n{report[:1000]}..."
    except Exception as e:
        return f"Error generating audit report: {str(e)}"

def migrate_connection(legacy_conn_id: str, new_name: str) -> str:
    """
    Pulls a legacy database connection, parses its host/port/database parameters,
    and creates a new Database V2 connection component.
    Rule 1: Don't keep passwords. The password fields are left blank for manual configuration.
    """
    try:
        # Pull legacy connection XML
        legacy_xml = client.get_component_xml(legacy_conn_id)
        # Parse legacy metadata to get folderId
        root = ET = xml = import_xml_root_helper(legacy_xml)
        folder_id = root.get("folderId")
        
        # Assemble new V2 connection
        v2_xml = migrator.assemble_dbv2_connection_xml(legacy_xml, folder_id, new_name)
        
        # Create or get component on Boomi platform
        new_id = client.get_or_create_component(new_name, "connector-settings", folder_id, v2_xml)
        
        return f"Successfully migrated legacy connection {legacy_conn_id} to Database V2 Connection. New Component ID: `{new_id}`"
    except Exception as e:
        return f"Error migrating connection: {str(e)}"

def migrate_operation_and_profiles(
    legacy_oper_id: str,
    new_conn_id: str,
    new_oper_name: str,
    new_req_profile_name: str,
    new_resp_profile_name: str
) -> str:
    """
    Migrates a legacy database operation and its referenced profile.db to Database V2
    by creating equivalent JSON request/response profiles and a new DB V2 operation.
    """
    try:
        # Pull legacy operation
        legacy_oper_xml = client.get_component_xml(legacy_oper_id)
        oper_root = import_xml_root_helper(legacy_oper_xml)
        folder_id = oper_root.get("folderId")
        
        # Find referenced legacy DB Profile ID
        profile_el = oper_root.find('.//ReadProfile')
        if profile_el is None:
            profile_el = oper_root.find('.//WriteProfile')
        if profile_el is None:
            # Check inside elements
            profile_el = oper_root.find('.//*[@profileId]')
            
        if profile_el is None:
            return f"Error: Legacy operation does not reference any Database Profile."
            
        legacy_profile_id = profile_el.get("profileId")
        
        # Pull and parse legacy DB profile
        legacy_profile_xml = client.get_component_xml(legacy_profile_id)
        profile_meta = migrator.parse_profile_db_sql(legacy_profile_xml)
        
        # Generate new JSON request/response profiles
        req_profile_id = None
        resp_profile_id = None
        
        # If read query (select)
        if profile_meta["statementType"] == "select":
            # For select, inputs are parameters (req), output is fields (resp)
            if profile_meta["params"]:
                req_xml = migrator.generate_json_profile_xml(new_req_profile_name, profile_meta["params"], folder_id)
                req_profile_id = client.get_or_create_component(new_req_profile_name, "profile.json", folder_id, req_xml)
                
            if profile_meta["fields"]:
                resp_xml = migrator.generate_json_profile_xml(new_resp_profile_name, profile_meta["fields"], folder_id)
                resp_profile_id = client.get_or_create_component(new_resp_profile_name, "profile.json", folder_id, resp_xml)
        else:
            # For write operations (inserts, updates, deletes)
            st_type = profile_meta.get("statementType", "")
            if st_type == "dynamicupdate":
                # Only dynamicupdate combines SET fields and WHERE condition fields
                write_fields = list(profile_meta.get("fields", []))
                for p in profile_meta.get("params", []):
                    if not any(f.get("name") == p.get("name") for f in write_fields):
                        write_fields.append(p)
            elif st_type == "dynamicdelete":
                write_fields = list(profile_meta.get("params", []))
            else:
                write_fields = list(profile_meta.get("fields", []))

            if write_fields:
                req_xml = migrator.generate_json_profile_xml(new_req_profile_name, write_fields, folder_id)
                req_profile_id = client.get_or_create_component(new_req_profile_name, "profile.json", folder_id, req_xml)
                
            # Also create standard response profile for DB V2 write actions (UPDATE, CREATE)
            t_name = profile_meta.get("tableName", "table")
            act_name = "UPDATE" if st_type == "dynamicupdate" else ("DELETE" if st_type == "dynamicdelete" else "CREATE")
            resp_name, resp_xml_gen = migrator.generate_dbv2_standard_response_profile(t_name, folder_id, act_name)
            resp_profile_id = client.get_or_create_component(resp_name, "profile.json", folder_id, resp_xml_gen)

        # Assemble new V2 operation XML
        t_name = profile_meta.get("tableName", "") if profile_meta else ""
        v2_oper_xml = migrator.assemble_dbv2_operation_xml(
            new_oper_name,
            new_conn_id,
            profile_meta["sql"],
            profile_meta["statementType"],
            req_profile_id,
            resp_profile_id,
            folder_id,
            table_name=t_name
        )
        
        # Create or get operation on platform
        new_oper_id = client.get_or_create_component(new_oper_name, "connector-action", folder_id, v2_oper_xml)
        
        return json.dumps({
            "status": "success",
            "legacy_operation_id": legacy_oper_id,
            "new_operation_id": new_oper_id,
            "new_request_profile_id": req_profile_id,
            "new_response_profile_id": resp_profile_id
        }, indent=2)
        
    except Exception as e:
        return f"Error migrating operation: {str(e)}"

def migrate_map_component_mappings(map_id: str, legacy_profile_id: str, new_profile_id: str) -> str:
    """
    Rule 2: Rewrites Map mappings from legacy DB profile keys to new JSON profile keys.
    Updates the Map component on the platform.
    """
    try:
        map_xml = client.get_component_xml(map_id)
        legacy_profile_xml = client.get_component_xml(legacy_profile_id)
        new_profile_xml = client.get_component_xml(new_profile_id)
        
        updated_map_xml = migrator.migrate_map_component(
            map_xml,
            legacy_profile_xml,
            new_profile_xml,
            new_profile_id
        )
        
        client.update_component(map_id, updated_map_xml)
        return f"Successfully rewrote map {map_id} mappings to point to JSON profile {new_profile_id} exactly."
    except Exception as e:
        return f"Error migrating map mappings: {str(e)}"

def migrate_process_connector_shapes(
    process_id: str,
    legacy_conn_id: str,
    new_conn_id: str,
    legacy_oper_id: str,
    new_oper_id: str
) -> str:
    """
    Modifies connector shapes inside a process to use Database V2 shapes and connections.
    """
    try:
        process_xml = client.get_component_xml(process_id)
        updated_xml = migrator.migrate_process_connector_shapes(
            process_xml,
            legacy_conn_id,
            new_conn_id,
            legacy_oper_id,
            new_oper_id
        )
        
        if updated_xml != process_xml:
            client.update_component(process_id, updated_xml)
            return f"Successfully updated process {process_id} connector shapes to use Database V2."
        return f"Process {process_id} did not contain shapes referencing legacy connection {legacy_conn_id}."
    except Exception as e:
        return f"Error updating process shapes: {str(e)}"

def import_xml_root_helper(xml_str):
    import xml.etree.ElementTree as ET
    # Strips any potential outer encoding declarations if they cause parsing issues
    xml_str = re.sub(r'<\?xml[^>]*\?>', '', xml_str).strip()
    return ET.fromstring(xml_str)


# Instantiate the Google ADK Agent
root_agent = Agent(
    model='gemini-2.5-flash',
    name='boomi_migration_agent',
    description='An AI-powered agent to scan, audit, and migrate legacy database components in Boomi to Database V2.',
    instruction=(
        "You are the Boomi Migration Agent. Your job is to:\n"
        "1. Scan the user's account for legacy database connections, operations, and profiles.\n"
        "2. Run a where-used analysis and write a detailed markdown audit report of all legacy database usage in the account.\n"
        "3. Migrate legacy database connections to Database V2 connections. Remember, do NOT configure any passwords; leave them blank.\n"
        "4. Migrate legacy operations to Database V2, translating database profiles into flat JSON profiles and mapping configurations exactly without data loss.\n"
        "5. Update mapping definitions in Maps to use the new JSON profiles.\n"
        "6. Re-wire processes to reference the new V2 components.\n\n"
        "Be systematic, run tools in order, and output clear markdown progress updates."
    ),
    tools=[
        scan_legacy_database_components,
        generate_markdown_audit_report,
        migrate_connection,
        migrate_operation_and_profiles,
        migrate_map_component_mappings,
        migrate_process_connector_shapes
    ]
)

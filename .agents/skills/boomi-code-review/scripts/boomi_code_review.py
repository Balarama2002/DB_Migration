#!/usr/bin/env python3
"""
Boomi Code Review & Static Analysis CLI Tool
Enforces Psiog Integrations review checklist, DB service user rules (SRV_),
process property externalization, redundant connection detection, and PROD diffing.
"""

import sys
import os
import re
import json
import argparse
import io
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Dict, Any, Optional, Set, Tuple
from urllib.parse import urlparse

# Ensure UTF-8 output on Windows consoles
if sys.stdout and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, "buffer"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


SEVERITY_ORDER = {"CRITICAL": 4, "MAJOR": 3, "MINOR": 2, "ADVISORY": 1}

DEFAULT_SHAPE_LABELS = {
    "start", "stop", "connector", "map", "decision", "branch", "message",
    "notify", "set properties", "dataprocess", "dataprocessscript", "catcherrors",
    "returndocuments", "processcall", "businessrules", "exception", "programcommand",
    "route", "cleanse", "combinetest", "tradingpartner", "flowservice", "events",
    "undefined", "none"
}

SENSITIVE_PATTERNS = re.compile(
    r"(?i)(password|secret|bearer\s+|apikey|api_key|client_secret|authorization\s*[:=]|token\s*[:=])",
    re.IGNORECASE
)

URL_PATTERN = re.compile(r"^https?://[^\s/$.?#].[^\s]*$", re.IGNORECASE)
FILE_PATH_PATTERN = re.compile(r"^([a-zA-Z]:\\|//|/var/|/opt/|/tmp/|/etc/|\\\\).*", re.IGNORECASE)

class ReviewFinding:
    def __init__(self, finding_id: str, severity: str, category: str, 
                 component_name: str, shape_or_element: str, 
                 description: str, remediation: str, file_path: Optional[str] = None):
        self.id = finding_id
        self.severity = severity.upper()
        self.category = category
        self.component_name = component_name
        self.shape_or_element = shape_or_element
        self.description = description
        self.remediation = remediation
        self.file_path = file_path

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "severity": self.severity,
            "category": self.category,
            "component_name": self.component_name,
            "shape_or_element": self.shape_or_element,
            "description": self.description,
            "remediation": self.remediation,
            "file_path": self.file_path
        }


class BoomiCodeReviewer:
    def __init__(self, prod_connections: Optional[Set[str]] = None, min_severity: str = "ADVISORY"):
        self.prod_connections = prod_connections or set()
        self.min_severity = min_severity.upper()
        self.findings: List[ReviewFinding] = []
        self._finding_counter = 1
        self.parsed_connections: List[Dict[str, Any]] = []
        self.parsed_processes: List[Dict[str, Any]] = []
        self.parsed_maps: List[Dict[str, Any]] = []
        self.parsed_process_properties: List[Dict[str, Any]] = []

    def _next_id(self) -> str:
        fid = f"F-{self._finding_counter:02d}"
        self._finding_counter += 1
        return fid

    def add_finding(self, severity: str, category: str, component_name: str,
                    shape_or_element: str, description: str, remediation: str,
                    file_path: Optional[str] = None):
        if SEVERITY_ORDER.get(severity, 1) >= SEVERITY_ORDER.get(self.min_severity, 1):
            finding = ReviewFinding(
                self._next_id(), severity, category, component_name,
                shape_or_element, description, remediation, file_path
            )
            self.findings.append(finding)

    def review_xml_file(self, file_path: str):
        path = Path(file_path)
        if not path.is_file() or path.suffix.lower() not in [".xml", ".bxml"]:
            return

        try:
            tree = ET.parse(file_path)
            root = tree.getroot()
        except Exception as e:
            # Not valid XML or parse failure
            return

        comp_type, comp_subtype, comp_name, comp_id = self._get_component_metadata(root)

        if comp_type == "process":
            self.parsed_processes.append({
                "file": file_path, "root": root, "name": comp_name, "id": comp_id
            })
            self._review_process(root, file_path, comp_name, comp_id)
        elif comp_type == "connector-settings":
            conn_info = self._extract_connection_info(root, file_path, comp_name, comp_subtype, comp_id)
            self.parsed_connections.append(conn_info)
            self._review_connection(conn_info)
        elif comp_type == "transform.map":
            self.parsed_maps.append({
                "file": file_path, "root": root, "name": comp_name, "id": comp_id
            })
            self._review_map(root, file_path, comp_name)
        elif comp_type == "processproperty":
            self.parsed_process_properties.append({
                "file": file_path, "root": root, "name": comp_name, "id": comp_id
            })

    def _get_component_metadata(self, root: ET.Element) -> Tuple[str, str, str, str]:
        # Handle both namespaced and non-namespaced Component elements
        tag = root.tag.split("}")[-1] if "}" in root.tag else root.tag
        comp_type = root.get("type", "")
        comp_subtype = root.get("subType", "")
        comp_name = root.get("name", "Unnamed Component")
        comp_id = root.get("componentId", "")
        return comp_type, comp_subtype, comp_name, comp_id

    def _review_process(self, root: ET.Element, file_path: str, name: str, comp_id: str):
        # 1. Process Naming Convention: [Domain]_[Object]_[Direction]_[Target]
        parts = name.split("_")
        if len(parts) < 3 or any(p.strip() == "" for p in parts):
            self.add_finding(
                severity="MAJOR",
                category="Structure & Naming",
                component_name=name,
                shape_or_element="Process Name",
                description=f"Process name '{name}' does not follow agreed convention '[Domain]_[Object]_[Direction]_[Target]'.",
                remediation="Rename process following the enterprise domain naming pattern (e.g. 'FIN_Invoice_Sync_to_SAP').",
                file_path=file_path
            )

        # 2. Process Description / Notes
        desc_elem = root.find(".//{http://api.platform.boomi.com/}description")
        if desc_elem is None:
            desc_elem = root.find(".//description")
        
        has_desc = desc_elem is not None and desc_elem.text and desc_elem.text.strip()
        if not has_desc:
            self.add_finding(
                severity="MINOR",
                category="Structure & Naming",
                component_name=name,
                shape_or_element="Process Description",
                description=f"Process notes/description is empty in '{name}'.",
                remediation="Add documentation explaining business purpose, trigger mechanism, and integration data flow.",
                file_path=file_path
            )

        # 3. Shape Labelling & Try/Catch & Hardcoded Configs
        shapes = root.findall(".//shape")
        has_try_catch = False
        has_connector_shape = False

        for shape in shapes:
            shape_id = shape.get("name", "unnamed_shape")
            shape_type = shape.get("shapetype", "").lower()
            user_label = shape.get("userlabel", "").strip()

            if shape_type == "catcherrors":
                has_try_catch = True
            elif shape_type == "connector" or shape.find(".//connectoraction") is not None:
                has_connector_shape = True

            # Labelling check
            if not user_label or user_label.lower() in DEFAULT_SHAPE_LABELS:
                self.add_finding(
                    severity="MAJOR",
                    category="Structure & Naming",
                    component_name=name,
                    shape_or_element=f"Shape: {shape_id} ({shape_type})",
                    description=f"Shape '{shape_id}' has default or missing label: '{user_label or '<blank>'}'.",
                    remediation="Add a descriptive label indicating business intent (e.g. 'Query Salesforce Contacts').",
                    file_path=file_path
                )

            # Check hardcoded URLs or file paths in Set Properties / Message
            for pv in shape.findall(".//parametervalue"):
                val_type = pv.get("valueType", "")
                static_val = pv.get("staticValue", "")
                if not static_val and pv.find(".//staticparameter") is not None:
                    sp = pv.find(".//staticparameter")
                    static_val = sp.get("staticValue", "") or sp.text or ""

                if val_type == "static" and static_val:
                    if URL_PATTERN.match(static_val.strip()) or FILE_PATH_PATTERN.match(static_val.strip()):
                        self.add_finding(
                            severity="MAJOR",
                            category="Configuration",
                            component_name=name,
                            shape_or_element=f"Shape: {user_label or shape_id}",
                            description=f"Hardcoded environment/system path or URL found in parameter: '{static_val}'.",
                            remediation="Move configurable endpoints and directories into a project Process Property component with extensions.",
                            file_path=file_path
                        )

            # Check Sensitive logging in Message and Notify shapes
            if shape_type in ["notify", "message"]:
                notify_msg = shape.find(".//notifyMessage")
                msg_elem = shape.find(".//message")
                text_content = ""
                if notify_msg is not None and notify_msg.text:
                    text_content += notify_msg.text + " "
                if msg_elem is not None and msg_elem.text:
                    text_content += msg_elem.text + " "

                if text_content and SENSITIVE_PATTERNS.search(text_content):
                    self.add_finding(
                        severity="CRITICAL",
                        category="Security",
                        component_name=name,
                        shape_or_element=f"Shape: {user_label or shape_id} ({shape_type})",
                        description=f"Potential sensitive credential/token logging detected in message body.",
                        remediation="Mask or omit passwords, authorization headers, and API keys from logs and alerts.",
                        file_path=file_path
                    )

        # Try/Catch coverage check
        if has_connector_shape and not has_try_catch:
            self.add_finding(
                severity="CRITICAL",
                category="Error Handling",
                component_name=name,
                shape_or_element="Canvas / Flow",
                description="Process calls external connectors but lacks a Try/Catch error handling shape.",
                remediation="Wrap external connector calls in a Try/Catch shape with an error notification and dead-letter path.",
                file_path=file_path
            )

        # 4. Error Notification Diagnostic Completeness Check
        # Check all Message and Notify shapes for error-handling context
        for shape in shapes:
            shape_id = shape.get("name", "unnamed_shape")
            shape_type = shape.get("shapetype", "").lower()
            user_label = shape.get("userlabel", "").strip()

            if shape_type in ["notify", "message"]:
                all_text = ET.tostring(shape, encoding="unicode", method="text")
                xml_str = ET.tostring(shape, encoding="unicode")
                
                # Check if this shape is intended for error notification
                is_error_notifier = (
                    "catcherrorsmessage" in xml_str.lower() or 
                    "error" in all_text.lower() or 
                    "failure" in all_text.lower() or 
                    "exception" in all_text.lower()
                )

                if is_error_notifier:
                    missing_diagnostics = []
                    # Check for Execution ID
                    if "executionid" not in xml_str.lower():
                        missing_diagnostics.append("Execution ID (meta.base.executionid)")
                    # Check for Atom / Runtime Name
                    if "atomname" not in xml_str.lower():
                        missing_diagnostics.append("Runtime / Atom Name")
                    # Check for Error Message
                    if "catcherrorsmessage" not in xml_str.lower():
                        missing_diagnostics.append("Catch Error Message (meta.base.catcherrorsmessage)")
                    # Check for Business Identifier (e.g. document property DDP_ or trackparameter)
                    has_business_id = bool(re.search(r"(ddp_|trackparameter|elementSetName)", xml_str, re.IGNORECASE))
                    if not has_business_id:
                        missing_diagnostics.append("Business Identifier (e.g. DDP_InvoiceId, DDP_EmployeeId)")

                    if missing_diagnostics:
                        self.add_finding(
                            severity="MAJOR",
                            category="Error Notification Completeness",
                            component_name=name,
                            shape_or_element=f"Shape: {user_label or shape_id} ({shape_type})",
                            description=f"Error notification is missing critical diagnostic fields: {', '.join(missing_diagnostics)}.",
                            remediation="Include Environment, Atom Name, Execution ID, Catch Error Message, and Business Document Identifier in the error notification template.",
                            file_path=file_path
                        )

        # 5. API Pagination Loop Closure Check
        xml_full = ET.tostring(root, encoding="unicode")
        has_pagination_token = bool(re.search(r"(next_page|page_token|cursor|pagenumber|page_offset)", xml_full, re.IGNORECASE))
        if has_pagination_token:
            has_decision = any(s.get("shapetype", "").lower() == "decision" for s in shapes)
            if not has_decision:
                self.add_finding(
                    severity="CRITICAL",
                    category="API Pagination",
                    component_name=name,
                    shape_or_element="Pagination Logic",
                    description="Pagination tokens detected but process lacks a Decision shape to verify null/empty token or loop closure.",
                    remediation="Add a Decision shape checking both empty/null token and a maximum iteration counter to ensure deterministic loop exit.",
                    file_path=file_path
                )

        # 6. Batch Processing Isolation & Halt Analysis
        has_split_shape = any(s.get("shapetype", "").lower() in ["split", "dataprocess"] for s in shapes)
        # If there's a split, check if Try/Catch is downstream
        if has_split_shape and has_try_catch:
            # Check shape order / positioning
            split_shapes = [s for s in shapes if s.get("shapetype", "").lower() in ["split", "dataprocess"]]
            tc_shapes = [s for s in shapes if s.get("shapetype", "").lower() == "catcherrors"]
            
            # Simple heuristic: if catcherrors appears before split, 1 failure aborts remaining docs
            tc_x = float(tc_shapes[0].get("x", 0)) if tc_shapes else 0
            split_x = float(split_shapes[0].get("x", 0)) if split_shapes else 0
            
            if tc_x < split_x:
                self.add_finding(
                    severity="MAJOR",
                    category="Batch Processing Dynamics",
                    component_name=name,
                    shape_or_element="Try/Catch Placement",
                    description="Batch Halt Risk: Try/Catch is positioned before the Split shape. If one document fails downstream, the entire batch will abort and halt remaining valid documents.",
                    remediation="Place a Try/Catch shape downstream of the Split shape if individual document-level error isolation is required.",
                    file_path=file_path
                )


    def _extract_connection_info(self, root: ET.Element, file_path: str,
                                comp_name: str, comp_subtype: str, comp_id: str) -> Dict[str, Any]:
        info = {
            "name": comp_name,
            "id": comp_id,
            "subtype": comp_subtype,
            "file": file_path,
            "endpoint": "",
            "username": "",
            "is_extended": False
        }

        # Check legacy database settings
        db_settings = root.find(".//DatabaseConnectionSettings")
        if db_settings is not None:
            info["username"] = db_settings.get("username", "")
            host = db_settings.get("host", "")
            port = db_settings.get("port", "")
            dbname = db_settings.get("dbname", "")
            info["endpoint"] = f"{host}:{port}/{dbname}".strip(":/")

        # Check GenericConnectionConfig (Database V2, REST, SFTP, etc.)
        for field in root.findall(".//GenericConnectionConfig/field"):
            fid = field.get("id", "")
            fval = field.get("value", "")
            if fid == "username":
                info["username"] = fval
            elif fid in ["url", "host"]:
                info["endpoint"] = fval

        # Check HTTP settings
        http_settings = root.find(".//HttpSettings")
        if http_settings is not None:
            info["endpoint"] = http_settings.get("url", "")
            auth = http_settings.find(".//AuthSettings")
            if auth is not None:
                info["username"] = auth.get("user", "")

        return info

    def _review_connection(self, conn: Dict[str, Any]):
        name = conn["name"]
        subtype = conn["subtype"]
        username = conn["username"]
        comp_id = conn["id"]
        file_path = conn["file"]

        # 1. Database Service User check (SRV_ prefix)
        is_db = (subtype == "database" or "dbv2" in subtype.lower() or "database" in subtype.lower())
        if is_db and username:
            if not username.upper().startswith("SRV_"):
                self.add_finding(
                    severity="CRITICAL",
                    category="Security",
                    component_name=name,
                    shape_or_element="Connection Settings (User)",
                    description=f"Database username '{username}' does not have the mandatory 'SRV_' service user prefix.",
                    remediation="Configure a dedicated service account prefixed with 'SRV_' (e.g. 'SRV_BOOMI_APP').",
                    file_path=file_path
                )

        # 2. Check if newly created and missing from PROD
        if self.prod_connections and comp_id:
            if comp_id not in self.prod_connections:
                self.add_finding(
                    severity="MAJOR",
                    category="Connectors & Connections",
                    component_name=name,
                    shape_or_element=f"Connection ID: {comp_id}",
                    description=f"Newly created connection '{name}' does not exist in PROD baseline.",
                    remediation="Verify whether this is a legitimate new external integration or an accidental duplicate of an existing PROD connection.",
                    file_path=file_path
                )

    def _review_map(self, root: ET.Element, file_path: str, name: str):
        # Inspect scripting functions in Map
        scripts = root.findall(".//FunctionStep[@category='Scripting']") + root.findall(".//mapscript")
        for idx, s in enumerate(scripts, start=1):
            body = ""
            for elem in s.iter():
                if elem.text:
                    body += elem.text + "\n"
            
            # Check comment density in custom script
            has_comments = bool(re.search(r"(//|/\*|#)", body))
            if body.strip() and not has_comments:
                self.add_finding(
                    severity="MINOR",
                    category="Data Handling & Mapping",
                    component_name=name,
                    shape_or_element=f"Map Function Script #{idx}",
                    description="Custom script in map function lacks comments or documentation.",
                    remediation="Add inline comments explaining transformation logic and handling of null/empty inputs.",
                    file_path=file_path
                )

    def check_cross_component_redundancies(self):
        # 1. Check for redundant connections targeting the same normalized endpoint
        endpoint_map: Dict[str, List[Dict[str, Any]]] = {}

        for conn in self.parsed_connections:
            ep = conn.get("endpoint", "").strip()
            if not ep:
                continue
            
            # Normalize endpoint (strip trailing slash, lowercase host)
            parsed = urlparse(ep) if "://" in ep else None
            norm_key = (parsed.netloc or parsed.path or ep).lower().rstrip("/") if parsed else ep.lower().rstrip("/")

            if norm_key not in endpoint_map:
                endpoint_map[norm_key] = []
            endpoint_map[norm_key].append(conn)

        for norm_ep, conns in endpoint_map.items():
            if len(conns) > 1:
                names = ", ".join(f"'{c['name']}' ({c['subtype']})" for c in conns)
                subtypes = {c['subtype'] for c in conns}
                
                if len(subtypes) > 1 and ("http" in subtypes or any("rest" in st.lower() for st in subtypes)):
                    desc = f"Redundant mixed connector types detected pointing to same endpoint '{norm_ep}': {names}."
                else:
                    desc = f"Duplicate connection components detected targeting identical endpoint '{norm_ep}': {names}."

                self.add_finding(
                    severity="MAJOR",
                    category="Connectors & Connections",
                    component_name="Shared Connections",
                    shape_or_element="Connection Registry",
                    description=desc,
                    remediation="Consolidate duplicate connection components into a single shared connection component across the workspace."
                )

        # 2. Check if project defines a process property component
        if self.parsed_processes and not self.parsed_process_properties:
            self.add_finding(
                severity="MAJOR",
                category="Configuration",
                component_name="Project Structure",
                shape_or_element="Process Property Component",
                description="No dedicated project Process Property component ('type=\"processproperty\"') found in workspace.",
                remediation="Create a dedicated Process Property component for project configurations (endpoints, folders, toggles) with Environment Extensions enabled."
            )

    def calculate_verdict(self) -> str:
        severities = [f.severity for f in self.findings]
        if "CRITICAL" in severities:
            return "✖ Rework required"
        major_count = severities.count("MAJOR")
        if major_count > 2:
            return "✖ Rework required"
        elif major_count > 0:
            return "⚠ Approved with conditions"
        return "✔ Approved"

    def format_text_report(self) -> str:
        lines = []
        lines.append("=" * 80)
        lines.append("               BOOMI CODE REVIEW & STATIC ANALYSIS REPORT")
        lines.append("=" * 80)
        lines.append(f"Components Scanned: {len(self.parsed_processes)} Processes, "
                     f"{len(self.parsed_connections)} Connections, {len(self.parsed_maps)} Maps, "
                     f"{len(self.parsed_process_properties)} Process Properties")
        lines.append(f"Total Findings: {len(self.findings)}")
        lines.append(f"Overall Verdict: {self.calculate_verdict()}")
        lines.append("-" * 80)

        if not self.findings:
            lines.append("✔ Clean review! All automated checks passed.")
            lines.append("=" * 80)
            return "\n".join(lines)

        lines.append(f"{'ID':<6} | {'SEVERITY':<8} | {'CATEGORY':<20} | {'COMPONENT / SHAPE':<25} | {'DESCRIPTION'}")
        lines.append("-" * 80)
        for f in self.findings:
            comp_shape = f"{f.component_name} [{f.shape_or_element}]"[:25]
            lines.append(f"{f.id:<6} | {f.severity:<8} | {f.category:<20} | {comp_shape:<25} | {f.description}")
            lines.append(f"       -> Fix: {f.remediation}")
            if f.file_path:
                lines.append(f"       -> File: {f.file_path}")
            lines.append("-" * 80)

        lines.append("=" * 80)
        return "\n".join(lines)

    def format_markdown_report(self) -> str:
        verdict = self.calculate_verdict()
        lines = [
            "# Boomi Code Review Report",
            "",
            "## Summary",
            f"- **Verdict**: **{verdict}**",
            f"- **Processes Scanned**: {len(self.parsed_processes)}",
            f"- **Connections Scanned**: {len(self.parsed_connections)}",
            f"- **Total Findings**: {len(self.findings)}",
            "",
            "## Findings Matrix",
            "",
            "| ID | Severity | Category | Component / Shape | Description | Remediation |",
            "|---|---|---|---|---|---|"
        ]
        for f in self.findings:
            comp = f"`{f.component_name}`<br>*{f.shape_or_element}*"
            lines.append(f"| **{f.id}** | `{f.severity}` | {f.category} | {comp} | {f.description} | {f.remediation} |")

        lines.append("")
        return "\n".join(lines)


def load_prod_connections(prod_path: str) -> Set[str]:
    p = Path(prod_path)
    res = set()
    if p.is_file():
        if p.suffix.lower() == ".json":
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    res.update(data)
                elif isinstance(data, dict):
                    res.update(data.keys())
            except Exception:
                pass
        elif p.suffix.lower() in [".xml", ".bxml"]:
            try:
                tree = ET.parse(prod_path)
                cid = tree.getroot().get("componentId")
                if cid:
                    res.add(cid)
            except Exception:
                pass
    elif p.is_dir():
        for f in p.rglob("*.xml"):
            try:
                tree = ET.parse(f)
                cid = tree.getroot().get("componentId")
                if cid:
                    res.add(cid)
            except Exception:
                pass
    return res


def main():
    parser = argparse.ArgumentParser(description="Boomi Code Review & Static Analysis Linter")
    parser.add_argument("target", help="XML file or directory to review (e.g. active-development/)")
    parser.add_argument("--prod-connections", help="File or directory of known PROD connection GUIDs", default=None)
    parser.add_argument("--min-severity", choices=["CRITICAL", "MAJOR", "MINOR", "ADVISORY"], default="ADVISORY")
    parser.add_argument("--format", choices=["text", "markdown", "json"], default="text")
    parser.add_argument("--output", help="Optional path to write report output", default=None)

    args = parser.parse_args()

    prod_set = load_prod_connections(args.prod_connections) if args.prod_connections else set()
    reviewer = BoomiCodeReviewer(prod_connections=prod_set, min_severity=args.min_severity)

    target_path = Path(args.target)
    if not target_path.exists():
        print(f"Error: Target path does not exist: {args.target}", file=sys.stderr)
        sys.exit(1)

    if target_path.is_file():
        reviewer.review_xml_file(str(target_path))
    else:
        for root_dir, _, files in os.walk(target_path):
            for file in files:
                if file.lower().endswith((".xml", ".bxml")):
                    reviewer.review_xml_file(os.path.join(root_dir, file))

    reviewer.check_cross_component_redundancies()

    if args.format == "json":
        output_str = json.dumps({
            "verdict": reviewer.calculate_verdict(),
            "findings": [f.to_dict() for f in reviewer.findings]
        }, indent=2)
    elif args.format == "markdown":
        output_str = reviewer.format_markdown_report()
    else:
        output_str = reviewer.format_text_report()

    if args.output:
        Path(args.output).write_text(output_str, encoding="utf-8")
        print(f"Report written to: {args.output}")
    else:
        print(output_str)

    # Exit code: 2 for CRITICAL, 1 for MAJOR, 0 otherwise
    severities = [f.severity for f in reviewer.findings]
    if "CRITICAL" in severities:
        sys.exit(2)
    elif "MAJOR" in severities:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()

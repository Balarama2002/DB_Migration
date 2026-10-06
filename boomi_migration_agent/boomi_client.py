import os
import re
import requests
import xml.etree.ElementTree as ET
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()
# Also search parent directory of this file (workspace root) to support execution via ADK CLI
parent_env = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
if os.path.exists(parent_env):
    load_dotenv(parent_env, override=True)

class BoomiClient:
    def __init__(self, api_url=None, account_id=None, username=None, api_token=None, branch=None):
        # Only fall back to .env if NO credential arguments were passed at all (e.g. CLI scripts)
        no_args_passed = (account_id is None and username is None and api_token is None)
        
        self.api_url = (api_url or "").strip() or os.getenv("BOOMI_API_URL", "https://api.boomi.com")
        if no_args_passed:
            self.account_id = os.getenv("BOOMI_ACCOUNT_ID")
            self.username = os.getenv("BOOMI_USERNAME")
            self.api_token = os.getenv("BOOMI_API_TOKEN")
            requested_branch = os.getenv("BOOMI_BRANCH")
        else:
            self.account_id = (account_id or "").strip() or None
            self.username = (username or "").strip() or None
            self.api_token = (api_token or "").strip() or None
            requested_branch = (branch or "").strip() or os.getenv("BOOMI_BRANCH")
            
        self.verify_ssl = os.getenv("BOOMI_VERIFY_SSL", "true").lower() == "true"
        
        if not all([self.account_id, self.username, self.api_token]):
            raise ValueError("Missing Boomi credentials: Username, API Token, and Account ID must all be provided.")

        self.auth = HTTPBasicAuth(f"BOOMI_TOKEN.{self.username}", self.api_token)
        self.base_url = f"{self.api_url}/api/rest/v1/{self.account_id}"
        self.session = requests.Session()
        from urllib3.util import Retry
        retry_strategy = Retry(
            total=6,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["POST", "GET"]
        )
        adapter = requests.adapters.HTTPAdapter(pool_connections=60, pool_maxsize=60, max_retries=retry_strategy)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

        self.branch_name = None
        self.branch_id = None
        if requested_branch:
            self.branch_name, self.branch_id = self.resolve_branch(requested_branch)

    def resolve_branch(self, branch_name_or_id):
        """Resolves a branch name or ID against the Boomi Platform. Enforces main branch protection."""
        if not branch_name_or_id:
            return None, None
        b_str = branch_name_or_id.strip()
        if b_str.lower() == "main":
            raise ValueError(
                "Execution terminated: Operations on the 'main' branch are strictly prohibited to safeguard production code. "
                "Please specify a non-main development or feature branch (e.g. 'dbv2_merging')."
            )
        try:
            branches = self.query("Branch", {"QueryFilter": {}}, single_page=True)
        except Exception as e:
            raise Exception(f"Failed to query branches for account {self.account_id}: {str(e)}")

        for b in branches:
            b_name = (b.get("name") or "").strip()
            b_id = (b.get("id") or "").strip()
            if b_name.lower() == b_str.lower() or b_id == b_str:
                if b_name.lower() == "main":
                    raise ValueError(
                        "Execution terminated: Operations on the 'main' branch are strictly prohibited to safeguard production code. "
                        "Please specify a non-main development or feature branch (e.g. 'dbv2_merging')."
                    )
                return b_name, b_id

        available = [b.get("name") for b in branches if (b.get("name") or "").lower() != "main"]
        avail_str = f" Available feature branches: {', '.join(available)}." if available else " No feature branches found."
        raise ValueError(f"Branch '{b_str}' was not found in account {self.account_id}.{avail_str}")

    def _inject_branch_id(self, xml_data):
        if not self.branch_id:
            return xml_data
        if 'branchId="' in xml_data:
            return re.sub(r'branchId="[^"]*"', f'branchId="{self.branch_id}"', xml_data, count=1)
        return re.sub(r'(<(?:[a-zA-Z0-9_\-]+:)?Component\b)', rf'\1 branchId="{self.branch_id}"', xml_data, count=1)

    def _get_headers(self, accept_xml=False, send_xml=False):
        headers = {}
        if accept_xml:
            headers["Accept"] = "application/xml"
        else:
            headers["Accept"] = "application/json"
            
        if send_xml:
            headers["Content-Type"] = "application/xml"
        else:
            headers["Content-Type"] = "application/json"
            
        headers["User-Agent"] = "boomi-companion/adk-migration-agent/1.0.0"
        return headers

    def query(self, endpoint, payload, progress_callback=None, single_page=False, page_callback=None):
        """Query platform API endpoint with pagination support and optional page-by-page streaming callback"""
        url = f"{self.base_url}/{endpoint}/query"
        response = self.session.post(
            url,
            json=payload,
            auth=self.auth,
            headers=self._get_headers(),
            verify=self.verify_ssl,
            timeout=45
        )
        if response.status_code != 200:
            err_text = response.text
            clean_msg = err_text
            try:
                # Extract clean message from Boomi UserMessage XML
                if "<Data>" in err_text and "</Data>" in err_text:
                    clean_msg = err_text.split("<Data>")[1].split("</Data>")[0].strip()
                elif "<message>" in err_text and "</message>" in err_text:
                    clean_msg = err_text.split("<message>")[1].split("</message>")[0].strip()
            except Exception:
                clean_msg = err_text
            raise Exception(f"Boomi API error (HTTP {response.status_code}): {clean_msg}")
        
        data = response.json()
        results = data.get("result", [])
        if single_page:
            if page_callback:
                page_callback(results, 1)
            return results

        token = data.get("queryToken")
        page = 1
        if progress_callback:
            progress_callback(len(results), page)
        if page_callback:
            page_callback(results, 1)
        
        # Paginate results if queryToken is present
        while token:
            page += 1
            url_more = f"{self.base_url}/{endpoint}/queryMore"
            response_more = None
            for attempt in range(4):
                try:
                    response_more = self.session.post(
                        url_more,
                        data=token,
                        auth=self.auth,
                        headers=self._get_headers(send_xml=False),
                        verify=self.verify_ssl,
                        timeout=45
                    )
                    if response_more.status_code == 200:
                        break
                    if attempt == 3:
                        raise Exception(f"Boomi queryMore error (HTTP {response_more.status_code}): {response_more.text}")
                    import time
                    time.sleep(0.5 * (2 ** attempt))
                except Exception as e:
                    if attempt == 3:
                        raise
                    import time
                    time.sleep(0.5 * (2 ** attempt))

            if response_more is None or response_more.status_code != 200:
                break
            data_more = response_more.json()
            page_results = data_more.get("result", [])
            results.extend(page_results)
            token = data_more.get("queryToken")
            if progress_callback:
                progress_callback(len(results), page)
            if page_callback:
                page_callback(page_results, page)
            
        return results

    def get_component_xml(self, component_id, version=None):
        """Get component definition XML from the platform"""
        if version:
            endpoint = f"Component/{component_id}~{version}"
            url = f"{self.base_url}/{endpoint}"
            response = self.session.get(
                url,
                auth=self.auth,
                headers=self._get_headers(accept_xml=True),
                verify=self.verify_ssl
            )
            if response.status_code != 200:
                raise Exception(f"Failed to get component {component_id} version {version} (HTTP {response.status_code}): {response.text}")
            return response.text

        if self.branch_id:
            endpoint = f"Component/{component_id}~{self.branch_id}"
            url = f"{self.base_url}/{endpoint}"
            response = self.session.get(
                url,
                auth=self.auth,
                headers=self._get_headers(accept_xml=True),
                verify=self.verify_ssl
            )
            if response.status_code == 200:
                return response.text
            # If not found or error, fallback to base component (inherited from main)

        endpoint = f"Component/{component_id}"
        url = f"{self.base_url}/{endpoint}"
        response = self.session.get(
            url,
            auth=self.auth,
            headers=self._get_headers(accept_xml=True),
            verify=self.verify_ssl
        )
        if response.status_code != 200:
            raise Exception(f"Failed to get component {component_id} (HTTP {response.status_code}): {response.text}")
        return response.text

    def create_component(self, xml_data):
        """Create a new component on the platform (stamped with branchId if working on branch)"""
        xml_data = self._inject_branch_id(xml_data)
        url = f"{self.base_url}/Component"
        response = self.session.post(
            url,
            data=xml_data,
            auth=self.auth,
            headers=self._get_headers(accept_xml=True, send_xml=True),
            verify=self.verify_ssl
        )
        if response.status_code != 200:
            raise Exception(f"Failed to create component (HTTP {response.status_code}): {response.text}")
        return response.text

    def update_component(self, component_id, xml_data):
        """Update an existing component on the platform (stamped with branchId if working on branch)"""
        xml_data = self._inject_branch_id(xml_data)
        url = f"{self.base_url}/Component/{component_id}"
        response = self.session.post(
            url,
            data=xml_data,
            auth=self.auth,
            headers=self._get_headers(accept_xml=True, send_xml=True),
            verify=self.verify_ssl
        )
        if response.status_code != 200:
            raise Exception(f"Failed to update component {component_id} (HTTP {response.status_code}): {response.text}")
        return response.text

    def get_or_create_component(self, name, type_name, folder_id, xml_data):
        """Query platform ComponentMetadata to check if component exists. If yes, return its ID; otherwise, create it."""
        nested = [
            {"operator": "EQUALS", "property": "name", "argument": [name]},
            {"operator": "EQUALS", "property": "type", "argument": [type_name]},
            {"operator": "EQUALS", "property": "folderId", "argument": [folder_id]},
            {"operator": "EQUALS", "property": "deleted", "argument": ["false"]}
        ]
        if self.branch_name:
            nested.append({"operator": "EQUALS", "property": "branchName", "argument": [self.branch_name]})
        else:
            nested.append({"operator": "EQUALS", "property": "currentVersion", "argument": ["true"]})

        query_payload = {
            "QueryFilter": {
                "expression": {
                    "operator": "AND",
                    "nestedExpression": nested
                }
            }
        }
        try:
            results = self.query("ComponentMetadata", query_payload)
            if results:
                comp_id = results[0].get("componentId")
                print(f"Found existing component '{name}' (Type: {type_name}) with ID: {comp_id}. Reusing.")
                return comp_id
        except Exception as e:
            print(f"Error querying metadata for {name}: {e}. Proceeding with creation.")
            
        print(f"Creating new component '{name}' (Type: {type_name})...")
        created_xml = self.create_component(xml_data)
        # Strip XML declaration and parse componentId
        clean_xml = re.sub(r'<\?xml[^>]*\?>', '', created_xml).strip()
        comp_id = ET.fromstring(clean_xml).get("componentId")
        return comp_id

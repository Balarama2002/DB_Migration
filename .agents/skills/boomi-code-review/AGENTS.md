# Boomi Code Review & Architecture Agent Instructions

This repository contains the Boomi Code Review Skill and static analysis CLI, implementing the Psiog Integrations code review standards.

## Quick CLI Reference
- Run static review: `python scripts/boomi_code_review.py <target-file-or-dir> --format markdown`
- Review checklist reference: `references/checklist.md`
- Formal report template: `references/report_template.md`

## Core Review Directives
1. **Database Service Accounts**: Strictly enforce `SRV_` prefix on database usernames (`CRITICAL`).
2. **Credential Security**: Reject hardcoded passwords, tokens, API keys, or cleartext secrets in process properties (`CRITICAL`).
3. **Connector Error Handling**: Ensure all external connector calls (HTTP, REST, DB, WSS) are wrapped in Try/Catch (`CRITICAL`).
4. **Connection Governance**: Flag duplicate connection components and mixed connector types pointing to identical endpoints (`MAJOR`).
5. **Batch Processing Dynamics**: Ensure Try/Catch is placed downstream of Split shapes to isolate document failures (`MAJOR`).
6. **Error Notification Diagnostics**: Verify presence of Execution ID, Atom Name, Catch Errors Message, and Business Tracking IDs (`MAJOR`).
7. **Canvas Hygiene**: Flag unlabelled shapes (`userlabel=""`), orphaned shapes, and empty maps (`MAJOR` / `MINOR`).

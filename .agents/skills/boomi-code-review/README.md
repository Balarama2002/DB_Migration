# Boomi Code Review & Architecture Skill

A multi-platform, automated static analysis engine and architectural peer-review skill for **Dell Boomi** integrations, implementing the **Psiog Integrations Code Review Framework** and enterprise security policies.

Compatible with **Antigravity**, **Claude (Claude Code)**, **Cursor**, **Codex / GitHub Copilot**, and **Standalone CLI**.

---

## Features

- 🛡️ **Database Service Account Enforcement**: Mandates `SRV_` username prefix for legacy and Database V2 connections (`CRITICAL`).
- 🔐 **Credential Leak Detection**: Identifies hardcoded tokens, passwords, API keys, and unencrypted Process Property default values (`CRITICAL`).
- ⚡ **Resilience & Try/Catch Coverage**: Audits outbound connectors (HTTP, REST, DB, WSS) for missing Try/Catch wrappers (`CRITICAL`).
- 🔄 **Redundant Connection Detection**: Identifies duplicate connection components targeting identical endpoints, and flags mixed HTTP/REST connector types (`MAJOR`).
- 📦 **Batch Processing & Halt Analysis**: Detects batch abort risks where Try/Catch is placed upstream of Split shapes (`MAJOR`).
- 📋 **Diagnostic Metadata Verification**: Verifies error notifications contain Execution ID, Atom Name, Error Message, and Business Tracking IDs (`MAJOR`).
- 🧹 **Canvas Hygiene & Dead Code Detection**: Detects unlabelled shapes (`userlabel=""`), empty maps (`0 mappings`), and orphaned/unreachable canvas shapes (`MAJOR` / `MINOR`).
- 📄 **Formal Report Generation**: Generates standard markdown review reports with ServiceNow metadata, checklist items, and an actionable verdict (`Approved`, `Approved with conditions`, `Rework required`).

---

## Compatibility & Quickstart

| Platform | Setup Location | How to Trigger |
|---|---|---|
| **Antigravity / Gemini** | `.agents/skills/boomi-code-review/` | `/boomi-code-review [path]` |
| **Claude (Claude Code CLI)** | `.claude/commands/boomi-code-review.md` or `CLAUDE.md` | `/boomi-code-review [path]` |
| **Cursor** | `.cursor/rules/boomi-code-review.mdc` | `@boomi-code-review` in Composer or auto-triggered on XMLs |
| **Codex / GitHub Copilot** | `.github/copilot-instructions.md` | `@workspace /review` or natural prompt in Copilot Chat |
| **Standalone Terminal** | `scripts/boomi_code_review.py` | `python scripts/boomi_code_review.py <path>` |

---

## Installation Guide for Peers

### 1. Standalone / Workspace Installation (Recommended)
Clone this repository into your project's `.agents/skills/` directory:

```bash
mkdir -p .agents/skills
git clone https://github.com/<your-org>/boomi-code-review.git .agents/skills/boomi-code-review
```

*(Or as a Git Submodule: `git submodule add https://github.com/<your-org>/boomi-code-review.git .agents/skills/boomi-code-review`)*

### 2. Global Installation (Machine-Wide)
To make this skill available across **all projects** opened in your local IDE without re-cloning:

* **Windows:**
  ```powershell
  git clone https://github.com/<your-org>/boomi-code-review.git "$HOME\.gemini\skills\boomi-code-review"
  ```
* **macOS / Linux:**
  ```bash
  git clone https://github.com/<your-org>/boomi-code-review.git ~/.gemini/skills/boomi-code-review
  ```

---

## Standalone CLI Usage

The core Python analyzer has **zero external pip dependencies** and runs on Python 3.8+:

```bash
# Review a single process or component XML
python scripts/boomi_code_review.py path/to/MyProcess.xml

# Review an entire folder of components with markdown output
python scripts/boomi_code_review.py active-development/ --format markdown

# Review components against known PROD connection GUIDs
python scripts/boomi_code_review.py active-development/ --prod-connections prod-baseline/

# Output JSON report to a file
python scripts/boomi_code_review.py active-development/ --format json --output report.json
```

### CLI Arguments

| Argument | Description | Default |
|---|---|---|
| `target` | Path to an XML file or directory of component XMLs | *Required* |
| `--format` | Output format: `text`, `markdown`, or `json` | `text` |
| `--output` | File path to write the formatted report | `None` (stdout) |
| `--min-severity` | Minimum severity to display: `CRITICAL`, `MAJOR`, `MINOR`, `ADVISORY` | `ADVISORY` |
| `--prod-connections` | Directory or JSON file containing known PROD connection GUIDs | `None` |

### CLI Exit Codes
- `0`: Clean review (or only Minor/Advisory findings).
- `1`: One or more `MAJOR` findings detected.
- `2`: One or more `CRITICAL` policy violations detected.

---

## Repository Structure

```text
boomi-code-review/
├── README.md                              # Main documentation & setup guide
├── AGENTS.md                              # Universal cross-agent prompt standard
├── CLAUDE.md                              # Claude Code CLI instructions
├── SKILL.md                               # Antigravity skill definition & frontmatter
├── .cursorrules                           # Legacy Cursor rules
├── .gitignore                             # Git ignore for cache and local data
├── .claude/
│   └── commands/
│       └── boomi-code-review.md           # Claude Code slash command
├── .cursor/
│   └── rules/
│       └── boomi-code-review.mdc          # Cursor IDE MDC rule
├── .github/
│   └── copilot-instructions.md            # Codex & GitHub Copilot instructions
├── scripts/
│   └── boomi_code_review.py               # Core Python static analysis engine
└── references/
    ├── checklist.md                       # Comprehensive 7-category review checklist
    └── report_template.md                 # Formal review report template
```

---

## Review Verdict Rules

| Verdict | Criteria | Deployment Action |
|---|---|---|
| **✔ Approved** | 0 Critical, 0 Major issues. | Ready for QA / PROD release. |
| **⚠ Approved with conditions** | 0 Critical issues, ≤ 2 Major issues. | Remediation required before final PROD release. |
| **✖ Rework required** | Any Critical issue, or > 2 Major issues. | **Deployment blocked**. Fix and resubmit for review. |

---

## License & Standards

- **Standard**: Psiog Integrations Boomi Review Checklist
- **Engine**: Python 3.8+ Standard Library (`xml.etree.ElementTree`, `urllib.parse`, `argparse`, `json`, `re`)

# AutoCVE API Documentation

## Table of Contents

- [1. Basic Information](#1-basic-information)
- [2. Authentication](#2-authentication)
- [3. Project Management](#3-project-management)
- [4. Audit Tasks](#4-audit-tasks)
- [5. Agent Audit Tasks](#5-agent-audit-tasks)
- [6. Audit Sessions](#6-audit-sessions)
- [7. Agent Direct Audit](#7-agent-direct-audit)
- [8. Vulnerability Management](#8-vulnerability-management)
- [9. System Configuration](#9-system-configuration)
- [10. Skills Management](#10-skills-management)
- [11. One-Click CVE](#11-one-click-cve)


## 1. Basic Information

### 1.1 Service Addresses

Default addresses for local Docker deployment:

```text
Frontend: http://localhost:3000
Backend: http://localhost:8000
API prefix: http://localhost:8000/api/v1
Swagger UI: http://localhost:8000/docs
OpenAPI JSON: http://localhost:8000/api/v1/openapi.json
```

Health check:

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/health` | Backend health check; returns `{"status":"ok"}` |
| `GET` | `/` | Root path; returns welcome information and demo account tips |

### 1.2 Authentication Method

The login API returns a JWT Token. Except for public APIs, request headers must include:

```http
Authorization: Bearer <access_token>
```

The login API uses OAuth2 Password Form, and `Content-Type` is `application/x-www-form-urlencoded`:

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=demo@example.com&password=demo123"
```

Other JSON APIs generally use:

```http
Content-Type: application/json
Authorization: Bearer <access_token>
```

File upload APIs use:

```http
Content-Type: multipart/form-data
Authorization: Bearer <access_token>
```

### 1.3 Response Format

Most APIs directly return objects or arrays. Error responses are returned uniformly by FastAPI:

```json
{
  "detail": "Error description"
}
```

Time fields are usually ISO-formatted strings, for example:

```text
2026-06-11T10:20:30.000000
```

### 1.4 Common Enumerations

Agent-related status values are subject to the database model and runtime. Common values include:

| Type | Common Values |
| --- | --- |
| Task status | `pending`, `running`, `completed`, `failed`, `cancelled` |
| Agent phase | `orchestrator`, `recon`, `scan`, `triage`, `finding`, `verification` |
| Vulnerability severity | `critical`, `high`, `medium`, `low`, `info` |
| Finding Runtime Stack | `runtime` |
| Audit session message role | `system`, `user`, `assistant`, `tool_use`, `tool_result`, `handoff` |

## 2. Authentication

### 2.1 Authentication APIs

Base path: `/api/v1/auth`

| Method | Path | Authentication | Description |
| --- | --- | --- | --- |
| `POST` | `/login` | No | User login; returns JWT Token |
| `POST` | `/register` | No | Register a user; the first registered user becomes an administrator |

#### POST `/auth/login`

The request body is a form:

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `username` | string | Yes | User email |
| `password` | string | Yes | User password |

Response:

```json
{
  "access_token": "jwt-token",
  "token_type": "bearer"
}
```

#### POST `/auth/register`

Request body:

```json
{
  "email": "user@example.com",
  "password": "password123",
  "full_name": "User Name"
}
```

Response fields:

| Field | Type | Description |
| --- | --- | --- |
| `id` | string | User ID |
| `email` | string | Email |
| `full_name` | string | User name |
| `is_active` | boolean | Whether enabled |
| `is_superuser` | boolean | Whether administrator |
| `role` | string | Role |
| `created_at` | datetime | Creation time |

### 2.2 User APIs

Base path: `/api/v1/users`

| Method | Path | Authentication | Description |
| --- | --- | --- | --- |
| `GET` | `/` | Yes | User list |
| `POST` | `/` | Yes | Create user |
| `GET` | `/me` | Yes | Current user information |
| `PUT` | `/me` | Yes | Update current user information |
| `GET` | `/{user_id}` | Yes | Get specified user |
| `PUT` | `/{user_id}` | Yes | Update specified user |
| `DELETE` | `/{user_id}` | Yes | Delete user |
| `POST` | `/{user_id}/toggle-status` | Yes | Enable/disable user |

User creation fields:

```json
{
  "email": "user@example.com",
  "password": "password123",
  "full_name": "User Name",
  "role": "member",
  "phone": "",
  "github_username": "",
  "gitlab_username": ""
}
```

## 3. Project Management

Base path: `/api/v1/projects`

Project APIs are responsible for creating, importing, viewing, updating, deleting, and restoring projects, and provide project file browsing, file content reading, ZIP management, branch query, and project scan entry points.

### 3.1 Project API Overview

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/managed-local-directories` | Get the list of local directories managed by the backend |
| `POST` | `/` | Create project |
| `GET` | `/` | Get project list |
| `GET` | `/deleted` | Get recycle-bin project list |
| `GET` | `/stats` | Get project statistics |
| `POST` | `/repository-branches` | Query remote repository branches |
| `GET` | `/{id}` | Get project details |
| `PUT` | `/{id}` | Update project |
| `DELETE` | `/{id}` | Soft-delete project |
| `POST` | `/{id}/restore` | Restore soft-deleted project |
| `DELETE` | `/{id}/permanent` | Permanently delete project |
| `GET` | `/{id}/files` | Get project file tree |
| `GET` | `/{id}/file-content` | Get specified file content |
| `POST` | `/{id}/scan` | Create a regular scan task based on the project |
| `GET` | `/{id}/zip` | View project ZIP file information |
| `POST` | `/{id}/zip` | Upload or replace project ZIP |
| `DELETE` | `/{id}/zip` | Delete project ZIP |
| `POST` | `/{id}/source-artifacts/delete` | Delete ZIP or persisted source-code artifacts |
| `GET` | `/{id}/branches` | Get project repository branches |

### 3.2 Create Project

`POST /api/v1/projects/`

Request body:

```json
{
  "name": "demo-project",
  "source_type": "repository",
  "repository_url": "https://github.com/example/demo.git",
  "repository_type": "github",
  "local_path": null,
  "workspace_mode": null,
  "description": "Test project",
  "default_branch": "main",
  "programming_languages": ["python", "javascript"]
}
```

Field description:

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | Yes | Project name |
| `source_type` | string | No | `repository`, `zip`, or local directory mode |
| `repository_url` | string | No | Git repository URL |
| `repository_type` | string | No | `github`, `gitlab`, `other` |
| `local_path` | string | No | Local path |
| `workspace_mode` | string | No | Workspace mode |
| `description` | string | No | Project description |
| `default_branch` | string | No | Default branch |
| `programming_languages` | string[] | No | Project languages |

Core response fields:

| Field | Type | Description |
| --- | --- | --- |
| `id` | string | Project ID |
| `name` | string | Project name |
| `source_type` | string | Source type |
| `repository_url` | string | Repository URL |
| `local_path` | string | Local path |
| `default_branch` | string | Default branch |
| `programming_languages` | string[] | Languages |
| `is_active` | boolean | Whether enabled |
| `created_at` | datetime | Creation time |
| `owner` | object | Project owner |

### 3.3 Read File Content

`GET /api/v1/projects/{id}/file-content?path=<relative_path>`

Response:

```json
{
  "path": "src/app.py",
  "content": "file content",
  "size": 1024,
  "truncated": false
}
```

### 3.4 Upload Project ZIP

`POST /api/v1/projects/{id}/zip`

Request type: `multipart/form-data`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `file` | file | Yes | ZIP file |

The response is ZIP metadata:

```json
{
  "has_file": true,
  "original_filename": "demo.zip",
  "file_size": 123456,
  "uploaded_at": "2026-06-11T10:00:00",
  "has_persistent_source": true,
  "persistent_source_path": "...",
  "persistent_source_updated_at": "2026-06-11T10:00:00"
}
```

### 3.5 Query Repository Branches

`POST /api/v1/projects/repository-branches`

```json
{
  "repository_url": "https://github.com/example/demo.git",
  "repository_type": "github"
}
```

Response:

```json
{
  "branches": ["main", "develop"],
  "default_branch": "main",
  "error": null
}
```

## 4. Audit Tasks

Base path: `/api/v1/tasks`

This API group targets regular scan tasks and historical task records. Agent-based audit tasks use `/agent-tasks`.

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/` | Get task list |
| `GET` | `/{id}` | Get task details |
| `POST` | `/{id}/cancel` | Cancel task |
| `GET` | `/{id}/issues` | Get issues discovered by the task |
| `PATCH` | `/{task_id}/issues/{issue_id}` | Update issue status |
| `GET` | `/{id}/report/pdf` | Export task PDF report |

Issue update request:

```json
{
  "status": "resolved",
  "is_false_positive": false
}
```

## 5. Agent Audit Tasks

Base path: `/api/v1/agent-tasks`

Agent tasks are AutoCVE's core audit entry point. They start the Orchestrator and execute nodes such as Recon, Scan, Triage, Finding, and Verification according to the workflow.

### 5.1 Agent Task API Overview

| Method | Path | Description |
| --- | --- | --- |
| `POST` | `/` | Create Agent audit task |
| `GET` | `/` | Get Agent task list |
| `GET` | `/debug-tasks` | Get debug task list |
| `GET` | `/{task_id}` | Get task details |
| `GET` | `/{task_id}/debug-trace` | Get task debug trace |
| `POST` | `/{task_id}/resume` | Resume task |
| `POST` | `/{task_id}/cancel` | Cancel task |
| `GET` | `/{task_id}/events` | Get event stream or event data |
| `GET` | `/{task_id}/stream` | SSE real-time task stream |
| `GET` | `/{task_id}/events/list` | Get event list |
| `GET` | `/{task_id}/findings` | Get task vulnerability list |
| `GET` | `/{task_id}/findings/{finding_id}` | Get a single vulnerability |
| `GET` | `/{task_id}/summary` | Get task summary |
| `PATCH` | `/{task_id}/findings/{finding_id}` | Update vulnerability status or manual information |
| `GET` | `/{task_id}/tree` | Get Agent execution tree |
| `GET` | `/{task_id}/checkpoints` | Get Runtime checkpoints |
| `GET` | `/{task_id}/checkpoints/{checkpoint_id}` | Get checkpoint details |
| `GET` | `/{task_id}/report` | Get task report |

### 5.2 Create Agent Audit Task

`POST /api/v1/agent-tasks/`

Request body:

```json
{
  "project_id": "project-id",
  "name": "demo version audit",
  "description": "Audit the authentication and file upload logic of version v1.0.0",
  "audit_scope": {
    "mode": "targeted"
  },
  "target_vulnerabilities": ["RCE", "SQL Injection", "Path Traversal"],
  "verification_level": "sandbox",
  "version_label": "v1.0.0",
  "version_tag": "v1.0.0",
  "branch_name": "main",
  "exclude_patterns": ["node_modules", "__pycache__", ".git", "*.min.js"],
  "target_files": ["src/auth.py", "src/upload.py"],
  "max_iterations": 50,
  "timeout_seconds": 1800,
  "finding_runtime_stack": "runtime"
}
```

Field description:

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `project_id` | string | Yes | Project ID |
| `name` | string | No | Task name |
| `description` | string | No | Task description |
| `audit_scope` | object | No | Audit scope configuration |
| `target_vulnerabilities` | string[] | No | Priority vulnerability types |
| `verification_level` | string | No | `analysis_only`, `sandbox`, `generate_poc` |
| `version_label` | string | Yes | Version label entered by the user |
| `version_tag` | string | No | Git tag |
| `branch_name` | string | No | Git branch |
| `exclude_patterns` | string[] | No | Exclusion rules |
| `target_files` | string[] | No | Target files |
| `max_iterations` | int | No | Maximum iterations: 1-200 |
| `timeout_seconds` | int | No | Timeout: 10-7200 |
| `finding_runtime_stack` | string | No | Currently recommended to use `runtime` |

Core response fields:

| Field | Type | Description |
| --- | --- | --- |
| `id` | string | Task ID |
| `project_id` | string | Project ID |
| `status` | string | Task status |
| `current_phase` | string | Current phase |
| `progress_percentage` | number | Progress |
| `findings_count` | int | Vulnerability count |
| `verified_count` | int | Verified count |
| `runtime_session_id` | string | Finding Runtime session ID |
| `runtime_completion_mode` | string | Runtime completion mode |
| `created_at` | datetime | Creation time |

### 5.3 Get Events and Real-Time Stream

Event list:

```http
GET /api/v1/agent-tasks/{task_id}/events/list
```

SSE real-time stream:

```http
GET /api/v1/agent-tasks/{task_id}/stream
Accept: text/event-stream
```

Core event response fields:

| Field | Type | Description |
| --- | --- | --- |
| `id` | string | Event ID |
| `task_id` | string | Task ID |
| `event_type` | string | Event type |
| `phase` | string | Phase |
| `message` | string | Display message |
| `sequence` | int | Sequence number |
| `tool_name` | string | Tool name |
| `tool_input` | object | Tool input |
| `tool_output` | object | Tool output |
| `metadata` | object | Extended information |

### 5.4 Get Vulnerability Results

```http
GET /api/v1/agent-tasks/{task_id}/findings
GET /api/v1/agent-tasks/{task_id}/findings/{finding_id}
PATCH /api/v1/agent-tasks/{task_id}/findings/{finding_id}
```

Core vulnerability response fields:

| Field | Type | Description |
| --- | --- | --- |
| `id` | string | Finding ID |
| `vulnerability_type` | string | Vulnerability type |
| `severity` | string | Severity |
| `title` | string | Title |
| `description` | string | Description |
| `file_path` | string | File path |
| `line_start` / `line_end` | int | Start/end line |
| `code_snippet` | string | Code snippet |
| `is_verified` | boolean | Whether verified |
| `confidence` | number | Confidence |
| `status` | string | Status |
| `poc` | object | PoC information |
| `exploit_chain` | object[] | Exploit chain |
| `impact` | string | Impact |
| `cve_justification` | string | CVE value justification |

### 5.5 Get Task Summary

`GET /api/v1/agent-tasks/{task_id}/summary`

Response:

```json
{
  "task_id": "task-id",
  "status": "completed",
  "security_score": 78,
  "total_findings": 3,
  "verified_findings": 1,
  "severity_distribution": {
    "critical": 0,
    "high": 1,
    "medium": 2
  },
  "vulnerability_types": {
    "Path Traversal": 1
  },
  "duration_seconds": 300,
  "phases_completed": ["recon", "finding", "verification"]
}
```

## 6. Audit Sessions

Base path: `/api/v1/audit-sessions`

Audit session APIs are used to view messages, tool calls, Skill calls, Memory, and Handoff in Runtime sessions, and support continuing a conversation around one audit.

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/{session_id}` | Get session details |
| `GET` | `/{session_id}/messages` | Get session messages |
| `GET` | `/{session_id}/tool-calls` | Get tool calls |
| `GET` | `/{session_id}/skills` | Get session Skill list |
| `GET` | `/{session_id}/skill-invocations` | Get Skill invocation records |
| `GET` | `/{session_id}/memories` | Get Memory |
| `GET` | `/{session_id}/handoffs` | Get Handoff |
| `POST` | `/{session_id}/messages` | Append user message and get a regular response |
| `POST` | `/{session_id}/messages/stream` | Append user message and get a streaming response |

Append message request:

```json
{
  "content": "Please continue analyzing whether this vulnerability has CVE submission value.",
  "mode": "chat",
  "selected_skill_refs": ["cve-report-writer"]
}
```

Core message response fields:

| Field | Type | Description |
| --- | --- | --- |
| `id` | string | Message ID |
| `session_id` | string | Session ID |
| `sequence` | int | Sequence number |
| `role` | string | Role |
| `content` | string | Content |
| `metadata` | object | Metadata |
| `created_at` | datetime | Creation time |

## 7. Agent Direct Audit

Base path: `/api/v1/agent-direct-audit`

The direct audit APIs are used to create a project-bound audit session and talk with the Agent directly without going through the full Agent task workflow. They are suitable for debugging Finding Runtime, supplementing manual follow-up questions, verifying tool calls, and generating vulnerability reports.

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/sessions` | Get direct audit session list |
| `POST` | `/sessions` | Create direct audit session |
| `POST` | `/sessions/stream` | Create session and run in streaming mode |
| `GET` | `/sessions/{session_id}` | Get session details |
| `PATCH` | `/sessions/{session_id}/guardrails` | Update guardrails switch |
| `GET` | `/sessions/{session_id}/messages` | Get messages |
| `POST` | `/sessions/{session_id}/messages` | Send message |
| `POST` | `/sessions/{session_id}/messages/stream` | Send message and stream response |
| `POST` | `/sessions/{session_id}/tool-calls/{tool_call_id}/approve/stream` | Approve tool call and continue streaming execution |
| `GET` | `/sessions/{session_id}/managed-vulnerabilities` | Get vulnerabilities associated with the session |
| `POST` | `/sessions/{session_id}/managed-vulnerabilities/sync-latest-report` | Sync latest report to vulnerability management |

Create session request:

```json
{
  "project_id": "project-id",
  "content": "Please focus on auditing file upload related logic.",
  "guardrails_enabled": false
}
```

Tool approval request:

```json
{
  "scope": "single_use"
}
```

Optional values for `scope`:

- `single_use`: Approve only this tool call.
- `session`: Approve within the current session.

## 8. Vulnerability Management

Base path: `/api/v1/vulnerabilities`

Vulnerability management APIs target final structured vulnerability assets, which are different from task-scoped Findings in `/agent-tasks/{task_id}/findings`.

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/` | Get vulnerability list |
| `GET` | `/{vulnerability_id}` | Get vulnerability details |
| `PATCH` | `/{vulnerability_id}` | Update vulnerability manual status, CVE status, etc. |
| `DELETE` | `/{vulnerability_id}` | Delete vulnerability |
| `GET` | `/{vulnerability_id}/reports` | Get vulnerability report list |
| `GET` | `/{vulnerability_id}/reports/{report_kind}` | Get specified report type |
| `PATCH` | `/{vulnerability_id}/reports/{report_kind}` | Update report Markdown |
| `GET` | `/{vulnerability_id}/reports/{report_kind}/export` | Export report |

Vulnerability update request:

```json
{
  "vulnerability_name": "Path Traversal in file download",
  "vulnerability_type": "Path Traversal",
  "severity": "high",
  "human_review_result": "confirmed",
  "cve_request_status": "drafting",
  "cve_failure_reason": null,
  "cve_id": null
}
```

Report update request:

```json
{
  "markdown_content": "# Vulnerability Report\n\n...",
  "source_type": "manual"
}
```

Core vulnerability list response fields:

| Field | Type | Description |
| --- | --- | --- |
| `id` | string | Vulnerability ID |
| `project_id` | string | Project ID |
| `task_id` | string | Source task ID |
| `finding_id` | string | Source Finding ID |
| `project_name` | string | Project name |
| `vulnerability_name` | string | Vulnerability name |
| `vulnerability_type` | string | Vulnerability type |
| `severity` | string | Severity |
| `human_review_result` | string | Manual review result |
| `cve_request_status` | string | CVE submission status |
| `cve_id` | string | CVE ID |
| `report_generation_status` | string | Report generation status |

## 9. System Configuration

Base path: `/api/v1/config`

System configuration APIs manage user-level model configuration, model plans for different Agents, workflow switches, Tokens, connection tests, and asset synchronization.

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/defaults` | Get default configuration |
| `GET` | `/me` | Get current user configuration |
| `PUT` | `/me` | Save current user configuration |
| `DELETE` | `/me` | Delete current user configuration and restore defaults |
| `POST` | `/test-llm` | Test model connection |
| `POST` | `/test-agent-model` | Test a model configuration for a specific Agent |
| `POST` | `/sync-assets` | Sync Skills and report template assets |
| `GET` | `/llm-providers` | Get supported model providers |

Save configuration request:

```json
{
  "llmConfig": {
    "llmProvider": "openai",
    "llmApiKey": "sk-xxx",
    "llmModel": "gpt-4o-mini",
    "llmBaseUrl": "https://api.openai.com/v1",
    "llmTimeout": 150,
    "llmTemperature": 0.1,
    "llmMaxTokens": 4096,
    "endpointProtocol": "openai",
    "toolMessageFormat": "openai",
    "agentConfigs": {
      "finding": {
        "enabled": true,
        "llmProvider": "deepseek",
        "llmApiKey": "xxx",
        "llmModel": "deepseek-chat",
        "llmBaseUrl": "https://api.deepseek.com/v1",
        "maxIterations": 50
      }
    },
    "modelProfiles": [
      {
        "id": "profile-1",
        "name": "Default plan",
        "isDefault": true,
        "llmProvider": "openai",
        "llmModel": "gpt-4o-mini"
      }
    ]
  },
  "otherConfig": {
    "githubToken": "ghp_xxx",
    "gitlabToken": "glpat_xxx",
    "maxAnalyzeFiles": 0,
    "llmConcurrency": 3,
    "llmGapMs": 2000,
    "outputLanguage": "zh-CN",
    "workflowConfig": {
      "recon": true,
      "scan": true,
      "triage": true,
      "finding": true,
      "verification": true
    }
  }
}
```

Test model request:

```json
{
  "provider": "openai",
  "apiKey": "sk-xxx",
  "model": "gpt-4o-mini",
  "baseUrl": "https://api.openai.com/v1",
  "endpointProtocol": "openai",
  "toolMessageFormat": "openai",
  "prompt": "Please only reply: model connection succeeded."
}
```

## 10. Skills Management

Base path: `/api/v1/skills`

Skills APIs are used to import, create, edit, and delete Skills, and to configure binding relationships for different Agents.

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/` | Get Skill list |
| `GET` | `/{skill_id}` | Get Skill details |
| `POST` | `/` | Create Skill |
| `POST` | `/import-github` | Import Skill from GitHub |
| `POST` | `/upload-zip` | Upload ZIP to import Skill |
| `PUT` | `/{skill_id}` | Update Skill |
| `DELETE` | `/{skill_id}` | Delete Skill |
| `POST` | `/{skill_id}/bindings` | Create Skill binding for an Agent |
| `PUT` | `/{skill_id}/bindings/{binding_id}` | Update binding |
| `DELETE` | `/{skill_id}/bindings/{binding_id}` | Delete binding |
| `POST` | `/resync` | Resync Skill library |

Create Skill request:

```json
{
  "name": "Code Audit Finding",
  "slug": "code-audit-finding",
  "description": "Code audit Skill for Finding Agent",
  "source_type": "manual",
  "source_url": null,
  "content": "# Skill\n\n...",
  "tags": ["security", "finding"],
  "frontmatter": {},
  "extension_manifest": [],
  "extension_payload": {},
  "is_active": true,
  "is_system": false,
  "bindings": [
    {
      "agent_type": "finding",
      "enabled": true,
      "always_include": false,
      "sort_order": 0,
      "match_keywords": ["RCE", "SQL Injection"],
      "match_config": {}
    }
  ]
}
```

Import from GitHub:

```json
{
  "repo_url": "https://github.com/example/audit-skill",
  "agent_type": "finding",
  "bind_to_agent": true,
  "enabled": true,
  "always_include": false,
  "match_keywords": ["cve", "audit"]
}
```

## 11. One-Click CVE

Base path: `/api/v1/one-click-cve`

One-click CVE APIs are used to create batch tasks, automatically select GitHub projects, and continuously create Agent audit tasks until the target number of CVE candidates is found.

| Method | Path | Description |
| --- | --- | --- |
| `POST` | `/batches` | Create one-click CVE batch |
| `GET` | `/batches` | Get batch list |
| `GET` | `/batches/{batch_id}` | Get batch details |
| `POST` | `/batches/{batch_id}/cancel` | Cancel batch |

Create batch request:

```json
{
  "target_count": 3,
  "prefer_security_advisory": true
}
```

Core response fields:

| Field | Type | Description |
| --- | --- | --- |
| `id` | string | Batch ID |
| `user_id` | string | User ID |
| `requested_count` | int | Target count |
| `found_count` | int | Number found |
| `status` | string | Batch status |
| `prefer_security_advisory` | boolean | Whether to prioritize security advisory projects |
| `projects` | object[] | Projects processed in this batch |

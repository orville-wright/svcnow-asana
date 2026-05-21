# Asana Challenge

A collection of tools for working with a specific Asana project via the Asana REST API. The repo contains three runnable interfaces — a terminal chatbot (`asana_agent.py`), a REPL copilot backed by the official Asana SDK (`asana_REPL_copilot.py`), and a FastMCP server for Claude Code / AI agent use (`asana_mcp_server.py`) — plus a credential validation helper and a set of early prototypes.

## Target Asana Project

| | |
|---|---|
| Workspace GID | `1214958615680522` |
| Project GID | `1214982995972383` |
| Active task filter | Not completed **and** not in a section named `Implemented` |

---

## Project Structure

```
asana_challenge/
├── asana_agent.py          # Terminal chatbot (requests + rich)
├── asana_mcp_server.py     # FastMCP stdio server (4 tools)
├── asana_REPL_copilot.py   # REPL copilot (official Asana SDK)
├── svcnow_a_challenge.py   # Credential / API validation helper
├── prototypes/
│   ├── a_asana_1.py        # Workspace membership lookup (SDK)
│   ├── b_asana_1.py        # Token verification (raw requests)
│   └── c_asana_1.py        # User info + memberships (SDK)
├── tests/
│   ├── test_asana_agent.py
│   └── test_asana_mcp_server.py
├── .env.example
├── .mcp.json               # MCP server wiring for Claude Code
└── pyproject.toml
```

---

## Setup

Requires **Python 3.13+** and [uv](https://docs.astral.sh/uv/).

```bash
cp .env.example .env
# fill in ASANA_TOKEN in .env
uv sync
```

### Environment variables

| Variable | Required | Default | Notes |
|---|---|---|---|
| `ASANA_TOKEN` | Yes | — | Asana Personal Access Token |
| `ASANA_WORKSPACE_GID` | Yes | — | Workspace GID |
| `ASANA_PROJECT_GID` | Yes | — | Project GID |
| `ASANA_API_BASE` | No | `https://app.asana.com/api/1.0` | Override for proxies |
| `ASANA_IMPLEMENTED_SECTION_NAME` | No | `Implemented` | Section name to exclude from active tasks |

If `ASANA_TOKEN` is not set when running `asana_agent.py`, the agent prompts for it without saving it.

---

## asana_agent.py — Terminal Chatbot

An interactive terminal chatbot built on `requests` and `rich`. Authenticates at startup, then accepts free-text commands in a REPL loop.

### Run

```bash
uv run python asana_agent.py
```

On Windows (PowerShell):
```powershell
$env:ASANA_TOKEN="your-token"
python asana_agent.py
```

### What it can do

| Command examples | Action |
|---|---|
| `create a task` | Prompts for description and due date, then creates the task |
| `show active tasks`, `list`, `display open tasks` | Lists active tasks as a rich table |
| `close the first task`, `close 002`, `complete 1214982880426742` | Marks one or more tasks complete |
| `mark done top 3` | Closes the first three tasks in the list |
| `goodbye`, `quit`, `exit` | Exits |

Tasks are displayed in a table with columns: **Row ID**, **Asana Task id**, **Task title**.

### Supported due-date formats

```
today           tomorrow        next week
3 days from now
05/22/2026      5/22/26         2026-05-22
May 22, 2026    May 22 2026
```

### Task selection syntax

Tasks can be identified by:
- **Row ID**: `001`, `2`, `003`
- **Ordinal**: `first`, `second`, `third` … `tenth`
- **Positional suffix**: `1st`, `2nd`, `3rd`
- **Asana task GID**: full numeric GID
- **Title**: exact or partial match (disambiguated interactively if ambiguous)
- **Batch**: `top 3`, `top 5`

### Manual verification steps

1. `uv run python asana_agent.py`
2. Create a task.
3. `show active tasks` — confirm the new task appears.
4. Close that task by row ID, GID, or title.
5. `show active tasks` — confirm the task is no longer listed.
6. `goodbye` to exit.

---

## asana_REPL_copilot.py — SDK-based REPL Copilot

An alternative REPL built on the **official Asana Python SDK** (`asana>=5.2.4`). It runs a scripted demo conversation first, then drops into an interactive loop.

### Run

```bash
uv run python asana_REPL_copilot.py
```

Requires `ASANA_TOKEN` and `ASANA_PROJECT_GID` in the environment (or `.env`).

### Features

- **Multi-turn task creation**: inline title extraction from `create a task called X`, or step-by-step prompting if no title is found.
- **Due-date parsing**: `today`, `tomorrow`, `tmrw`, `next week`, `YYYY-MM-DD`.
- **List open tasks**: fetches all non-completed tasks and prints GID, name, and due date.
- **Close a task**: keyword-matches the user's message against open task titles.
- **Scripted demo feed**: replays a fixed set of turns before going interactive, useful for quick live demos.
- **Clean SDK shutdown**: explicitly closes the Asana SDK thread pool to prevent hang on exit.

### Scripted demo turns

```
I want to create a task
Complete Take Home Assignment for Moveworks Product Management Interview
Tomorrow
What tasks are open?
Can we close the Take Home one?
```

---

## asana_mcp_server.py — FastMCP Stdio Server

A [FastMCP](https://github.com/jlowin/fastmcp) stdio MCP server that exposes four tools for use with Claude Code, OpenAI Codex, or any MCP-compatible AI agent.

### Tools

| Tool | Parameters | Description |
|---|---|---|
| `create_asana_task` | `description`, `due_date` | Create a task in the configured project |
| `list_asana_tasks` | — | List active tasks; returns a table with **Due Date** column |
| `close_asana_task` | `task_ref` | Mark one or more tasks complete |
| `modify_asana_task` | `task_ref`, `description?`, `due_date?` | Update a task's title and/or due date |

`task_ref` accepts the same syntax as `asana_agent.py`: row ID, ordinal, GID, partial title, or `top N`.

`list_asana_tasks` and `close_asana_task` cache the most recently fetched task list in module state so consecutive calls within a session avoid redundant network round-trips.

### Run

```bash
uv run python asana_mcp_server.py
```

### Claude Code integration

The repo ships with `.mcp.json` pre-configured:

```json
{
  "mcpServers": {
    "asana": {
      "command": "uv",
      "args": ["run", "python", "asana_mcp_server.py"],
      "cwd": "/home/dbrace/code/asana_challenge"
    }
  }
}
```

Claude Code picks this up automatically. The four tools appear as `mcp__asana__create_asana_task`, `mcp__asana__list_asana_tasks`, `mcp__asana__close_asana_task`, and `mcp__asana__modify_asana_task`.

---

## svcnow_a_challenge.py — Credential Validation Helper

Runs three sequential validation checks against the Asana API to confirm credentials and connectivity before using the main tools.

| Check | Method | What it verifies |
|---|---|---|
| 1 | Asana SDK `WorkspaceMembershipsApi` | Workspace membership is accessible |
| 2 | Raw `requests` to `/users/me` | PAT is valid; lists user name, email, and workspaces |
| 3 | Asana SDK `UsersApi` + `WorkspaceMembershipsApi` | Full user record and workspace membership list |

```bash
uv run python svcnow_a_challenge.py
```

Output is colored via `rich`.

---

## prototypes/

Early exploration scripts kept for reference.

| File | What it does |
|---|---|
| `a_asana_1.py` | Workspace membership lookup via the Asana SDK |
| `b_asana_1.py` | Token verification via raw `requests` to `/users/me` |
| `c_asana_1.py` | Authenticated user info and workspace memberships via the Asana SDK |

These are standalone scripts; run them with `ASANA_TOKEN` set in the environment.

---

## Tests

Automated tests cover date parsing, intent detection, active-task filtering, task selection/resolution, API client pagination and error handling, and all four MCP tool functions. No live Asana writes are made.

```bash
uv run python -m unittest discover -s tests
```

Or with standard Python:

```bash
python -m unittest discover -s tests
```

### Test coverage

| Test file | Covers |
|---|---|
| `tests/test_asana_agent.py` | `parse_due_date`, `detect_intent`, `is_active_task`, `summarize_active_tasks`, `select_tasks`, `strip_close_words`, `format_prompt` |
| `tests/test_asana_mcp_server.py` | `load_config`, `parse_due_date`, `is_active_task`, `summarize_active_tasks`, `format_task_table`, `resolve_task_reference`, `AsanaClient` (create, list with pagination, error surface, modify), and all four MCP tool functions via mocked `AsanaClient` |

---

## Dependencies

Declared in `pyproject.toml` (Python 3.13+):

| Package | Purpose |
|---|---|
| `asana>=5.2.4` | Official Asana SDK (used by `asana_REPL_copilot.py` and `svcnow_a_challenge.py`) |
| `fastmcp>=2.13.0` | MCP server framework |
| `python-dotenv>=1.2.1` | `.env` file loading |
| `requests>=2.34.2` | HTTP client for `asana_agent.py` and `asana_mcp_server.py` |
| `rich>=15.0.0` | Colored terminal output |

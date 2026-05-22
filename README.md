# Asana Challenge

A collection of tools for working with a specific Asana project via the Asana REST API. The repo contains one production-ready MCP server (`asana_mcp_server.py`) and two prototype conversational interfaces — a terminal chatbot and an SDK-backed REPL copilot — both housed in `prototypes/`, plus a credential validation helper and a set of early exploration scripts.


## LOOM Demo video  (4:50 mins)
https://www.loom.com/share/70620a8a683448c6b0cb7883f977769a


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
├── asana_mcp_server.py              # FastMCP stdio server (4 tools)
├── preflight_checker.py             # Credential / API validation helper
├── prototypes/
│   ├── asana_basic_REPL_agent.py   # Terminal chatbot (requests + rich)
│   ├── asana_full_REPL_copilot.py  # REPL copilot (official Asana SDK)
│   ├── a_asana_1.py                # Workspace membership lookup (SDK)
│   ├── b_asana_1.py                # Token verification (raw requests)
│   └── c_asana_1.py                # User info + memberships (SDK)
├── tests/
│   ├── test_asana_agent.py
│   └── test_asana_mcp_server.py
├── serviceNOW_challenge_Dave-Brace.pdf
├── serviceNOW_memo_2.pdf
├── .env.example
├── .mcp.json                        # MCP server wiring for Claude Code
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

If `ASANA_TOKEN` is not set when running the prototype scripts, they prompt for it interactively without saving it.

---

## The main solution
My final solution to the Take Home Challenge is the asana_mcp_server.py


### How to run
- Please install the MCP server into Claude Code or OpenAI Codex
   - Simply ask Claude (or Codex) to install the asana_mcp_server.py for you
   - Check that 4 MCP new tools are now available... (you may need to exit/restart or force a Refresh)
   - You can now conversationally interact with Asana project tasks. The new tools will do all the work for you.
   - You will need to add the ASANA env vars to the .env file
   - All of that info is provided in the serviceNOW_challenge_1 PDF doc. - (I will securely nuke that info later)


## Asana_mcp_server.py — FastMCP Stdio Server

A [FastMCP](https://github.com/jlowin/fastmcp) stdio MCP server that exposes four tools for use with Claude Code, OpenAI Codex, or any MCP-compatible AI agent.

### MCP Tools

| Tool | Parameters | Description |
|---|---|---|
| `create_asana_task` | `description`, `due_date` | Create a task in the configured project |
| `list_asana_tasks` | — | List active tasks; returns a table with **Due Date** column |
| `close_asana_task` | `task_ref` | Mark one or more tasks complete |
| `modify_asana_task` | `task_ref`, `description?`, `due_date?` | Update a task's title and/or due date |

`task_ref` accepts row ID, ordinal, GID, partial title, or `top N`.

`list_asana_tasks` and `close_asana_task` cache the most recently fetched task list in module state so consecutive calls within a session avoid redundant network round-trips.



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

# Early phase prototype tools and V1, V2 experiments

## preflight_checker.py — Credential Validation Helper

Runs three sequential validation checks against the Asana API to confirm credentials and connectivity before using the main tools.

| Check | Method | What it verifies |
|---|---|---|
| 1 | Asana SDK `WorkspaceMembershipsApi` | Workspace membership is accessible |
| 2 | Raw `requests` to `/users/me` | PAT is valid; lists user name, email, and workspaces |
| 3 | Asana SDK `UsersApi` + `WorkspaceMembershipsApi` | Full user record and workspace membership list |

```bash
uv run python preflight_checker.py
```

Output is colored via `rich`.

---

## prototypes/

Prototype and exploratory scripts kept for reference.

### asana_basic_REPL_agent.py — Terminal Chatbot

An interactive terminal chatbot built on `requests` and `rich`. Authenticates at startup, then accepts free-text commands in a REPL loop.

#### Run

```bash
uv run python prototypes/asana_basic_REPL_agent.py
```

#### What it can do

| Command examples | Action |
|---|---|
| `create a task` | Prompts for description and due date, then creates the task |
| `show active tasks`, `list`, `display open tasks` | Lists active tasks as a rich table |
| `close the first task`, `close 002`, `complete 1214982880426742` | Marks one or more tasks complete |
| `mark done top 3` | Closes the first three tasks in the list |
| `goodbye`, `quit`, `exit` | Exits |

Tasks are displayed in a table with columns: **Row ID**, **Asana Task id**, **Task title**.

#### Supported due-date formats

```
today           tomorrow        next week
3 days from now
05/22/2026      5/22/26         2026-05-22
May 22, 2026    May 22 2026
```

#### Task selection syntax

Tasks can be identified by:
- **Row ID**: `001`, `2`, `003`
- **Ordinal**: `first`, `second`, `third` … `tenth`
- **Positional suffix**: `1st`, `2nd`, `3rd`
- **Asana task GID**: full numeric GID
- **Title**: exact or partial match (disambiguated interactively if ambiguous)
- **Batch**: `top 3`, `top 5`

---

### asana_full_REPL_copilot.py — SDK-based REPL Copilot

A conversational REPL built on the **official Asana Python SDK** (`asana>=5.2.4`). Uses a layered architecture — a storage-agnostic `Copilot` conversation layer over an `AsanaStore` data layer — and runs in interactive mode.

#### Run

```bash
uv run python prototypes/asana_full_REPL_copilot.py
```

Requires `ASANA_TOKEN` and `ASANA_PROJECT_GID` in the environment (or `.env`).

#### Features

- **Multi-turn task creation**: inline title extraction from `create a task called X`, or step-by-step prompting if no title is found.
- **Due-date parsing**: `today`, `tomorrow`, `tmrw`, `next week`, `YYYY-MM-DD`.
- **List open tasks**: fetches all non-completed tasks and prints GID, name, and due date.
- **Close a task**: keyword-matches the user's message against open task titles.
- **Clean SDK shutdown**: explicitly closes the Asana SDK thread pool to prevent hang on exit.

---

### Early exploration scripts

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
| `asana>=5.2.4` | Official Asana SDK (used by `asana_full_REPL_copilot.py` and `preflight_checker.py`) |
| `fastmcp>=2.13.0` | MCP server framework |
| `python-dotenv>=1.2.1` | `.env` file loading |
| `requests>=2.34.2` | HTTP client for `asana_basic_REPL_agent.py` and `asana_mcp_server.py` |
| `rich>=15.0.0` | Colored terminal output |

# Asana Challenge Agent

This repo contains a small terminal chatbot for working with a specific Asana
project. It uses the same credential pattern proven in `svcnow_a_challenge.py`:
an Asana Personal Access Token supplied through `ASANA_TOKEN`.

## Target Asana Project

- Workspace GID: `1214958615680522`
- Project GID: `1214982995972383`
- Active task filter: tasks are shown when they are not completed and are not
  in a section named `Implemented`.

## Run

In PowerShell:

```powershell
$env:ASANA_TOKEN="your-asana-personal-access-token"
python asana_agent.py
```

If `ASANA_TOKEN` is not set, the agent prompts for the token without saving it.

The agent starts with:

```text
hello, how can I help you in Asana today?
```

You can then ask it to:

- Create a task, for example `create a task`.
- List active tasks, for example `show active tasks`.
- Close a task, for example `close the first task`, `close 001`, or
  `complete 1214982880426742`.
- Exit, for example `goodbye` or `quit`.

## Create Task Date Inputs

Supported due-date inputs include:

- `today`
- `tomorrow`
- `3 days from now`
- `next week`
- `05/22/2026`
- `5/22/26`
- `2026-05-22`
- `May 22, 2026`

## Manual Verification

1. Set `$env:ASANA_TOKEN`.
2. Run `python asana_agent.py`.
3. Create a task.
4. List active tasks and confirm the new task appears.
5. Close that task by list number, task id, or title.
6. List active tasks again and confirm the closed task is no longer active.
7. Type `goodbye` to exit.

## Tests

The automated tests cover date parsing, intent detection, active-task filtering,
and task selection. They do not perform live Asana writes.

```powershell
python -m unittest discover -s tests
```

## FastMCP Asana Server

The repo also includes `asana_mcp_server.py`, a stdio MCP server for Claude Code
and OpenAI Codex. It exposes three tools:

- `create_asana_task`
- `list_asana_tasks`
- `close_asana_task`

Create a local `.env` from `.env.example`:

```bash
cp .env.example .env
```

Set these required values:

```dotenv
ASANA_TOKEN=your-asana-personal-access-token
ASANA_WORKSPACE_GID=1214958615680522
ASANA_PROJECT_GID=1214982995972383
```

Optional values:

```dotenv
ASANA_API_BASE=https://app.asana.com/api/1.0
ASANA_IMPLEMENTED_SECTION_NAME=Implemented
```

Run the MCP server over stdio with uv:

```bash
uv run python asana_mcp_server.py
```

Example MCP client command configuration:

```json
{
  "command": "uv",
  "args": ["run", "python", "asana_mcp_server.py"]
}
```

On Windows, use the same command from the repo root after installing `uv` and
creating `.env`.

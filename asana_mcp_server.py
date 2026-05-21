from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import requests

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - dependency is declared for runtime use.
    load_dotenv = None

try:
    from fastmcp import FastMCP
except ImportError:  # pragma: no cover - lets pure logic tests run before install.
    FastMCP = None


DEFAULT_ASANA_API_BASE = "https://app.asana.com/api/1.0"
DEFAULT_IMPLEMENTED_SECTION_NAME = "Implemented"
TASK_OPT_FIELDS = "gid,name,completed,memberships.section.name"
LAST_ACTIVE_TASKS: list["TaskSummary"] = []


@dataclass(frozen=True)
class AsanaConfig:
    token: str
    workspace_gid: str
    project_gid: str
    api_base: str = DEFAULT_ASANA_API_BASE
    implemented_section_name: str = DEFAULT_IMPLEMENTED_SECTION_NAME


@dataclass(frozen=True)
class TaskSummary:
    list_number: int
    gid: str
    title: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "list_number": f"{self.list_number:03}",
            "asana_task_id": self.gid,
            "task_title": self.title,
        }


class AsanaConfigError(RuntimeError):
    pass


class AsanaApiError(RuntimeError):
    pass


def load_environment() -> None:
    if load_dotenv is not None:
        load_dotenv()
        return

    env_path = Path(".env")
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def load_config() -> AsanaConfig:
    load_environment()
    missing = [
        name
        for name in ("ASANA_TOKEN", "ASANA_WORKSPACE_GID", "ASANA_PROJECT_GID")
        if not os.environ.get(name, "").strip()
    ]
    if missing:
        raise AsanaConfigError(f"Missing required environment variables: {', '.join(missing)}")

    return AsanaConfig(
        token=os.environ["ASANA_TOKEN"].strip(),
        workspace_gid=os.environ["ASANA_WORKSPACE_GID"].strip(),
        project_gid=os.environ["ASANA_PROJECT_GID"].strip(),
        api_base=os.environ.get("ASANA_API_BASE", DEFAULT_ASANA_API_BASE).strip().rstrip("/"),
        implemented_section_name=os.environ.get(
            "ASANA_IMPLEMENTED_SECTION_NAME", DEFAULT_IMPLEMENTED_SECTION_NAME
        ).strip(),
    )


class AsanaClient:
    def __init__(self, config: AsanaConfig, session: requests.Session | None = None) -> None:
        self.config = config
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {config.token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
        )

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        url = f"{self.config.api_base}{path}"
        try:
            response = self.session.request(method, url, timeout=20, **kwargs)
        except requests.RequestException as exc:
            raise AsanaApiError(f"network error: {exc}") from exc

        if response.ok:
            return response.json()

        reason = response.text.strip()
        try:
            payload = response.json()
            errors = payload.get("errors") or []
            if errors:
                reason = "; ".join(str(error.get("message", error)) for error in errors)
        except ValueError:
            pass

        raise AsanaApiError(f"{response.status_code} {response.reason}: {reason}")

    def create_task(self, description: str, due_on: date) -> dict[str, Any]:
        payload = {
            "data": {
                "workspace": self.config.workspace_gid,
                "projects": [self.config.project_gid],
                "name": description,
                "due_on": due_on.isoformat(),
            }
        }
        return self._request("POST", "/tasks", json=payload).get("data", {})

    def list_project_tasks(self) -> list[dict[str, Any]]:
        params = {"opt_fields": TASK_OPT_FIELDS, "limit": 100}
        tasks: list[dict[str, Any]] = []
        path = f"/projects/{self.config.project_gid}/tasks"

        while True:
            response = self._request("GET", path, params=params)
            tasks.extend(response.get("data", []))
            next_page = response.get("next_page") or {}
            offset = next_page.get("offset")
            if not offset:
                return tasks
            params["offset"] = offset

    def complete_task(self, task_gid: str) -> dict[str, Any]:
        return self._request("PUT", f"/tasks/{task_gid}", json={"data": {"completed": True}}).get(
            "data", {}
        )

    def modify_task(
        self,
        task_gid: str,
        description: str | None = None,
        due_on: date | None = None,
    ) -> dict[str, Any]:
        data: dict[str, Any] = {}
        if description is not None:
            data["name"] = description
        if due_on is not None:
            data["due_on"] = due_on.isoformat()

        if not data:
            raise ValueError("Provide a new description, a new due date, or both.")

        return self._request("PUT", f"/tasks/{task_gid}", json={"data": data}).get("data", {})


def parse_due_date(value: str, today: date | None = None) -> date:
    base = today or date.today()
    normalized = " ".join(value.strip().lower().split())

    if normalized == "today":
        return base
    if normalized == "tomorrow":
        return base + timedelta(days=1)
    if normalized in {"next week", "a week from now", "one week from now"}:
        return base + timedelta(days=7)

    days_match = re.fullmatch(r"(\d+)\s+days?\s+from\s+now", normalized)
    if days_match:
        return base + timedelta(days=int(days_match.group(1)))

    for fmt in (
        "%m/%d/%Y",
        "%m/%d/%y",
        "%Y-%m-%d",
        "%B %d, %Y",
        "%B %d %Y",
        "%b %d, %Y",
        "%b %d %Y",
    ):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue

    raise ValueError(
        "Use today, tomorrow, 3 days from now, next week, MM/DD/YYYY, or YYYY-MM-DD."
    )


def is_active_task(task: dict[str, Any], implemented_section_name: str) -> bool:
    if task.get("completed"):
        return False

    for membership in task.get("memberships", []) or []:
        section = membership.get("section") or {}
        if section.get("name", "").casefold() == implemented_section_name.casefold():
            return False

    return True


def summarize_active_tasks(
    tasks: list[dict[str, Any]], implemented_section_name: str
) -> list[TaskSummary]:
    active_tasks = [task for task in tasks if is_active_task(task, implemented_section_name)]
    return [
        TaskSummary(index, task.get("gid", ""), task.get("name", ""))
        for index, task in enumerate(active_tasks, start=1)
    ]


def format_task_table(tasks: list[TaskSummary]) -> str:
    lines = [
        "================================================",
        "       Active Asana tasks",
        "================================================",
        "list_number | Asana Task id | Task title",
    ]
    if not tasks:
        lines.append("No active Asana tasks found.")
        return "\n".join(lines)

    for task in tasks:
        lines.append(f"{task.list_number:03} | {task.gid} | {task.title}")
    return "\n".join(lines)


def ordinal_to_number(text: str) -> int | None:
    words = {
        "first": 1,
        "second": 2,
        "third": 3,
        "fourth": 4,
        "fifth": 5,
        "sixth": 6,
        "seventh": 7,
        "eighth": 8,
        "ninth": 9,
        "tenth": 10,
    }
    for word, number in words.items():
        if re.search(rf"\b{word}\b", text):
            return number

    match = re.search(r"\b(\d+)(?:st|nd|rd|th)\b", text)
    if match:
        return int(match.group(1))

    return None


def resolve_task_reference(task_ref: str, tasks: list[TaskSummary]) -> tuple[list[TaskSummary], str | None]:
    text = task_ref.strip().lower()
    if not text:
        return [], "Task reference is empty."

    top_match = re.search(r"\btop\s+(\d+)\b", text)
    if top_match:
        count = int(top_match.group(1))
        return tasks[:count], None

    ordinal = ordinal_to_number(text)
    if ordinal is not None:
        matches = [task for task in tasks if task.list_number == ordinal]
        return matches, None if matches else f"No active task found for list number {ordinal:03}."

    number_match = re.fullmatch(r"0*(\d+)", text)
    if number_match:
        number = int(number_match.group(1))
        matches = [
            task for task in tasks if task.list_number == number or task.gid == task_ref.strip()
        ]
        return matches, None if matches else f"No active task found for {task_ref}."

    gid_matches = [task for task in tasks if task.gid == task_ref.strip()]
    if gid_matches:
        return gid_matches, None

    exact_title = [task for task in tasks if task.title.casefold() == task_ref.strip().casefold()]
    if exact_title:
        if len(exact_title) > 1:
            return exact_title, "Multiple tasks matched that title. Use a list_number or task id."
        return exact_title, None

    partial_title = [task for task in tasks if text in task.title.casefold()]
    if len(partial_title) > 1:
        return partial_title, "Multiple tasks matched that title. Use a list_number or task id."
    if partial_title:
        return partial_title, None

    return [], f"No active task matched {task_ref!r}."


def get_client() -> AsanaClient:
    return AsanaClient(load_config())


def create_asana_task(description: str, due_date: str) -> dict[str, Any]:
    """Create an Asana task in the configured workspace and project."""
    description = description.strip()
    if not description:
        return {"success": False, "message": "Task description is required."}

    try:
        config = load_config()
        due_on = parse_due_date(due_date)
        task = AsanaClient(config).create_task(description, due_on)
    except (AsanaConfigError, AsanaApiError, ValueError) as exc:
        return {"success": False, "message": f"failed to submit task: {exc}"}

    task_gid = task.get("gid", "")
    return {
        "success": True,
        "task_gid": task_gid,
        "workspace_gid": config.workspace_gid,
        "project_gid": config.project_gid,
        "due_on": due_on.isoformat(),
        "message": f"successfully submitted task {task_gid}",
    }


def list_asana_tasks() -> dict[str, Any]:
    """List active Asana tasks in the configured project."""
    global LAST_ACTIVE_TASKS

    try:
        config = load_config()
        active_tasks = summarize_active_tasks(
            AsanaClient(config).list_project_tasks(), config.implemented_section_name
        )
    except (AsanaConfigError, AsanaApiError) as exc:
        return {"success": False, "message": f"failed to list tasks: {exc}", "tasks": []}

    LAST_ACTIVE_TASKS = active_tasks
    return {
        "success": True,
        "count": len(active_tasks),
        "tasks": [task.to_dict() for task in active_tasks],
        "table": format_task_table(active_tasks),
    }


def close_asana_task(task_ref: str) -> dict[str, Any]:
    """Close one or more Asana tasks by marking them complete."""
    global LAST_ACTIVE_TASKS

    try:
        config = load_config()
        client = AsanaClient(config)
        active_tasks = LAST_ACTIVE_TASKS or summarize_active_tasks(
            client.list_project_tasks(), config.implemented_section_name
        )
        targets, resolution_error = resolve_task_reference(task_ref, active_tasks)
        if resolution_error:
            return {
                "success": False,
                "message": resolution_error,
                "matches": [task.to_dict() for task in targets],
            }
        if not targets:
            return {"success": False, "message": f"No active task matched {task_ref!r}."}

        results = []
        for task in targets:
            try:
                client.complete_task(task.gid)
                results.append(
                    {
                        "success": True,
                        "asana_task_id": task.gid,
                        "task_title": task.title,
                        "message": f"closed task {task.gid}",
                    }
                )
            except AsanaApiError as exc:
                results.append(
                    {
                        "success": False,
                        "asana_task_id": task.gid,
                        "task_title": task.title,
                        "message": f"failed to close task {task.gid}: {exc}",
                    }
                )
    except (AsanaConfigError, AsanaApiError) as exc:
        return {"success": False, "message": f"failed to close task: {exc}"}

    successful_gids = {result["asana_task_id"] for result in results if result["success"]}
    LAST_ACTIVE_TASKS = [task for task in active_tasks if task.gid not in successful_gids]
    return {
        "success": all(result["success"] for result in results),
        "closed_count": len(successful_gids),
        "results": results,
    }


def modify_asana_task(
    task_ref: str,
    description: str | None = None,
    due_date: str | None = None,
) -> dict[str, Any]:
    """Modify an Asana task title/description and/or due date."""
    global LAST_ACTIVE_TASKS

    new_description = description.strip() if description is not None else None
    if new_description == "":
        return {"success": False, "message": "Description cannot be blank."}

    try:
        due_on = parse_due_date(due_date) if due_date and due_date.strip() else None
        if new_description is None and due_on is None:
            return {"success": False, "message": "Provide a description, a due_date, or both."}

        config = load_config()
        client = AsanaClient(config)
        active_tasks = LAST_ACTIVE_TASKS or summarize_active_tasks(
            client.list_project_tasks(), config.implemented_section_name
        )
        targets, resolution_error = resolve_task_reference(task_ref, active_tasks)
        if resolution_error:
            return {
                "success": False,
                "message": resolution_error,
                "matches": [task.to_dict() for task in targets],
            }
        if not targets:
            return {"success": False, "message": f"No active task matched {task_ref!r}."}
        if len(targets) > 1:
            return {
                "success": False,
                "message": "Multiple tasks matched. Use a single list_number or task id.",
                "matches": [task.to_dict() for task in targets],
            }

        target = targets[0]
        task = client.modify_task(target.gid, description=new_description, due_on=due_on)
    except (AsanaConfigError, AsanaApiError, ValueError) as exc:
        return {"success": False, "message": f"failed to modify task: {exc}"}

    updated_title = task.get("name") or new_description or target.title
    updated_due_on = task.get("due_on") or (due_on.isoformat() if due_on else None)
    updated_summary = TaskSummary(target.list_number, target.gid, updated_title)
    LAST_ACTIVE_TASKS = [
        updated_summary if cached_task.gid == target.gid else cached_task
        for cached_task in active_tasks
    ]

    return {
        "success": True,
        "asana_task_id": target.gid,
        "task_title": updated_title,
        "due_on": updated_due_on,
        "message": f"modified task {target.gid}",
    }


def build_server() -> Any:
    if FastMCP is None:
        raise RuntimeError("fastmcp is required to run this MCP server. Install with `uv sync`.")

    server = FastMCP(
        name="AsanaProjectServer",
        instructions=(
            "Use these tools to create, list, modify, and close tasks in the configured Asana project."
        ),
    )
    server.tool()(create_asana_task)
    server.tool()(list_asana_tasks)
    server.tool()(close_asana_task)
    server.tool()(modify_asana_task)
    return server


mcp = build_server() if FastMCP is not None else None


if __name__ == "__main__":
    if mcp is None:
        raise RuntimeError("fastmcp is required to run this MCP server. Install with `uv sync`.")
    mcp.run()

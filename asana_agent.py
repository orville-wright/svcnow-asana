from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from getpass import getpass
from typing import Any

import requests
from rich.console import Console
from rich.table import Table


ASANA_API_BASE = "https://app.asana.com/api/1.0"
WORKSPACE_GID = "1214958615680522"
PROJECT_GID = "1214982995972383"
IMPLEMENTED_SECTION_NAME = "Implemented"

console = Console()


@dataclass(frozen=True)
class TaskSummary:
    list_number: int
    gid: str
    title: str


class AsanaApiError(RuntimeError):
    pass


class AsanaClient:
    def __init__(self, token: str) -> None:
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
        )

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        url = f"{ASANA_API_BASE}{path}"
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

    def validate_me(self) -> dict[str, Any]:
        return self._request("GET", "/users/me").get("data", {})

    def create_task(self, name: str, due_on: date) -> dict[str, Any]:
        payload = {
            "data": {
                "workspace": WORKSPACE_GID,
                "projects": [PROJECT_GID],
                "name": name,
                "due_on": due_on.isoformat(),
            }
        }
        return self._request("POST", "/tasks", json=payload).get("data", {})

    def get_project_tasks(self) -> list[dict[str, Any]]:
        params = {
            "opt_fields": "gid,name,completed,memberships.section.name",
            "limit": 100,
        }
        tasks: list[dict[str, Any]] = []
        path = f"/projects/{PROJECT_GID}/tasks"

        while True:
            response = self._request("GET", path, params=params)
            tasks.extend(response.get("data", []))
            next_page = response.get("next_page") or {}
            offset = next_page.get("offset")
            if not offset:
                return tasks
            params["offset"] = offset

    def complete_task(self, task_gid: str) -> dict[str, Any]:
        payload = {"data": {"completed": True}}
        return self._request("PUT", f"/tasks/{task_gid}", json=payload).get("data", {})


def get_token() -> str:
    token = os.environ.get("ASANA_TOKEN", "").strip()
    if token:
        return token

    token = prompt_secret("Please enter your Asana Personal Access Token: ").strip()
    if not token:
        console.print("[red]No token provided. Exiting.[/red]")
        sys.exit(1)
    return token


def prompt_user(prompt_text: str) -> str:
    if sys.stdin.isatty():
        try:
            if sys.platform == "win32":
                return read_line_windows(prompt_text)
            return read_line_posix(prompt_text)
        except (ImportError, OSError):
            pass

    return input(format_prompt(prompt_text))


def prompt_secret(prompt_text: str) -> str:
    if sys.stdin.isatty():
        try:
            if sys.platform == "win32":
                return read_line_windows(prompt_text, echo=False)
            return read_line_posix(prompt_text, echo=False)
        except (ImportError, OSError):
            pass

    return getpass(format_prompt(prompt_text))


def format_prompt(prompt_text: str) -> str:
    if prompt_text.endswith(" "):
        return prompt_text
    return f"{prompt_text} "


def read_line_windows(prompt_text: str, echo: bool = True) -> str:
    import msvcrt

    console.print(prompt_text, end="")
    chars: list[str] = []

    while True:
        char = msvcrt.getwch()

        if char in {"\r", "\n"}:
            sys.stdout.write("\n")
            sys.stdout.flush()
            return "".join(chars)

        if char == "\x03":
            raise KeyboardInterrupt

        if char == "\x1a":
            raise EOFError

        if char in {"\x00", "\xe0"}:
            msvcrt.getwch()
            continue

        if char in {"\b", "\x7f"}:
            if chars:
                chars.pop()
                sys.stdout.write("\b \b")
                sys.stdout.flush()
            continue

        if char.isprintable():
            chars.append(char)
            if echo:
                sys.stdout.write(char)
                sys.stdout.flush()


def read_line_posix(prompt_text: str, echo: bool = True) -> str:
    import termios
    import tty

    console.print(prompt_text, end="")
    chars: list[str] = []
    file_descriptor = sys.stdin.fileno()
    old_settings = termios.tcgetattr(file_descriptor)

    try:
        tty.setraw(file_descriptor)
        while True:
            char = sys.stdin.read(1)

            if char in {"\r", "\n"}:
                sys.stdout.write("\n")
                sys.stdout.flush()
                return "".join(chars)

            if char == "\x03":
                raise KeyboardInterrupt

            if char == "\x04":
                raise EOFError

            if char == "\x1b":
                consume_escape_sequence()
                continue

            if char in {"\b", "\x7f", "\x08"}:
                if chars:
                    chars.pop()
                    sys.stdout.write("\b \b")
                    sys.stdout.flush()
                continue

            if char.isprintable():
                chars.append(char)
                if echo:
                    sys.stdout.write(char)
                    sys.stdout.flush()
    finally:
        termios.tcsetattr(file_descriptor, termios.TCSADRAIN, old_settings)


def consume_escape_sequence() -> None:
    import select

    while select.select([sys.stdin], [], [], 0)[0]:
        char = sys.stdin.read(1)
        if char.isalpha() or char == "~":
            return


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

    formats = (
        "%m/%d/%Y",
        "%m/%d/%y",
        "%Y-%m-%d",
        "%B %d, %Y",
        "%B %d %Y",
        "%b %d, %Y",
        "%b %d %Y",
    )
    for fmt in formats:
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue

    raise ValueError(
        "Use today, tomorrow, 3 days from now, next week, MM/DD/YYYY, or YYYY-MM-DD."
    )


def detect_intent(message: str) -> str:
    text = message.strip().lower()
    if not text:
        return "unknown"

    exit_terms = ("exit", "quit", "leave", "goodbye", "bye", "end", "stop")
    if any(re.search(rf"\b{term}\b", text) for term in exit_terms):
        return "exit"

    close_patterns = (
        r"\bclose\b",
        r"\bcomplete\b",
        r"\bmark\b.*\b(done|complete|completed)\b",
        r"\bdone\s+with\b",
        r"\bfinish\b",
    )
    if any(re.search(pattern, text) for pattern in close_patterns):
        return "close"

    list_patterns = (
        r"\blist\b",
        r"\bshow\b",
        r"\bdisplay\b",
        r"\bopen\s+tasks?\b",
        r"\bactive\s+tasks?\b",
        r"\ball\s+tasks?\b",
    )
    if any(re.search(pattern, text) for pattern in list_patterns):
        return "list"

    create_patterns = (
        r"\bcreate\b",
        r"\bnew\s+(task|request)\b",
        r"\bsubmit\b",
        r"\badd\s+(task|request)\b",
    )
    if any(re.search(pattern, text) for pattern in create_patterns):
        return "create"

    return "unknown"


def is_active_task(task: dict[str, Any]) -> bool:
    if task.get("completed"):
        return False

    for membership in task.get("memberships", []) or []:
        section = membership.get("section") or {}
        if section.get("name", "").casefold() == IMPLEMENTED_SECTION_NAME.casefold():
            return False

    return True


def summarize_active_tasks(tasks: list[dict[str, Any]]) -> list[TaskSummary]:
    active_tasks = [task for task in tasks if is_active_task(task)]
    return [
        TaskSummary(index, task.get("gid", ""), task.get("name", ""))
        for index, task in enumerate(active_tasks, start=1)
    ]


def display_tasks(tasks: list[TaskSummary]) -> None:
    console.print("=" * 48)
    console.print("       Active Asana tasks")
    console.print("=" * 48)

    if not tasks:
        console.print("[yellow]No active Asana tasks found.[/yellow]")
        return

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("list_number", style="white", no_wrap=True)
    table.add_column("Asana Task id", style="green", no_wrap=True)
    table.add_column("Task title", style="white")

    for task in tasks:
        table.add_row(f"{task.list_number:03}", task.gid, task.title)

    console.print(table)


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


def select_tasks(identifier: str, tasks: list[TaskSummary]) -> tuple[list[TaskSummary], bool]:
    text = identifier.strip().lower()
    if not text:
        return [], False

    top_match = re.search(r"\btop\s+(\d+)\b", text)
    if top_match:
        count = int(top_match.group(1))
        return tasks[:count], False

    ordinal = ordinal_to_number(text)
    if ordinal is not None:
        return [task for task in tasks if task.list_number == ordinal], False

    number_match = re.fullmatch(r"0*(\d+)", text)
    if number_match:
        number = int(number_match.group(1))
        matches = [
            task for task in tasks if task.list_number == number or task.gid == identifier.strip()
        ]
        return matches, False

    exact_gid = [task for task in tasks if task.gid == identifier.strip()]
    if exact_gid:
        return exact_gid, False

    exact_title = [task for task in tasks if task.title.casefold() == identifier.strip().casefold()]
    if exact_title:
        return exact_title, len(exact_title) > 1

    partial_title = [task for task in tasks if text in task.title.casefold()]
    return partial_title, len(partial_title) > 1


def resolve_close_targets(identifier: str, tasks: list[TaskSummary]) -> list[TaskSummary]:
    matches, ambiguous = select_tasks(identifier, tasks)
    if not ambiguous:
        return matches

    console.print("[yellow]I found more than one matching task.[/yellow]")
    display_tasks(matches)
    answer = prompt_user("Enter the list_number for the task to close").strip()
    selected, _ = select_tasks(answer, matches)
    return selected


def handle_create(client: AsanaClient) -> None:
    description = prompt_user("Whats the description of the task?").strip()
    while not description:
        description = prompt_user("Please enter a task description").strip()

    while True:
        due_text = prompt_user("When is that task due by?").strip()
        try:
            due_on = parse_due_date(due_text)
            break
        except ValueError as exc:
            console.print(f"[red]{exc}[/red]")

    console.print("preparing task...")
    try:
        task = client.create_task(description, due_on)
        console.print(f"submitted task to workspace {WORKSPACE_GID}")
        console.print(f"[green]successfully submitted task {task.get('gid', 'unknown')}[/green]")
    except AsanaApiError as exc:
        console.print(f"[red]failed to submit task: {exc}[/red]")


def handle_list(client: AsanaClient) -> list[TaskSummary]:
    try:
        tasks = summarize_active_tasks(client.get_project_tasks())
    except AsanaApiError as exc:
        console.print(f"[red]failed to list tasks: {exc}[/red]")
        return []

    display_tasks(tasks)
    return tasks


def strip_close_words(message: str) -> str:
    text = re.sub(
        r"\b(close|complete|task|tasks|mark|done|completed|please|the|a|an|to|as)\b",
        " ",
        message,
        flags=re.IGNORECASE,
    )
    return " ".join(text.split())


def handle_close(client: AsanaClient, recent_tasks: list[TaskSummary], message: str) -> list[TaskSummary]:
    tasks = recent_tasks or handle_list(client)
    if not tasks:
        return tasks

    identifier = strip_close_words(message)
    if not identifier:
        identifier = prompt_user("which task do you want to close?").strip()

    targets = resolve_close_targets(identifier, tasks)
    while not targets:
        console.print("[yellow]I could not find a matching task.[/yellow]")
        identifier = prompt_user("which task do you want to close?").strip()
        targets = resolve_close_targets(identifier, tasks)

    for task in targets:
        try:
            client.complete_task(task.gid)
            console.print(f"[green]closed task {task.gid} | {task.title}[/green]")
        except AsanaApiError as exc:
            console.print(f"[red]failed to close task {task.gid}: {exc}[/red]")

    return [task for task in tasks if task not in targets]


def run_chat() -> None:
    token = get_token()
    client = AsanaClient(token)

    try:
        user = client.validate_me()
    except AsanaApiError as exc:
        console.print(f"[red]Asana credential validation failed: {exc}[/red]")
        sys.exit(1)

    name = user.get("name") or "there"
    console.print(f"[green]Authenticated as {name}.[/green]")
    console.print("hello, how can I help you in Asana today?")

    recent_tasks: list[TaskSummary] = []
    while True:
        message = prompt_user("> ")
        intent = detect_intent(message)

        if intent == "exit":
            console.print("Goodbye.")
            return
        if intent == "create":
            handle_create(client)
            console.print("Is there anything more I can help you with?")
            continue
        if intent == "list":
            recent_tasks = handle_list(client)
            console.print("Is there anything more I can help you with?")
            continue
        if intent == "close":
            recent_tasks = handle_close(client, recent_tasks, message)
            console.print("Is there anything more I can help you with?")
            continue

        console.print(
            "I can create a task, list active tasks, close a task, or exit. What would you like to do?"
        )


if __name__ == "__main__":
    run_chat()

from __future__ import annotations

import os
import unittest
from datetime import date
from unittest.mock import patch

from asana_mcp_server import (
    AsanaApiError,
    AsanaClient,
    AsanaConfig,
    AsanaConfigError,
    TaskSummary,
    close_asana_task,
    create_asana_task,
    format_task_table,
    is_active_task,
    list_asana_tasks,
    load_config,
    parse_due_date,
    resolve_task_reference,
    summarize_active_tasks,
)


class FakeResponse:
    def __init__(
        self,
        payload: dict,
        ok: bool = True,
        status_code: int = 200,
        reason: str = "OK",
        text: str = "",
    ) -> None:
        self.payload = payload
        self.ok = ok
        self.status_code = status_code
        self.reason = reason
        self.text = text

    def json(self) -> dict:
        return self.payload


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses
        self.headers: dict[str, str] = {}
        self.calls: list[dict] = []

    def request(self, method: str, url: str, timeout: int, **kwargs):
        self.calls.append({"method": method, "url": url, "timeout": timeout, **kwargs})
        return self.responses.pop(0)


class AsanaMcpServerTest(unittest.TestCase):
    def test_load_config_requires_expected_env_values(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch("asana_mcp_server.load_environment", return_value=None):
                with self.assertRaises(AsanaConfigError):
                    load_config()

    def test_load_config_uses_env_and_defaults(self):
        env = {
            "ASANA_TOKEN": "token",
            "ASANA_WORKSPACE_GID": "workspace",
            "ASANA_PROJECT_GID": "project",
        }
        with patch.dict(os.environ, env, clear=True):
            with patch("asana_mcp_server.load_environment", return_value=None):
                config = load_config()

        self.assertEqual(config.token, "token")
        self.assertEqual(config.workspace_gid, "workspace")
        self.assertEqual(config.project_gid, "project")
        self.assertEqual(config.api_base, "https://app.asana.com/api/1.0")
        self.assertEqual(config.implemented_section_name, "Implemented")

    def test_parse_due_date_values(self):
        today = date(2026, 5, 21)

        self.assertEqual(parse_due_date("today", today), date(2026, 5, 21))
        self.assertEqual(parse_due_date("tomorrow", today), date(2026, 5, 22))
        self.assertEqual(parse_due_date("3 days from now", today), date(2026, 5, 24))
        self.assertEqual(parse_due_date("next week", today), date(2026, 5, 28))
        self.assertEqual(parse_due_date("05/30/2026", today), date(2026, 5, 30))
        self.assertEqual(parse_due_date("2026-05-30", today), date(2026, 5, 30))

    def test_active_task_filter_and_table_formatting(self):
        tasks = [
            {"gid": "1", "name": "Done", "completed": True, "memberships": []},
            {"gid": "2", "name": "Open", "completed": False, "memberships": []},
            {
                "gid": "3",
                "name": "Shipped",
                "completed": False,
                "memberships": [{"section": {"name": "Implemented"}}],
            },
        ]

        self.assertFalse(is_active_task(tasks[0], "Implemented"))
        self.assertTrue(is_active_task(tasks[1], "Implemented"))
        self.assertFalse(is_active_task(tasks[2], "Implemented"))

        active = summarize_active_tasks(tasks, "Implemented")
        self.assertEqual(active, [TaskSummary(1, "2", "Open")])
        self.assertIn("001 | 2 | Open", format_task_table(active))

    def test_resolve_task_reference_forms(self):
        tasks = [
            TaskSummary(1, "121", "Daves test task #1"),
            TaskSummary(2, "122", "Daves test task #2"),
            TaskSummary(3, "123", "Another request"),
        ]

        self.assertEqual(resolve_task_reference("001", tasks)[0], [tasks[0]])
        self.assertEqual(resolve_task_reference("122", tasks)[0], [tasks[1]])
        self.assertEqual(resolve_task_reference("second task", tasks)[0], [tasks[1]])
        self.assertEqual(resolve_task_reference("top 2 tasks", tasks)[0], tasks[:2])
        self.assertEqual(resolve_task_reference("Another request", tasks)[0], [tasks[2]])

    def test_client_create_task_posts_expected_payload(self):
        session = FakeSession([FakeResponse({"data": {"gid": "task-1"}})])
        config = AsanaConfig("token", "workspace", "project")
        client = AsanaClient(config, session=session)

        task = client.create_task("A task", date(2026, 5, 30))

        self.assertEqual(task["gid"], "task-1")
        self.assertEqual(session.calls[0]["method"], "POST")
        self.assertEqual(session.calls[0]["json"]["data"]["workspace"], "workspace")
        self.assertEqual(session.calls[0]["json"]["data"]["projects"], ["project"])

    def test_client_list_tasks_follows_pagination(self):
        session = FakeSession(
            [
                FakeResponse(
                    {
                        "data": [{"gid": "1"}],
                        "next_page": {"offset": "abc"},
                    }
                ),
                FakeResponse({"data": [{"gid": "2"}], "next_page": None}),
            ]
        )
        client = AsanaClient(AsanaConfig("token", "workspace", "project"), session=session)

        self.assertEqual(client.list_project_tasks(), [{"gid": "1"}, {"gid": "2"}])
        self.assertEqual(session.calls[1]["params"]["offset"], "abc")

    def test_client_surfaces_asana_errors(self):
        session = FakeSession(
            [
                FakeResponse(
                    {"errors": [{"message": "bad token"}]},
                    ok=False,
                    status_code=401,
                    reason="Unauthorized",
                )
            ]
        )
        client = AsanaClient(AsanaConfig("token", "workspace", "project"), session=session)

        with self.assertRaisesRegex(AsanaApiError, "bad token"):
            client.list_project_tasks()

    def test_tool_create_success_with_mocked_client(self):
        env = {
            "ASANA_TOKEN": "token",
            "ASANA_WORKSPACE_GID": "workspace",
            "ASANA_PROJECT_GID": "project",
        }
        with patch.dict(os.environ, env, clear=True):
            with patch.object(AsanaClient, "create_task", return_value={"gid": "task-1"}):
                result = create_asana_task("A task", "2026-05-30")

        self.assertTrue(result["success"])
        self.assertEqual(result["task_gid"], "task-1")
        self.assertEqual(result["workspace_gid"], "workspace")

    def test_tool_list_success_with_mocked_client(self):
        env = {
            "ASANA_TOKEN": "token",
            "ASANA_WORKSPACE_GID": "workspace",
            "ASANA_PROJECT_GID": "project",
        }
        api_tasks = [{"gid": "1", "name": "Open", "completed": False, "memberships": []}]
        with patch.dict(os.environ, env, clear=True):
            with patch.object(AsanaClient, "list_project_tasks", return_value=api_tasks):
                result = list_asana_tasks()

        self.assertTrue(result["success"])
        self.assertEqual(result["tasks"][0]["list_number"], "001")

    def test_tool_close_success_with_mocked_client(self):
        env = {
            "ASANA_TOKEN": "token",
            "ASANA_WORKSPACE_GID": "workspace",
            "ASANA_PROJECT_GID": "project",
        }
        api_tasks = [{"gid": "1", "name": "Open", "completed": False, "memberships": []}]
        with patch.dict(os.environ, env, clear=True):
            with patch.object(AsanaClient, "list_project_tasks", return_value=api_tasks):
                with patch.object(AsanaClient, "complete_task", return_value={"gid": "1"}):
                    result = close_asana_task("001")

        self.assertTrue(result["success"])
        self.assertEqual(result["closed_count"], 1)


if __name__ == "__main__":
    unittest.main()

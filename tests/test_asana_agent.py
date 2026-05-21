from datetime import date
import unittest

from asana_agent import (
    TaskSummary,
    detect_intent,
    is_active_task,
    parse_due_date,
    select_tasks,
    strip_close_words,
    summarize_active_tasks,
)


class AsanaAgentTest(unittest.TestCase):
    def test_parse_due_date_relative_values(self):
        today = date(2026, 5, 20)

        self.assertEqual(parse_due_date("today", today), date(2026, 5, 20))
        self.assertEqual(parse_due_date("tomorrow", today), date(2026, 5, 21))
        self.assertEqual(parse_due_date("3 days from now", today), date(2026, 5, 23))
        self.assertEqual(parse_due_date("next week", today), date(2026, 5, 27))

    def test_parse_due_date_explicit_values(self):
        today = date(2026, 5, 20)

        self.assertEqual(parse_due_date("05/22/2026", today), date(2026, 5, 22))
        self.assertEqual(parse_due_date("5/22/26", today), date(2026, 5, 22))
        self.assertEqual(parse_due_date("2026-05-22", today), date(2026, 5, 22))
        self.assertEqual(parse_due_date("May 22, 2026", today), date(2026, 5, 22))

    def test_detect_intent(self):
        self.assertEqual(detect_intent("create a task"), "create")
        self.assertEqual(detect_intent("submit request"), "create")
        self.assertEqual(detect_intent("show active tasks"), "list")
        self.assertEqual(detect_intent("mark the second task done"), "close")
        self.assertEqual(detect_intent("goodbye"), "exit")
        self.assertEqual(detect_intent("what now"), "unknown")

    def test_active_task_filter(self):
        self.assertFalse(is_active_task({"completed": True, "memberships": []}))
        self.assertFalse(
            is_active_task(
                {
                    "completed": False,
                    "memberships": [{"section": {"name": "Implemented"}}],
                }
            )
        )
        self.assertTrue(
            is_active_task(
                {
                    "completed": False,
                    "memberships": [{"section": {"name": "Backlog"}}],
                }
            )
        )

    def test_summarize_active_tasks_numbers_rows_after_filtering(self):
        tasks = [
            {"gid": "1", "name": "Done", "completed": True, "memberships": []},
            {"gid": "2", "name": "Open A", "completed": False, "memberships": []},
            {
                "gid": "3",
                "name": "Implemented A",
                "completed": False,
                "memberships": [{"section": {"name": "Implemented"}}],
            },
            {"gid": "4", "name": "Open B", "completed": False, "memberships": []},
        ]

        self.assertEqual(
            summarize_active_tasks(tasks),
            [
                TaskSummary(1, "2", "Open A"),
                TaskSummary(2, "4", "Open B"),
            ],
        )

    def test_select_tasks_by_list_number_gid_title_ordinal_and_top_n(self):
        tasks = [
            TaskSummary(1, "121", "Daves test task #1"),
            TaskSummary(2, "122", "Daves test task #2"),
            TaskSummary(3, "123", "Another request"),
        ]

        self.assertEqual(select_tasks("001", tasks)[0], [tasks[0]])
        self.assertEqual(select_tasks("122", tasks)[0], [tasks[1]])
        self.assertEqual(select_tasks("Daves test task #1", tasks)[0], [tasks[0]])
        self.assertEqual(select_tasks("second task", tasks)[0], [tasks[1]])
        self.assertEqual(select_tasks("top 2 tasks", tasks)[0], tasks[:2])

    def test_strip_close_words_preserves_identifier(self):
        self.assertEqual(strip_close_words("close the first task"), "first")
        self.assertEqual(strip_close_words("please mark 002 as done"), "002")


if __name__ == "__main__":
    unittest.main()

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from python_backend import task_runner
from python_backend.protocol import TaskRequest


class TaskControlTest(unittest.TestCase):
    def test_resolve_task_concurrency_limits_and_task_type(self):
        self.assertEqual(
            task_runner.resolve_task_concurrency("reformat", {"task_concurrency": 8}),
            4,
        )
        self.assertEqual(
            task_runner.resolve_task_concurrency("font_decrypt", {"task_concurrency": 4}),
            1,
        )
        self.assertEqual(
            task_runner.resolve_task_concurrency("transfer_img", {"concurrency": 2}),
            2,
        )

    def test_request_task_cancel_marks_active_task(self):
        event = task_runner.register_task_cancel_event("task-cancel-1")
        try:
            self.assertFalse(event.is_set())
            self.assertTrue(task_runner.request_task_cancel("task-cancel-1"))
            self.assertTrue(event.is_set())
            self.assertTrue(task_runner.is_task_cancelled("task-cancel-1"))
        finally:
            task_runner.clear_task_cancel_event("task-cancel-1")

    def test_run_task_stops_after_cancel_between_files(self):
        request = TaskRequest(
            task_id="task-cancel-2",
            task_type="reformat",
            input_files=["a.epub", "b.epub", "c.epub"],
            output_dir=None,
            options={"task_concurrency": 1},
        )

        def fake_execute_task(task_type, input_file, output_dir, options):
            if input_file.endswith("a.epub"):
                task_runner.request_task_cancel(request.task_id)
                return 0
            return 0

        with (
            patch.object(task_runner, "execute_task", side_effect=fake_execute_task),
            patch.object(task_runner, "patched_logger") as patched,
            patch.object(task_runner, "mark_epub_generated_by_tool", lambda *_args, **_kwargs: None),
            patch.object(task_runner.os.path, "exists", return_value=True),
            patch.object(
                task_runner,
                "resolve_generated_output_path",
                side_effect=lambda input_file, *_args: input_file.replace(
                    ".epub", "_reformat.epub"
                ),
            ),
        ):
            patched.return_value.__enter__.return_value = None
            patched.return_value.__exit__.return_value = None
            result = task_runner.run_task(request)

        self.assertEqual(result.status, "partial")
        self.assertEqual(result.summary["success"], 1)
        self.assertGreaterEqual(result.summary.get("cancelled", 0), 1)


if __name__ == "__main__":
    unittest.main()

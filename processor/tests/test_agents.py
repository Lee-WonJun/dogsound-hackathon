import json
from pathlib import Path
import unittest

from processor.agents import _run_command, build_claude_command, build_codex_command, extract_display_reply, format_stream_line


class AgentCommandTests(unittest.TestCase):
    def test_codex_initial_command_uses_open_permissions(self) -> None:
        command = build_codex_command(
            resume=False,
            workspace="/tmp/workspace",
            open_permissions=True,
            json_output=True,
        )

        self.assertEqual(command[:2], ["codex", "exec"])
        self.assertIn("--skip-git-repo-check", command)
        self.assertIn("-C", command)
        self.assertIn("/tmp/workspace", command)
        self.assertIn("--dangerously-bypass-approvals-and-sandbox", command)
        self.assertEqual(command[-1], "-")

    def test_codex_resume_command_targets_session_or_last(self) -> None:
        command = build_codex_command(
            resume=True,
            workspace="/tmp/workspace",
            open_permissions=True,
            json_output=True,
            session_id="session-123",
        )

        self.assertEqual(command[:3], ["codex", "exec", "resume"])
        self.assertIn("session-123", command)
        self.assertIn("--dangerously-bypass-approvals-and-sandbox", command)
        self.assertEqual(command[-1], "-")

    def test_codex_command_can_pass_model(self) -> None:
        command = build_codex_command(
            resume=False,
            workspace="/tmp/workspace",
            open_permissions=True,
            json_output=True,
            model="gpt-5.3-codex-spark",
        )

        self.assertIn("--model", command)
        self.assertIn("gpt-5.3-codex-spark", command)
        self.assertLess(command.index("--model"), command.index("-"))

    def test_codex_command_can_pass_reasoning_effort(self) -> None:
        command = build_codex_command(
            resume=False,
            workspace="/tmp/workspace",
            open_permissions=True,
            json_output=True,
            model="gpt-5.5",
            reasoning_effort="low",
        )

        self.assertIn("--model", command)
        self.assertIn("gpt-5.5", command)
        self.assertIn("-c", command)
        self.assertIn('model_reasoning_effort="low"', command)
        self.assertLess(command.index("-c"), command.index("--json"))

    def test_claude_command_uses_print_continue_and_open_permissions(self) -> None:
        initial = build_claude_command(resume=False, open_permissions=True, prompt="hello")
        resumed = build_claude_command(resume=True, open_permissions=True, prompt="again")

        self.assertEqual(initial[:2], ["claude", "-p"])
        self.assertIn("--dangerously-skip-permissions", initial)
        self.assertEqual(initial[-1], "hello")
        self.assertIn("-c", resumed)
        self.assertIn("-p", resumed)
        self.assertEqual(resumed[-1], "again")

    def test_extract_display_reply_prefers_assistant_json_text(self) -> None:
        stdout = "\n".join(
            [
                json.dumps({"type": "event", "message": "starting"}),
                json.dumps({"role": "assistant", "content": [{"type": "output_text", "text": "Built the game."}]}),
            ]
        )

        self.assertEqual(extract_display_reply(stdout), "Built the game.")

    def test_extract_display_reply_falls_back_to_plain_output(self) -> None:
        self.assertEqual(extract_display_reply("line one\nline two\n"), "line one\nline two")

    def test_run_command_times_out_long_running_process(self) -> None:
        result = _run_command(
            ["python3", "-c", "import time; time.sleep(5)"],
            cwd=Path("."),
            timeout_seconds=1,
        )

        self.assertTrue(result.timed_out)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("timed out", result.stderr)

    def test_run_command_streams_stdout_lines_before_exit(self) -> None:
        seen = []

        result = _run_command(
            ["python3", "-c", "print('first', flush=True); print('second', flush=True)"],
            cwd=Path("."),
            timeout_seconds=5,
            on_output=lambda source, line: seen.append((source, line.strip())),
        )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(seen, [("stdout", "first"), ("stdout", "second")])
        self.assertEqual(result.stdout, "first\nsecond\n")

    def test_run_command_times_out_when_output_goes_idle(self) -> None:
        seen = []

        result = _run_command(
            ["python3", "-c", "import time; print('first', flush=True); time.sleep(5)"],
            cwd=Path("."),
            timeout_seconds=10,
            idle_timeout_seconds=1,
            on_output=lambda source, line: seen.append((source, line.strip())),
        )

        self.assertTrue(result.idle_timed_out)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(("stdout", "first"), seen)
        self.assertIn("produced no output", result.stderr)

    def test_format_stream_line_summarizes_codex_json_events(self) -> None:
        line = json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "Working now."}})

        self.assertEqual(format_stream_line("stdout", line), "Working now.")


if __name__ == "__main__":
    unittest.main()

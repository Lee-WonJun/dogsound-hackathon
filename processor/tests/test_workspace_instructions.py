import tempfile
import unittest
from pathlib import Path

from processor.cli import _ensure_workspace_instructions


class WorkspaceInstructionTests(unittest.TestCase):
    def test_codex_instructions_are_written_to_agents_md(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = _ensure_workspace_instructions(
                workspace=Path(tmpdir),
                agent_name="codex",
                context="Make it tiny.",
            )

            self.assertEqual(path.name, "AGENTS.md")
            text = path.read_text(encoding="utf-8")
            self.assertIn("brilliant game designer", text)
            self.assertIn("cipher-like shorthand", text)
            self.assertIn("The input is game design direction", text)
            self.assertIn("Make it tiny.", text)
            self.assertIn("ANALYSIS.md", text)
            self.assertNotIn("Minimum playable requirements", text)

    def test_claude_instructions_are_written_to_claude_md(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = _ensure_workspace_instructions(
                workspace=Path(tmpdir),
                agent_name="claude",
                context="",
            )

            self.assertEqual(path.name, "CLAUDE.md")

    def test_existing_file_is_preserved_outside_managed_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            agents = workspace / "AGENTS.md"
            agents.write_text("# Existing\n\nKeep this.\n", encoding="utf-8")

            _ensure_workspace_instructions(workspace=workspace, agent_name="codex", context="First.")
            _ensure_workspace_instructions(workspace=workspace, agent_name="codex", context="Second.")

            text = agents.read_text(encoding="utf-8")
            self.assertIn("Keep this.", text)
            self.assertNotIn("First.", text)
            self.assertIn("Second.", text)
            self.assertEqual(text.count("generated-game-input-instructions:start"), 1)


if __name__ == "__main__":
    unittest.main()

import unittest

from processor.prompt import PromptInput, render_agent_instructions, render_prompt
from processor.tokenizer import summarize_tokens


class PromptTests(unittest.TestCase):
    def test_render_prompt_sends_only_input_for_every_message(self) -> None:
        first = render_prompt(
            PromptInput(
                tokens="abcxyz",
                stats=summarize_tokens("abcxyz"),
                utterance_index=1,
                workspace="/tmp/workspace",
                context="This must not be repeated.",
            )
        )
        second = render_prompt(
            PromptInput(
                tokens="def",
                stats=summarize_tokens("def"),
                utterance_index=2,
                workspace="/tmp/workspace",
                context="This must not be repeated.",
            )
        )

        self.assertEqual(first, "abcxyz\n")
        self.assertEqual(second, "def\n")

    def test_render_agent_instructions_sets_game_designer_frame(self) -> None:
        instructions = render_agent_instructions("Use a compact arcade style.")

        self.assertIn("brilliant game designer", instructions)
        self.assertIn("cipher-like shorthand", instructions)
        self.assertIn("The input is game design direction", instructions)
        self.assertIn("coherent, concrete game idea", instructions)
        self.assertIn("Use a compact arcade style.", instructions)
        self.assertIn("Phaser 3", instructions)
        self.assertIn("Before implementation", instructions)
        self.assertIn("how you read the input as game requirements", instructions)
        self.assertIn("multiple possible readings", instructions)
        self.assertIn("chosen reading and why it fits", instructions)
        self.assertIn("mechanics, rules, objectives, controls, pacing, theme, UI, audio, level structure", instructions)
        self.assertIn("Do not default to a map update", instructions)
        self.assertIn("written analysis selects it as the best fit", instructions)
        self.assertIn("product planning and game design requirements", instructions)
        self.assertIn("best fits the project", instructions)
        self.assertIn("instead of defaulting to a fixed type of change", instructions)
        self.assertIn("ANALYSIS.md", instructions)
        self.assertIn("README.md", instructions)
        self.assertNotIn("Minimum playable requirements", instructions)
        self.assertNotIn("WASD and arrow-key controls", instructions)
        self.assertNotIn("Audio feedback", instructions)
        self.assertNotIn("every character in the Input", instructions)
        self.assertNotIn("INPUT_INTERPRETATION.md", instructions)
        self.assertNotIn("implementation_hint", instructions)
        self.assertNotIn("volatile pulse", instructions)
        self.assertNotIn("steady hold", instructions)
        self.assertNotIn("bright cluster", instructions)
        self.assertNotIn("S1", instructions)
        self.assertNotIn("Pattern notes", instructions)
        self.assertNotIn("same development thread", instructions)
        self.assertNotIn("previous session", instructions)
        self.assertNotIn("preserve", instructions)
        self.assertNotIn("smallest useful", instructions)
        self.assertNotIn("fresh game", instructions)
        self.assertNotIn("replace the previous", instructions)
        self.assertNotIn("larger redesign", instructions)
        self.assertNotIn("rebuilding the game", instructions)
        self.assertNotIn("assume", instructions.lower())
        self.assertNotIn("treat", instructions.lower())
        self.assertNotIn("meaningless", instructions.lower())
        self.assertNotIn("token", instructions.lower())
        self.assertNotIn("symbol", instructions.lower())
        self.assertNotIn("directive", instructions.lower())

    def test_render_agent_instructions_does_not_expose_input_transport(self) -> None:
        instructions = render_agent_instructions().lower()

        self.assertNotIn("dogsound", instructions)
        self.assertNotIn("dog sound", instructions)
        self.assertNotIn("acoustic", instructions)
        self.assertNotIn("microphone", instructions)
        self.assertNotIn("audio input", instructions)
        self.assertNotIn("audio stream", instructions)
        self.assertNotIn("token", instructions)


if __name__ == "__main__":
    unittest.main()

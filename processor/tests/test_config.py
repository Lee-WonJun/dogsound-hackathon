import unittest

from processor.config import DEFAULT_CONFIG


class ConfigTests(unittest.TestCase):
    def test_default_log_path_is_workspace_local_hidden_file(self) -> None:
        self.assertIsNone(DEFAULT_CONFIG["logging"]["path"])

    def test_default_agent_timeout_is_bounded(self) -> None:
        self.assertIsNone(DEFAULT_CONFIG["agent"]["model"])
        self.assertIsNone(DEFAULT_CONFIG["agent"]["reasoning_effort"])
        self.assertEqual(DEFAULT_CONFIG["agent"]["timeout_seconds"], 600)
        self.assertEqual(DEFAULT_CONFIG["agent"]["idle_timeout_seconds"], 120)

    def test_default_audio_uses_live_noise_calibration(self) -> None:
        self.assertIs(DEFAULT_CONFIG["audio"]["auto_threshold"], True)
        self.assertEqual(DEFAULT_CONFIG["audio"]["calibration_ms"], 1200)
        self.assertEqual(DEFAULT_CONFIG["audio"]["min_utterance_ms"], 120)


if __name__ == "__main__":
    unittest.main()

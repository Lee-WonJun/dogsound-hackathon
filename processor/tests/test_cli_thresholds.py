import unittest

from processor.cli import _suggest_thresholds_from_noise


class ThresholdSuggestionTests(unittest.TestCase):
    def test_noise_floor_raises_stop_threshold(self) -> None:
        thresholds = _suggest_thresholds_from_noise(
            [0.045, 0.050, 0.052, 0.055, 0.058, 0.060, 0.064],
            configured_start=0.015,
            configured_stop=0.010,
        )

        self.assertGreater(thresholds["stop_threshold"], 0.060)
        self.assertGreater(thresholds["start_threshold"], thresholds["stop_threshold"])

    def test_configured_thresholds_are_the_floor_for_quiet_inputs(self) -> None:
        thresholds = _suggest_thresholds_from_noise(
            [0.0, 0.001, 0.002],
            configured_start=0.015,
            configured_stop=0.010,
        )

        self.assertEqual(thresholds["start_threshold"], 0.015)
        self.assertEqual(thresholds["stop_threshold"], 0.010)


if __name__ == "__main__":
    unittest.main()

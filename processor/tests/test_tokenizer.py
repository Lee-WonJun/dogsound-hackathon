import math
import unittest

from processor.tokenizer import quantize_to_letters, summarize_tokens, tokenize_samples


class TokenizerTests(unittest.TestCase):
    def test_quantize_to_letters_maps_unit_interval_to_alphabet(self) -> None:
        self.assertEqual(quantize_to_letters([0.0, 0.5, 1.0]), "amz")

    def test_tokenize_samples_emits_lowercase_letters(self) -> None:
        sample_rate = 8000
        frame_size = int(sample_rate * 0.02)
        samples = []
        for frame_index in range(16):
            amplitude = 0.03 + frame_index * 0.01
            for sample_index in range(frame_size):
                angle = 2 * math.pi * 220 * sample_index / sample_rate
                samples.append(amplitude * math.sin(angle))

        tokens = tokenize_samples(samples, sample_rate=sample_rate, frame_ms=20, hop_ms=20)

        self.assertGreater(len(tokens), 0)
        self.assertTrue(tokens.islower())
        self.assertTrue(tokens.isalpha())

    def test_tokenize_samples_rejects_silence(self) -> None:
        with self.assertRaisesRegex(ValueError, "too quiet"):
            tokenize_samples([0.0] * 800, sample_rate=8000, frame_ms=20)

    def test_summarize_tokens_counts_shape(self) -> None:
        summary = summarize_tokens("abbz")

        self.assertEqual(summary["length"], 4)
        self.assertEqual(summary["min"], 0)
        self.assertEqual(summary["max"], 25)
        self.assertEqual(summary["counts"]["b"], 2)
        self.assertEqual(summary["rises"], 2)
        self.assertEqual(summary["flats"], 1)
        self.assertEqual(summary["jumps"], 1)
        self.assertEqual(summary["longest_runs"][0]["char"], "b")


if __name__ == "__main__":
    unittest.main()
